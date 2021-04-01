# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
import os
from abc import ABC, abstractmethod
from copy import copy
from datetime import datetime, timedelta
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


class PgsSubtitleItem:

    def __init__(self, index: int, media_path: MediaPath,
                 pds: PaletteDefinitionSegment, ods: ObjectDefinitionSegment, wds: WindowDefinitionSegment):
        self.index = index
        self.start = SubRipTime.from_ordinal(ods.presentation_timestamp)
        self.end: Optional[SubRipTime] = None
        self.pds = pds
        self.ods = ods
        self.wds = wds
        self.media_path = media_path
        self.image = PgsImage(ods.img_data, pds.palettes)
        self.text: Optional[str] = None
        self.place: Optional[Tuple[int, int, int, int]] = None

    def __repr__(self):
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self):
        return f'{self.media_path} [{self.start} --> {self.end or ""}]'

    @property
    def language(self):
        return self.media_path.language

    @property
    def height(self):
        return self.image.shape[0]

    @property
    def width(self):
        return self.image.shape[1]

    @property
    def h_center(self):
        shape = self.shape
        return shape[0] + (shape[2] - shape[0]) // 2

    @property
    def shape(self):
        height, width = self.height, self.width
        y_offset = self.wds.y_offset
        x_offset = self.wds.x_offset

        return y_offset, x_offset, y_offset + height, x_offset + width

    def validate(self):
        corruption = self.ods.check_corruption()
        if corruption:
            logger.warning(f'Corrupted {self!r}: {corruption}')
        if not self.end:
            logger.warning(f'Corrupted {self!r}: No end timestamp')
        elif self.end <= self.start:
            logger.warning(f'Corrupted {self!r}: End is before the start')

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
            self._items = self.decode(data, self.media_path)
        return self._items

    def matches(self, options: Options):
        if not self.srt_path.exists():
            return True

        if not options.overwrite:
            logger.debug(f'Skipping {self} since {self.srt_path} already exists')
            return False
        if options.srt_age and self.srt_path.m_age < options.srt_age:
            logger.debug(f'Skipping since {self.srt_path} is too new')
            return False

        return True

    @classmethod
    def decode(cls, data: bytes, media_path: MediaPath):
        segments = PgsReader.read_segments(data)
        display_sets = PgsReader.create_display_sets(segments)
        index = 0
        items = []
        for display_set in display_sets:
            if not display_set.has_image:
                items[-1].end = SubRipTime.from_ordinal(display_set.wds[-1].presentation_timestamp)
                continue

            for (pds, ods, wds) in zip(display_set.pds, display_set.ods, display_set.wds):
                item = PgsSubtitleItem(index, media_path, pds, ods, wds)
                if items and items[-1].end is None and items[-1].start + 5000 >= item.start:
                    items[-1].end = max(items[-1].start, item.start - 1)
                items.append(item)
                index += 1

        for item in items:
            item.validate()

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

    @property
    def age(self):
        if self.media_path.exists():
            return self.media_path.m_age

        return timedelta()

    def matches(self, options: Options):
        if options.age and self.age > options.age:
            return False

        if options.languages and not self.languages.intersection(options.languages):
            return False
        return True

    @abstractmethod
    def get_pgs_medias(self, options: Options) -> Iterable[Pgs]:
        pass
