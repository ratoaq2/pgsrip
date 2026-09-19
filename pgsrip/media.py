from __future__ import annotations

import json
import logging
import os
import shutil
import typing
from abc import ABC, abstractmethod
from datetime import timedelta
from types import TracebackType

from babelfish import Language
from pysrt import SubRipTime

from pgsrip.media_path import MediaPath
from pgsrip.options import Options
from pgsrip.pgs import DisplaySet, Palette, PgsImage, PgsReader
from pgsrip.utils import pairwise

logger = logging.getLogger(__name__)


class PgsSubtitleItem:
    def __init__(self, index: int, media_path: MediaPath, display_sets: list[DisplaySet]):
        self.index = index
        self.media_path = media_path
        timestamps = [ds.pcs.presentation_timestamp for ds in display_sets]
        self.start: SubRipTime | None = min((t for t in timestamps if t is not None), default=None)
        self.end: SubRipTime | None = max((t for t in timestamps if t is not None), default=None)
        self.image = PgsSubtitleItem.generate_image(display_sets)
        x_offsets = [ds.wds.x_offset for ds in display_sets if ds.wds.num_windows > 0]
        self.x_offset: int | None = min((x for x in x_offsets if x is not None), default=None)
        y_offsets = [ds.wds.y_offset for ds in display_sets if ds.wds.num_windows > 0]
        self.y_offset: int | None = min((y for y in y_offsets if y is not None), default=None)
        self.text: str | None = None
        self.place: tuple[int, int, int, int] | None = None

    @staticmethod
    def create_items(media_path: MediaPath, display_sets: typing.Iterable[DisplaySet]) -> list[PgsSubtitleItem]:
        current_sets: list[DisplaySet] = []
        index = 0
        candidates: list[PgsSubtitleItem] = []
        for ds in display_sets:
            if current_sets and ds.is_start():
                candidates.append(PgsSubtitleItem(index, media_path, current_sets))
                current_sets = []
                index += 1

            current_sets.append(ds)

        if current_sets:
            candidates.append(PgsSubtitleItem(index, media_path, current_sets))

        results = []
        for item, next_item in pairwise(candidates):
            if item.auto_fix(next_item=next_item):
                results.append(item)

        return results

    @staticmethod
    def generate_image(display_sets: typing.Iterable[DisplaySet]) -> PgsImage | None:
        for ds in display_sets:
            if not ds.pcs.is_start():
                continue

            palettes: list[Palette] = []
            for pds in ds.pds_segments:
                palettes += pds.palettes
            img_data = b''
            for ods in ds.ods_segments:
                img_data += ods.img_data

            return PgsImage(img_data, palettes)

        return None

    @property
    def language(self) -> Language:
        return self.media_path.language

    @property
    def height(self) -> int:
        assert self.image is not None
        return self.image.shape[0]

    @property
    def width(self) -> int:
        assert self.image is not None
        return self.image.shape[1]

    @property
    def h_center(self) -> int:
        shape = self.shape
        return shape[0] + (shape[2] - shape[0]) // 2

    @property
    def shape(self) -> tuple[int, int, int, int]:
        height, width = self.height, self.width
        y_offset, x_offset = self.y_offset, self.x_offset
        assert y_offset is not None
        assert x_offset is not None

        return y_offset, x_offset, y_offset + height, x_offset + width

    def auto_fix(self, next_item: PgsSubtitleItem | None) -> bool:
        valid = True
        if self.image is None:
            logger.warning('Corrupted %r: No Image', self)
            valid = False
        if self.y_offset is None:
            logger.warning('Corrupted %r: No y_offset', self)
            valid = False
        if self.x_offset is None:
            logger.warning('Corrupted %r: No x_offset', self)
            valid = False
        if self.start is None:
            logger.warning('Corrupted %r: No Start timestamp', self)
            valid = False
        elif not self.end or self.end <= self.start:
            if next_item and next_item.start and self.start + 10000 >= next_item.start:
                self.end = max(self.start + 1, next_item.start - 1)
                logger.info('Fix applied for %r: Subtitle end timestamp was fixed', self)
            else:
                logger.warning('Corrupted %r: Subtitle with corrupted end timestamp', self)
                valid = False

        return valid

    def intersect(self, item: PgsSubtitleItem) -> bool:
        shape = self.shape

        return shape[0] <= item.h_center <= shape[2]

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self) -> str:
        return f'{self.media_path} [{self.start} --> {self.end or ""}]'


class Pgs:
    def __init__(
        self, media_path: MediaPath, options: Options, data_reader: typing.Callable[[], bytes], temp_folder: str
    ):
        self.media_path = media_path
        self.options = options
        self.data_reader = data_reader
        self.temp_folder = temp_folder
        self._items: list[PgsSubtitleItem] | None = None

    @property
    def language(self) -> Language:
        return self.media_path.language

    @property
    def srt_path(self) -> MediaPath:
        return self.media_path.translate(number=0, extension='srt')

    @property
    def items(self) -> list[PgsSubtitleItem]:
        if self._items is None:
            data = self.data_reader()
            self._items = self.decode(data, self.media_path)
        return self._items

    def matches(self, options: Options) -> bool:
        if not self.srt_path.exists():
            return True

        if not options.overwrite:
            logger.debug('Skipping %s since %s already exists', self, self.srt_path)
            return False
        if options.srt_age and self.srt_path.m_age < options.srt_age:
            logger.debug('Skipping since %s is too new', self.srt_path)
            return False

        return True

    def decode(self, data: bytes, media_path: MediaPath) -> list[PgsSubtitleItem]:
        display_sets = list(PgsReader.decode(data, media_path))
        logger.info(f'Decoding {media_path}')

        if self.options.keep_temp_files:
            self.dump_display_sets(display_sets)

        return PgsSubtitleItem.create_items(media_path, display_sets)

    def dump_display_sets(self, display_sets: list[DisplaySet]) -> None:
        new_line = '\n'
        with open(os.path.join(self.temp_folder, 'display-sets.txt'), mode='w', encoding='utf8') as f:
            f.write(f'{new_line.join([str(ds) for ds in display_sets])}')
        with open(os.path.join(self.temp_folder, 'display-sets.json'), mode='w', encoding='utf8') as f:
            json.dump([ds.to_json() for ds in display_sets], f, indent=2, ensure_ascii=False, default=lambda x: str(x))

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self) -> str:
        return str(self.media_path)

    def __enter__(self) -> Pgs:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self._items = None
        if self.options.keep_temp_files:
            logger.info('Keeping temporary files in %s', self.temp_folder)
        else:
            logger.debug('Removing temporary files in %s', self.temp_folder)
            shutil.rmtree(self.temp_folder)


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

    def matches(self, options: Options) -> bool:
        if options.age and self.age > options.age:
            return False

        if options.languages and not self.languages.intersection(options.languages):
            return False

        return True

    @abstractmethod
    def get_pgs_medias(self, options: Options) -> typing.Iterable[Pgs]:
        pass
