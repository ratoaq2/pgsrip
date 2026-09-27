from __future__ import annotations

import functools
import logging
import os
import typing
from datetime import timedelta

from babelfish import Language
from trakit.api import trakit

from pgsrip.media import Pgs
from pgsrip.media_path import MediaPath
from pgsrip.options import Options
from pgsrip.track_flags import TrackFlags

if typing.TYPE_CHECKING:
    from pgsrip.diagnostics import Check

logger = logging.getLogger(__name__)


def _parse_language(code: str | None) -> Language | None:
    return Language.fromcleanit(code) or None if code else None


class Track:
    """A PGS track of a media, with no detail of the tool that reads it."""

    @classmethod
    def create(
        cls, id: int, name: str | None, language_tags: list[str | None], container_flags: dict[str, bool | None]
    ) -> Track:
        """Merge the facts of the container with the guess from the track name.

        `language_tags` is in order of preference: the first tag that parses wins, else `und`.
        """
        expected_language = next(
            (lang for lang in map(_parse_language, language_tags) if lang), Language.fromcleanit('und')
        )
        options = {'expected_language': expected_language} if expected_language else {}
        guess = trakit(name, options) if name else {}

        # container `true` wins; container `false`/absent falls back to the track-name guess.
        return cls(
            id,
            name=name,
            language=guess.get('language') or expected_language,
            disabled=container_flags.get('disabled') or None,
            default=container_flags.get('default') or None,
            original=container_flags.get('original') or None,
            forced=container_flags.get('forced') or guess.get('forced') or None,
            hearing_impaired=container_flags.get('hearing_impaired') or guess.get('hearing_impaired') or None,
            commentary=container_flags.get('commentary') or guess.get('commentary') or None,
            descriptive=container_flags.get('descriptive') or guess.get('descriptive') or None,
            closed_caption=guess.get('closed_caption') or None,  # no container equivalent
            external=guess.get('external'),
            version=guess.get('version'),
        )

    def __init__(
        self,
        id: int,
        name: str | None = None,
        language: Language | None = None,
        disabled: bool | None = None,
        default: bool | None = None,
        original: bool | None = None,
        forced: bool | None = None,
        hearing_impaired: bool | None = None,
        commentary: bool | None = None,
        descriptive: bool | None = None,
        closed_caption: bool | None = None,
        external: bool | None = None,
        version: str | None = None,
    ):
        self.id = id
        self.name = name
        self.language = language
        self.disabled = disabled
        self.default = default
        self.original = original
        self.forced = forced
        self.hearing_impaired = hearing_impaired
        self.commentary = commentary
        self.descriptive = descriptive
        self.closed_caption = closed_caption
        self.external = external
        self.version = version

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


class Source(typing.Protocol):
    """A tool that reads the PGS tracks of the media files with some extensions.

    `pgsrip.sources.SOURCES` is the built-in list, in order of preference.
    """

    #: the reason to show when the tool is not installed
    missing: typing.ClassVar[str]
    extensions: typing.ClassVar[tuple[str, ...]]

    @classmethod
    def check(cls) -> list[Check]:
        """The lines of `pgsrip doctor` for this tool."""

    def probe(self, path: str) -> list[Track]:
        """The PGS tracks of the file. Raise FileNotFoundError when the tool is not installed."""

    def extract(self, path: str, targets: dict[int, str]) -> dict[int, str]:
        """Extract the tracks with one call. `targets` maps a track id to a .sup path.

        Return the .sup path of each track: a source can give another path than the target.
        """


class Extraction:
    """One call of the source for all the selected tracks of a media, on the first read.

    The bytes stay on disk until each track reads them. When the call fails, each track gets the same error.
    """

    def __init__(self, source: Source, media_path: MediaPath, pgs_medias: list[Pgs]):
        self.source = source
        self.media_path = media_path
        self.pgs_medias = pgs_medias
        self._paths: dict[int, str] | None = None
        self._error: Exception | None = None

    def extract(self) -> dict[int, str]:
        lang_ext = f'.{str(self.media_path.language)}' if self.media_path.language else ''
        targets: dict[int, str] = {}
        for pgs in self.pgs_medias:
            assert pgs.track is not None
            targets[pgs.track.id] = os.path.join(pgs.temp_folder, f'{pgs.track.id}{lang_ext}.sup')

        logger.debug('Extracting %d tracks from %s', len(targets), self.media_path)
        return self.source.extract(str(self.media_path), targets)

    def read(self, track: Track) -> bytes:
        if self._paths is None and self._error is None:
            try:
                self._paths = self.extract()
            except Exception as e:
                self._error = e

        if self._error is not None:
            raise self._error

        assert self._paths is not None
        with open(self._paths[track.id], mode='rb') as f:
            return f.read()


