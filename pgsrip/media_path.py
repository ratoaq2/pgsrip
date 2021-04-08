import os
from copy import copy
from datetime import datetime

from babelfish import Language


class MediaPath:

    def __init__(self, path: str):
        file_part, extension = os.path.splitext(path)
        base_path, code = os.path.splitext(file_part)
        self.number = 0
        self.language = Language.fromcleanit(code[1:] if code else 'und')
        self.extension = extension[1:] if extension else None
        self.base_path = base_path if self.language else file_part

    def __repr__(self):
        return f'<{self.__class__.__name__} [{str(self)}]>'

    def __str__(self):
        return f'{self.base_path}' \
               f'{f"-{self.number}" if self.number else ""}' \
               f'{f".{str(self.language)}" if self.language else ""}' \
               f'{f".{self.extension}" if self.extension else ""}'

    @property
    def m_age(self):
        return datetime.utcnow() - datetime.utcfromtimestamp(os.path.getmtime(str(self)))

    def get_data(self):
        with open(str(self), 'rb') as f:
            return f.read()

    def exists(self):
        return os.path.exists(str(self))

    def translate(self, language: Language = None, extension: str = None, number: int = None):
        media_path = copy(self)
        if number is not None:
            media_path.number = number
        if language is not None:
            media_path.language = language
        if extension is not None:
            media_path.extension = extension
        return media_path