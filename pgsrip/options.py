from datetime import timedelta

from babelfish import Language
from cleanit import Config

from pgsrip.ripper import OcrEngine
from pgsrip.tesseract import TesseractEngine


class Options:
    def __init__(
        self,
        cleanit_config: str | None = None,
        languages: set[Language] | None = None,
        tags: set[str] | None = None,
        encoding: str | None = None,
        overwrite: bool = False,
        one_per_lang: bool = True,
        one_per_language: bool = False,
        include_flags: frozenset[str] = frozenset(),
        exclude_flags: frozenset[str] = frozenset(),
        keep_temp_files: bool = False,
        engines: list[OcrEngine] | None = None,
        age: timedelta | None = None,
        srt_age: timedelta | None = None,
    ):
        self.cleanit_config = Config.from_path(cleanit_config) if cleanit_config else Config()
        self.languages = languages or set()
        self.tags = tags or {'default'}
        self.encoding = encoding
        self.overwrite = overwrite
        self.one_per_lang = one_per_lang
        self.one_per_language = one_per_language
        self.include_flags = include_flags
        self.exclude_flags = exclude_flags
        self.keep_temp_files = keep_temp_files
        # a chain: each engine reads the items that the engines before it left unread
        self.engines = engines or [TesseractEngine()]
        self.age = age
        self.srt_age = srt_age

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self) -> str:
        return (
            f'languages:{self.languages}, '
            f'tags:{self.tags}, '
            f'encoding:{self.encoding}, '
            f'overwrite:{self.overwrite}, '
            f'one_per_lang:{self.one_per_lang}, '
            f'one_per_language:{self.one_per_language}, '
            f'include_flags:{self.include_flags}, '
            f'exclude_flags:{self.exclude_flags}, '
            f'keep_temp_files:{self.keep_temp_files}, '
            f'engines:{self.engines!r}, '
            f'age:{self.age}, '
            f'srt_age:{self.srt_age}'
        )
