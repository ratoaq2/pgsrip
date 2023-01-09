# -*- coding: utf-8 -*-
import json
import logging
from subprocess import check_output
from tempfile import NamedTemporaryFile

from babelfish import Language

from trakit.api import trakit

from .media import Media, Pgs
from .media_path import MediaPath
from .options import Options

logger = logging.getLogger(__name__)


class MkvPgs(Pgs):

    @classmethod
    def read_data(cls, media_path: MediaPath, track_id: int):
        with NamedTemporaryFile() as temp_file:
            cmd = ['mkvextract', str(media_path), 'tracks', f'{track_id}:{temp_file.name}']
            check_output(cmd)
            return temp_file.read()

    def __init__(self, media_path: MediaPath, track_id: int, language: Language, number: int):
        super().__init__(media_path=media_path.translate(language=language, number=number),
                         data_reader=lambda: self.read_data(media_path=media_path, track_id=track_id))
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

    def __repr__(self):
        return f'<{self.__class__.__name__} [{str(self)}]>'

    def __str__(self):
        return f'{self.id}:{self.type}:{self.codec}:{self.language}:{self.enabled}:{self.forced}'


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
        selected_languages = {}
        for t in tracks:
            language = t.language
            if options.languages and language not in options.languages:
                logger.debug(f'Filtering out track {t.id}:{language} in {self}')
                continue

            if options.one_per_lang and language in selected_languages:
                logger.debug(f'Skipping track {t.id}:{language} in {self}')
                continue

            if not language:
                logger.debug(f'Skipping unknown language track {t.id} in {self}')
                continue

            pgs = MkvPgs(self.media_path, t.id, language, selected_languages.get(language, 0))
            if pgs.matches(options):
                logger.debug(f'Selecting track {t.id}:{language} in {self}')
                yield pgs
                selected_languages[language] = selected_languages.get(language, 0) + 1
