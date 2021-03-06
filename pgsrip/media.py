# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Set, Iterable, List, Optional, Tuple, Callable

from babelfish import Language
from pysrt import SubRipTime

from .media_path import MediaPath
from .options import Options
from .pgs import PgsReader, PaletteDefinitionSegment, ObjectDefinitionSegment, WindowDefinitionSegment, PgsImage

logger = logging.getLogger(__name__)


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
        display_sets = PgsReader.decode(data, media_path)
        index = 0
        items = []
        for display_set in display_sets:
            if items and not display_set.has_image and display_set.wds:
                items[-1].end = SubRipTime.from_ordinal(display_set.wds[-1].presentation_timestamp)
                continue

            for (pds, ods, wds) in zip(display_set.pds, display_set.ods, display_set.wds):
                item = PgsSubtitleItem(index, media_path, pds, ods, wds)
                if items and items[-1].end is None and items[-1].start + 10000 >= item.start:
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
