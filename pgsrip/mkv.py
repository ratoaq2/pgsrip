import json
import logging
import os
import typing
from subprocess import check_output

from babelfish import Language

from trakit.api import trakit

from pgsrip.media import Media, Pgs
from pgsrip.media_path import MediaPath
from pgsrip.options import Options, SubtitleTypeFilter

logger = logging.getLogger(__name__)


class MkvPgs(Pgs):

    @classmethod
    def read_data(cls, media_path: MediaPath, track_id: int, temp_folder: str):
        lang_ext = f'.{str(media_path.language)}' if media_path.language else ''
        sup_file = os.path.join(temp_folder, f'{track_id}{lang_ext}.sup')
        cmd = ['mkvextract', str(media_path), 'tracks', f'{track_id}:{sup_file}']
        check_output(cmd)
        with open(sup_file, mode='rb') as f:
            return f.read()

    def __init__(self, media_path: MediaPath, track_id: int, language: Language, number: int, options: Options):
        temp_folder = media_path.create_temp_folder()
        super().__init__(media_path=media_path.translate(language=language, number=number),
                         options=options,
                         data_reader=lambda: self.read_data(
                             media_path=media_path, track_id=track_id, temp_folder=temp_folder),
                         temp_folder=temp_folder)
        self.track_id = track_id

    def __str__(self):
        return (f'{self.media_path.translate(language=Language("und"), number=0)} '
                f'[{self.track_id}:{self.media_path.language}]')


class MkvTrack:

    def __init__(self, track: dict):
        self.id = track['id']
        self.type = track['type']
        self.codec = track['codec']
        self.properties = track.get('properties', {})

    @property
    def enabled(self):
        return self.properties.get('enabled_track')

    @property
    def language(self):
        lang_ietf = self.properties.get('language_ietf')
        lang_alpha = self.properties.get('language')
        track_name = self.properties.get('track_name')

        language = Language.fromcleanit(lang_ietf or lang_alpha or 'und')
        options = {'expected_language': language} if language else {}
        guess = trakit(track_name, options) if track_name else {}

        return guess.get('language') or language

    @property
    def forced(self):
        return self.properties.get('forced_track')

    @property
    def is_sdh(self):
        """Check if subtitle is SDH (Subtitles for the Deaf and Hard of hearing)"""
        track_name = self.properties.get('track_name', '').lower()
        return any(term in track_name for term in ['sdh', 'hearing impaired', 'deaf', 'cc'])

    @property
    def is_full(self):
        """Check if subtitle is marked as FULL"""
        track_name = self.properties.get('track_name', '').lower()
        # Consider a subtitle as FULL if it's not explicitly forced and not SDH
        # or if it's explicitly marked as full/complete
        return (not self.forced and not self.is_sdh) or any(term in track_name for term in ['full', 'complete'])

    def matches_type_filter(self, subtitle_filter: SubtitleTypeFilter) -> bool:
        """Check if this track matches the subtitle type filter"""
        if subtitle_filter == SubtitleTypeFilter.ALL:
            return True
        elif subtitle_filter == SubtitleTypeFilter.FULL_ONLY:
            return self.is_full and not self.forced and not self.is_sdh
        elif subtitle_filter == SubtitleTypeFilter.FORCED_INCLUDED:
            return self.is_full or self.forced
        elif subtitle_filter == SubtitleTypeFilter.FORCED_ONLY:
            return self.forced
        elif subtitle_filter == SubtitleTypeFilter.SDH_INCLUDED:
            return self.is_full or self.is_sdh
        elif subtitle_filter == SubtitleTypeFilter.SDH_ONLY:
            return self.is_sdh
        elif subtitle_filter == SubtitleTypeFilter.ALL_INCLUDED:
            return self.is_full or self.forced or self.is_sdh
        return True

    def __repr__(self):
        return f'<{self.__class__.__name__} [{str(self)}]>'

    def __str__(self):
        return f'{self.id}:{self.type}:{self.codec}:{self.language}:{self.enabled}:{self.forced}:{self.is_full}:{self.is_sdh}'


class Mkv(Media):

    def __init__(self, path: str):
        metadata = json.loads(check_output(['mkvmerge', '-i', '-F', 'json', path]))
        tracks = [MkvTrack(t) for t in metadata.get('tracks', [])]
        super().__init__(MediaPath(path), languages={t.language for t in tracks})
        self.tracks = tracks

    def get_pgs_medias(self, options: Options):
        tracks = [t for t in self.tracks
                  if t.type == 'subtitles' and t.codec == 'HDMV PGS' and t.enabled]
        tracks.sort(key=lambda x: x.forced)
        tracks.sort(key=lambda x: x.id)
        selected_languages: typing.Dict[Language, int] = {}
        # For certain filters, we need to track different types separately
        selected_types_per_lang: typing.Dict[typing.Tuple[Language, str], int] = {}

        for t in tracks:
            language = t.language
            if options.languages and language not in options.languages:
                logger.debug('Filtering out track %s:%s in %s', t.id, language, self)
                continue

            # Apply subtitle type filter
            if not t.matches_type_filter(options.subtitle_type_filter):
                logger.debug('Filtering out track %s:%s (type filter: %s) in %s',
                           t.id, language, options.subtitle_type_filter.value, self)
                continue

            # Determine track type for naming and selection logic
            track_type = 'forced' if t.forced else ('sdh' if t.is_sdh else 'full')
            type_key = (language, track_type)

            # For mixed filters (forced-included, sdh-included, all-included), allow multiple types per language
            # For single type filters or default, use original one_per_lang logic
            should_skip_duplicate = False
            if options.subtitle_type_filter in [SubtitleTypeFilter.FORCED_INCLUDED, SubtitleTypeFilter.SDH_INCLUDED, SubtitleTypeFilter.ALL_INCLUDED]:
                # Allow one track per type per language
                if type_key in selected_types_per_lang:
                    should_skip_duplicate = True
            else:
                # Original logic: one track per language
                if options.one_per_lang and language in selected_languages:
                    should_skip_duplicate = True

            if should_skip_duplicate:
                logger.debug('Skipping track %s:%s (%s) - already have this type/language', t.id, language, track_type)
                continue

            if not language:
                logger.debug('Skipping unknown language track %s in %s', t.id, self)
                continue

            # Use track type for numbering when we have mixed types
            if options.subtitle_type_filter in [SubtitleTypeFilter.FORCED_INCLUDED, SubtitleTypeFilter.SDH_INCLUDED, SubtitleTypeFilter.ALL_INCLUDED]:
                track_number = selected_types_per_lang.get(type_key, 0)
                selected_types_per_lang[type_key] = track_number + 1
            else:
                track_number = selected_languages.get(language, 0)
                selected_languages[language] = track_number + 1

            pgs = MkvPgs(self.media_path, t.id, language, track_number, options=options)
            # Store track type in the pgs object for later use in naming
            pgs.track_type = track_type
            # Also update the media_path to include the track type
            pgs.media_path = pgs.media_path.translate(subtitle_type=track_type)
            if pgs.matches(options):
                logger.debug('Selecting track %s:%s (%s) in %s', t.id, language, track_type, self)
                yield pgs
