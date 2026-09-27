from __future__ import annotations

import typing
from abc import ABC, abstractmethod
from datetime import timedelta

from babelfish import Language

from pgsrip.media import Pgs
from pgsrip.media_path import MediaPath
from pgsrip.options import Options


class Media(ABC):
    def __init__(self, media_path: MediaPath, languages: set[Language]):
        self.name = str(media_path)
        self.media_path = media_path
        self.languages = languages

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

    @abstractmethod
    def get_pgs_medias(self, options: Options) -> typing.Iterable[Pgs]:
        pass
