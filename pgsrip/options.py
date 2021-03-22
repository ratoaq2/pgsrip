# -*- coding: utf-8 -*-
from datetime import timedelta
from typing import Set

from babelfish import Language
from cleanit import Config


class Options:

    def __init__(self, config_path: str = None, languages: Set[Language] = None, tags: Set[str] = None,
                 encoding: str = None, overwrite=False, one_per_lang=True, max_workers: int = None,
                 confidence=65, tesseract_width: int = None, age: timedelta = None, srt_age: timedelta = None):
        self.config = Config.from_path(config_path) if config_path else Config()
        self.languages = languages or set()
        self.tags = tags or {'default'}
        self.encoding = encoding
        self.overwrite = overwrite
        self.one_per_lang = one_per_lang
        self.max_workers = max_workers
        self.confidence = confidence
        self.tesseract_width = tesseract_width
        self.age = age
        self.srt_age = srt_age

    def __repr__(self):
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self):
        return (f'languages:{self.languages}, tags:{self.tags}, '
                f'overwrite:{self.overwrite}, one_per_lang:{self.one_per_lang}, '
                f'encoding:{self.encoding}, max_workers:{self.max_workers}, '
                f'confidence:{self.confidence}, tesseract_width:{self.tesseract_width}, '
                f'age:{self.age}, srt_age:{self.srt_age}')
