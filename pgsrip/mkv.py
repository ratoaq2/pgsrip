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
        properties = track.get('properties', {})
        self.id: int = track['id']
        self.name: typing.Optional[str] = properties.get('track_name')
        self.type: str = track['type']
        self.codec: str = track['codec']
        language_ietf = properties.get('language_ietf')
        language_alpha = properties.get('language')
        expected_language = Language.fromcleanit(language_ietf or language_alpha or 'und')
        options = {'expected_language': expected_language} if expected_language else {}
        guess = trakit(self.name, options) if self.name else {}
        self.language: typing.Optional[Language] = guess.get('language') or expected_language
        self.disabled = None if properties.get('enabled_track') else True
        self.default = properties.get('default_track') or None
        self.forced: typing.Optional[bool] = guess.get('forced_track')
        self.closed_caption: typing.Optional[bool] = guess.get('closed_caption')
        self.hearing_impaired: typing.Optional[bool] = guess.get('hearing_impaired')
        self.commentary: typing.Optional[bool] = guess.get('commentary')
        self.descriptive: typing.Optional[bool] = guess.get('descriptive')
        self.external: typing.Optional[bool] = guess.get('external')
        self.version: typing.Optional[str] = guess.get('version')

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def __repr__(self):
        return f'<{self.__class__.__name__} [{str(self)}]>'

    def __str__(self):
        return f'{self.to_dict()}'


class Mkv(Media):

    def __init__(self, path: str):
        metadata = json.loads(check_output(['mkvmerge', '-i', '-F', 'json', path]))
        tracks = [MkvTrack(t) for t in metadata.get('tracks', [])]
        super().__init__(MediaPath(path), languages={t.language for t in tracks})
        self.tracks = tracks

    def get_pgs_medias(self, options: Options):
        tracks = [t for t in self.tracks
                  if t.type == 'subtitles' and t.codec == 'HDMV PGS' and not t.disabled]
        tracks.sort(key=lambda x: x.forced or False)
        tracks.sort(key=lambda x: x.id)
        selected_languages: typing.Dict[Language, int] = {}
        for t in tracks:
            language = t.language
            if options.languages and language not in options.languages:
                logger.debug('Filtering out track %s:%s in %s', t.id, language, self)
                continue

            if options.one_per_lang and language in selected_languages:
                logger.debug('Skipping track %s:%s in %s', t.id, language, self)
                continue

            if not language:
                logger.debug('Skipping unknown language track %s in %s', t.id, self)
                continue

            pgs = MkvPgs(self.media_path, t.id, language, selected_languages.get(language, 0), options=options)
            if pgs.matches(options):
                logger.debug('Selecting track %s:%s in %s', t.id, language, self)
                yield pgs
                selected_languages[language] = selected_languages.get(language, 0) + 1
