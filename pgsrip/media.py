# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
import os
from abc import ABC, abstractmethod
from copy import copy
from typing import Set, Iterable, List, Optional, Tuple, Callable

from babelfish import Language
from pysrt import SubRipTime

from .options import Options
from .pgs import PgsReader, PaletteDefinitionSegment, ObjectDefinitionSegment, WindowDefinitionSegment, PgsImage

logger = logging.getLogger(__name__)


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


class PgsSubtitleItem:

    def __init__(self, index: int, language: Language,
                 pds: PaletteDefinitionSegment, ods: ObjectDefinitionSegment, wds: WindowDefinitionSegment):
        self.index = index
        self.start = SubRipTime.from_ordinal(ods.presentation_timestamp)
        self.end: Optional[SubRipTime] = None
        self.pds = pds
        self.ods = ods
        self.wds = wds
        self.language = language
        self.image = PgsImage(ods.img_data, pds.palettes)
        self.text: Optional[str] = None
        self.place: Optional[Tuple[int, int, int, int]] = None

    def __repr__(self):
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self):
        return f'{self.start} --> {self.end}: {self.language} [{self.shape}]'

    @property
    def height(self):
        return self.wds.height

    @property
    def width(self):
        return self.wds.width

    @property
    def h_center(self):
        shape = self.shape
        return shape[0] + (shape[2] - shape[0]) // 2

    @property
    def shape(self):
        height = self.height
        width = self.width
        y_offset = self.wds.y_offset
        x_offset = self.wds.x_offset

        return y_offset, x_offset, y_offset + height, x_offset + width

    def intersect(self, item: PgsSubtitleItem):
        shape = self.shape

        return shape[0] <= item.h_center <= shape[2]


class Pgs:

    def __init__(self, media_path: MediaPath, data_reader: Callable[[], bytes]):
        self.media_path = media_path
        self.data_reader = data_reader
        self._items: Optional[List[PgsSubtitleItem]] = None

    @property
    def language(self):
        return self.media_path.language

    @property
    def srt_path(self):
        return self.media_path.translate(number=0, extension='srt')

    @property
    def items(self):
        if self._items is None:
            data = self.data_reader()
            self._items = self.decode(data, self.media_path.language)
        return self._items

    @classmethod
    def decode(cls, data: bytes, language: Language):
        segments = PgsReader.read_segments(data)
        display_sets = PgsReader.create_display_sets(segments)
        index = 0
        items = []
        for display_set in display_sets:
            if not display_set.has_image:
                items[-1].end = SubRipTime.from_ordinal(display_set.wds[-1].presentation_timestamp)
                continue

            for (pds, ods, wds) in zip(display_set.pds, display_set.ods, display_set.wds):
                item = PgsSubtitleItem(index, language, pds, ods, wds)
                items.append(item)
                index += 1
        return items

    def deallocate(self):
        self._items = None

    def __repr__(self):
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self):
        return str(self.media_path)


class Media(ABC):

    def __init__(self, media_path: MediaPath, languages: Set[Language]):
        self.name = str(media_path)
        self.media_path = media_path
        self.languages = languages

    def __repr__(self):
        return f'<{self.__class__.__name__} [{self.media_path}]>'

    def __str__(self):
        return str(self.media_path)

    def matches(self, languages: Set[Language]):
        return not languages or self.languages.intersection(languages)

    @abstractmethod
    def get_pgs_medias(self, options: Options) -> Iterable[Pgs]:
        pass
