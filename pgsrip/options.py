import typing
from datetime import timedelta

from babelfish import Language

from cleanit import Config


class Options:

    def __init__(self,
                 config_path: typing.Optional[str] = None,
                 languages: typing.Optional[typing.Set[Language]] = None,
                 tags: typing.Optional[typing.Set[str]] = None,
                 encoding: typing.Optional[str] = None,
                 overwrite=False,
                 one_per_lang=True,
                 keep_temp_files=False,
                 max_workers: typing.Optional[int] = None,
                 confidence=65,
                 tesseract_width: typing.Optional[int] = None,
                 age: typing.Optional[timedelta] = None,
                 srt_age: typing.Optional[timedelta] = None):
        self.config = Config.from_path(config_path) if config_path else Config()
        self.languages = languages or set()
        self.tags = tags or {'default'}
        self.encoding = encoding
        self.overwrite = overwrite
        self.one_per_lang = one_per_lang
        self.keep_temp_files = keep_temp_files
        self.max_workers = max_workers
        self.confidence = confidence
        self.tesseract_width = tesseract_width
        self.age = age
        self.srt_age = srt_age

    def __repr__(self):
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self):
        return (f'languages:{self.languages}, '
                f'tags:{self.tags}, '
                f'encoding:{self.encoding}, '
                f'overwrite:{self.overwrite}, '
                f'one_per_lang:{self.one_per_lang}, '
                f'keep_temp_files:{self.keep_temp_files}, '
                f'max_workers:{self.max_workers}, '
                f'confidence:{self.confidence}, '
                f'tesseract_width:{self.tesseract_width}, '
                f'age:{self.age}, '
                f'srt_age:{self.srt_age}')
