import json
import logging
import os
import typing
from subprocess import check_output

from babelfish import Language
from trakit.api import trakit

from pgsrip.media import Media, Pgs
from pgsrip.media_path import MediaPath
from pgsrip.options import Options
from pgsrip.track_flags import TrackFlags

logger = logging.getLogger(__name__)


def _parse_language(code: str | None) -> Language | None:
    return Language.fromcleanit(code) or None if code else None


class MkvPgs(Pgs):
    @classmethod
    def read_data(cls, media_path: MediaPath, mkv_track_id: int, temp_folder: str) -> bytes:
        lang_ext = f'.{str(media_path.language)}' if media_path.language else ''
        sup_file = os.path.join(temp_folder, f'{mkv_track_id}{lang_ext}.sup')
        cmd = ['mkvextract', str(media_path), 'tracks', f'{mkv_track_id}:{sup_file}']
        check_output(cmd)
        with open(sup_file, mode='rb') as f:
            return f.read()

    def __init__(
        self,
        media_path: MediaPath,
        mkv_track_id: int,
        language: Language,
        flags: TrackFlags,
        options: Options,
        track_id: int | None = None,
    ):
        temp_folder = media_path.create_temp_folder()
        super().__init__(
            media_path=media_path.translate(language=language, flags=flags, track_id=track_id),
            options=options,
            data_reader=lambda: self.read_data(
                media_path=media_path, mkv_track_id=mkv_track_id, temp_folder=temp_folder
            ),
            temp_folder=temp_folder,
        )
        self.source_path = media_path
        self.track_id = mkv_track_id

    def __str__(self) -> str:
        return f'{self.media_path.translate(language=Language("und"))} [{self.track_id}:{self.media_path.language}]'


class MkvTrack:
    def __init__(self, track: dict[str, typing.Any]):
        properties = track.get('properties', {})
        self.id: int = track['id']
        self.name: str | None = properties.get('track_name')
        self.type: str = track['type']
        self.codec: str = track['codec']

        # mkvmerge always reports language_ietf, but it may not parse (e.g. a malformed tag); fall back to
        # the alpha3 language (639-2/B: fre, ger, chi, dut, gre, rum, may, cze) before giving up to und.
        language_ietf = properties.get('language_ietf')
        language_alpha = properties.get('language')
        expected_language = (
            _parse_language(language_ietf) or _parse_language(language_alpha) or Language.fromcleanit('und')
        )

        options = {'expected_language': expected_language} if expected_language else {}
        guess = trakit(self.name, options) if self.name else {}
        self.language: Language | None = guess.get('language') or expected_language
        self.disabled = None if properties.get('enabled_track') else True

        # container `true` wins; container `false`/absent falls back to the track-name guess.
        self.default: bool | None = properties.get('default_track') or None
        self.original: bool | None = properties.get('flag_original') or None
        self.forced: bool | None = properties.get('forced_track') or guess.get('forced') or None
        self.hearing_impaired: bool | None = (
            properties.get('flag_hearing_impaired') or guess.get('hearing_impaired') or None
        )
        self.commentary: bool | None = properties.get('flag_commentary') or guess.get('commentary') or None
        self.descriptive: bool | None = properties.get('flag_text_descriptions') or guess.get('descriptive') or None
        self.closed_caption: bool | None = guess.get('closed_caption') or None  # no container equivalent
        self.external: bool | None = guess.get('external')
        self.version: str | None = guess.get('version')

    @property
    def flags(self) -> TrackFlags:
        return TrackFlags(
            forced=bool(self.forced),
            hearing_impaired=bool(self.hearing_impaired),
            closed_caption=bool(self.closed_caption),
            commentary=bool(self.commentary),
            descriptive=bool(self.descriptive),
            default=bool(self.default),
            original=bool(self.original),
            version=self.version,
        )

    def to_dict(self) -> dict[str, typing.Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{str(self)}]>'

    def __str__(self) -> str:
        return f'{self.to_dict()}'


class Mkv(Media):
    def __init__(self, path: str):
        metadata = json.loads(check_output(['mkvmerge', '-i', '-F', 'json', path]))
        tracks = [MkvTrack(t) for t in metadata.get('tracks', [])]
        super().__init__(MediaPath(path), languages={t.language for t in tracks})
        self.tracks = tracks

    def get_pgs_medias(self, options: Options) -> typing.Iterable[Pgs]:
        candidates: list[MkvTrack] = []
        for t in self.tracks:
            if t.type != 'subtitles' or t.codec != 'HDMV PGS' or t.disabled:
                continue
            if not t.language:
                logger.debug('Skipping unknown language track %s in %s', t.id, self)
                continue
            if options.languages and t.language not in options.languages:
                logger.debug('Filtering out track %s:%s in %s', t.id, t.language, self)
                continue
            candidates.append(t)

        candidates.sort(key=lambda x: x.id)

        # group on the full candidate set (not the eventually-selected one) so a track's `.track<n>`
        # suffix is stable across runs regardless of `one_per_lang`/`--with`/`--without` filtering.
        groups: dict[tuple[Language | None, TrackFlags], list[MkvTrack]] = {}
        for t in candidates:
            groups.setdefault((t.language, t.flags), []).append(t)
        # the first (lowest-id) track of a group stays unlabeled; later ones get a 2, 3, ... ordinal
        suffixes = {t.id: i + 1 for members in groups.values() for i, t in enumerate(members) if i > 0}

        selected: set[tuple[Language | None, TrackFlags | None]] = set()
        for t in candidates:
            key = (t.language, None if options.one_per_language else t.flags)
            if options.one_per_lang and key in selected:
                logger.debug('Skipping track %s:%s in %s', t.id, t.language, self)
                continue
            if not t.flags.matches(options.include_flags, options.exclude_flags):
                logger.debug('Filtering out track %s:%s in %s', t.id, t.language, self)
                continue

            assert t.language is not None
            track_id = suffixes.get(t.id)
            pgs = MkvPgs(self.media_path, t.id, t.language, t.flags, options=options, track_id=track_id)
            if pgs.matches(options):
                logger.debug('Selecting track %s:%s in %s', t.id, t.language, self)
                yield pgs
                selected.add(key)