class Media:
    def __init__(self, path: str, source: Source | None = None):
        self.media_path = MediaPath(path)
        self.name = str(self.media_path)
        if source is None:
            self.source, self.tracks = self.find_source(path)
        else:
            self.source, self.tracks = source, source.probe(path)
        self.languages = {t.language for t in self.tracks}

    @staticmethod
    def find_source(path: str) -> tuple[Source, list[Track]]:
        """The first built-in source that reads the file, and the tracks that it finds."""
        from pgsrip.sources import EXTENSIONS, SOURCES  # pgsrip.sources imports this module

        extension = os.path.splitext(path.lower())[1]
        source_types = [s for s in SOURCES if extension in s.extensions]
        if not source_types:
            raise ValueError(f'unsupported extension, expected one of {", ".join(sorted(EXTENSIONS))}')

        for source_type in source_types:
            source = source_type()
            try:
                return source, source.probe(path)
            except FileNotFoundError as e:
                logger.debug('Cannot use %s for %s: %s', source_type.__name__, path, e)

        raise FileNotFoundError(source_types[0].missing)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self.media_path}]>'

    def __str__(self) -> str:
        return str(self.media_path)

    @property
    def age(self) -> timedelta:
        if self.media_path.exists():
            return self.media_path.m_age

        return timedelta()

    def filter_reason(self, options: Options) -> str | None:
        """Return why this media does not match the options, or None when it does."""
        if options.age and self.age > options.age:
            return f'file is older than {options.age}'

        if options.languages and not self.languages.intersection(options.languages):
            available = ', '.join(sorted(str(lang) for lang in self.languages if lang)) or 'none'
            return f'no track for the selected languages (available: {available})'

        return None

    def matches(self, options: Options) -> bool:
        return self.filter_reason(options) is None

    def get_pgs_medias(self, options: Options) -> list[Pgs]:
        candidates: list[Track] = []
        for t in self.tracks:
            if t.disabled:
                continue
            if options.languages and t.language not in options.languages:
                logger.debug('Filtering out track %s:%s in %s', t.id, t.language, self)
                continue
            candidates.append(t)

        candidates.sort(key=lambda x: x.id)

        # group on the full candidate set (not the eventually-selected one) so a track's `.track<n>`
        # suffix is stable across runs regardless of `one_per_lang`/`--with`/`--without` filtering.
        groups: dict[tuple[Language | None, TrackFlags], list[Track]] = {}
        for t in candidates:
            groups.setdefault((t.language, t.flags), []).append(t)
        # the first (lowest-id) track of a group stays unlabeled; later ones get a 2, 3, ... ordinal
        suffixes = {t.id: i + 1 for members in groups.values() for i, t in enumerate(members) if i > 0}

        selected: set[tuple[Language | None, TrackFlags | None]] = set()
        pgs_medias: list[Pgs] = []
        extraction = Extraction(self.source, self.media_path, pgs_medias)
        for t in candidates:
            key = (t.language, None if options.one_per_language else t.flags)
            if options.one_per_lang and key in selected:
                logger.debug('Skipping track %s:%s in %s', t.id, t.language, self)
                continue
            if not t.flags.matches(options.include_flags, options.exclude_flags):
                logger.debug('Filtering out track %s:%s in %s', t.id, t.language, self)
                continue

            pgs = Pgs(
                self.media_path.translate(language=t.language, flags=t.flags, track_id=suffixes.get(t.id)),
                options=options,
                data_reader=functools.partial(extraction.read, t),
                track=t,
            )
            pgs.source_path = self.media_path
            if pgs.matches(options):
                logger.debug('Selecting track %s:%s in %s', t.id, t.language, self)
                pgs_medias.append(pgs)
                selected.add(key)

        return pgs_medias
