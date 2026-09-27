"""OCR with tesseract: many subtitle bitmaps in a few composite images (see docs/ocr_batching.md)."""

from __future__ import annotations

import enum
import json
import logging
import os
import shutil
import typing
from concurrent.futures import ThreadPoolExecutor

import click
import cv2
import numpy as np
import numpy.typing as npt
import pytesseract as tess

from pgsrip.diagnostics import Check
from pgsrip.ripper import OcrEngine, PluginOption
from pgsrip.tessdata import (
    REPOSITORIES,
    Tessdata,
    TessdataError,
    get_config_arg,
    get_required_codes,
    get_tesseract_code,
    tessdata_env,
)
from pgsrip.tsv import TsvData, TsvDataItem
from pgsrip.utils import default_workers

if typing.TYPE_CHECKING:
    from babelfish import Language

    from pgsrip.media import Pgs, PgsSubtitleItem

logger = logging.getLogger(__name__)

#: tesseract refuses any image dimension above INT16_MAX; stay under it with room for the border.
MAX_TESS_DIMENSION = 31 * 1024
#: confidence of the first pass. The retry passes go lower, down to 0.
DEFAULT_CONFIDENCE = 65
#: a cue with a word below this confidence is doubtful: the next engine of the chain reads it again.
DEFAULT_THRESHOLD = 80
TESSERACT_HINT = 'Install tesseract-ocr and make sure that it is in the PATH'
MAX_REPORTED_LANGUAGES = 20


@enum.unique
class TesseractEngineMode(enum.Enum):
    LEGACY = 0
    NEURAL = 1
    LEGACY_AND_NEURAL = 2
    DEFAULT_AVAILABLE = 3


@enum.unique
class TesseractPageSegmentationMode(enum.Enum):
    OSD_ONLY = 0
    AUTOMATIC_PAGE_SEGMENTATION_WITH_OSD = 1
    AUTOMATIC_PAGE_SEGMENTATION_WITHOUT_OSD_OR_OCR = 2
    FULLY_AUTOMATIC_PAGE_SEGMENTATION_WITHOUT_OSD = 3
    SINGLE_COLUMN_OF_TEXT_OF_VARIABLE_SIZES = 4
    SINGLE_UNIFORM_BLOCK_OF_VERTICALLY_ALIGNED_TEXT = 5
    SINGLE_UNIFORM_BLOCK_OF_TEXT = 6
    SINGLE_TEXT_LINE = 7
    SINGLE_WORD = 8
    SINGLE_WORD_IN_CIRCLE = 9
    SINGLE_CHARACTER = 10
    SPARSE_TEXT = 11
    SPARSE_TEXT_WITH_OSD = 12
    RAW_LINE = 13


class ImageArea:
    def __init__(self, items: list[PgsSubtitleItem], gap: tuple[int, int]):
        self.gap = gap
        self.width = sum([(item.shape[3] - item.shape[1]) for item in items]) + (len(items) - 1) * gap[1]
        self.shape = (
            min([item.shape[0] for item in items]),
            items[0].shape[1],
            max([item.shape[2] for item in items]),
            min([item.shape[1] for item in items]) + self.width,
        )
        self.items = items

    def __str__(self) -> str:
        return str(self.shape)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'

    @property
    def height(self) -> int:
        return self.shape[2] - self.shape[0]

    def create_area_image(self, start: tuple[int, int]) -> npt.NDArray[np.uint8]:
        area_image = np.full((self.height, self.width), 255, dtype=np.uint8)

        current_width = 0
        for item in self.items:
            h_start, w_start, h_end, w_end = self.get_shape(item, current_width=current_width)
            item.place = (start[0] + h_start, start[1] + w_start, start[0] + h_end, start[1] + w_end)
            area_image[h_start:h_end, w_start:w_end] = item.bitmap
            current_width += item.width + self.gap[1]

        return area_image

    def get_shape(
        self, item: PgsSubtitleItem, current_width: int = 0, full_shape: bool = False
    ) -> tuple[int, int, int, int]:
        start_y = 0
        start_x = current_width
        h_start = start_y + ((item.shape[0] - self.shape[0]) if not full_shape else 0)
        w_start = start_x
        h_end = h_start + (item.height if not full_shape else self.height)
        w_end = w_start + (item.width if not full_shape else self.width)

        return h_start, w_start, h_end, w_end


class FullImage:
    border = 100

    def __init__(self, areas: list[ImageArea], gap: tuple[int, int]):
        border = self.border
        total_height = sum([area.height for area in areas]) + (len(areas) - 1) * gap[0] + 2 * border
        total_width = max([area.width for area in areas]) + 2 * border
        full_image = np.full((total_height, total_width), 255, dtype=np.uint8)
        h_start = border
        w_start = border
        for area in areas:
            h_end = h_start + area.height
            w_end = w_start + area.width
            full_image[h_start:h_end, w_start:w_end] = area.create_area_image((h_start, w_start))
            h_start = h_end + gap[0]

        self.data = full_image
        self.items = [item for area in areas for item in area.items]

    @classmethod
    def from_items(
        cls, items: list[PgsSubtitleItem], gap: tuple[int, int], max_width: int, max_height: int, parts: int = 1
    ) -> list[FullImage]:
        """Split items into at most `parts` composites of about the same height, to OCR them in parallel.

        No composite is taller than max_height, so a long track can give more than `parts` composites.
        An area taller than max_height on its own still gets a composite of its own.
        """
        areas: list[ImageArea] = []
        remaining = list(items)
        remaining.sort(key=lambda x: x.height)
        while len(remaining) > 0:
            first_item = remaining.pop(0)
            area_items = [first_item] + [item for item in remaining if item.intersect(first_item)]
            remaining = [item for item in remaining if not item.intersect(first_item)]
            current_items: list[PgsSubtitleItem] = []
            current_width = 0
            for area_item in area_items:
                current_width += area_item.width + gap[1]
                if current_width > max_width:
                    areas.append(ImageArea(current_items, gap))
                    current_width = area_item.width
                    current_items = [area_item]
                else:
                    current_items.append(area_item)

            if len(current_items) > 0:
                areas.append(ImageArea(current_items, gap))

        composites: list[FullImage] = []
        # cut the stacked areas in `parts` slices of the same height: each area goes to the slice of its middle.
        share = max(1.0, (sum(area.height for area in areas) + (len(areas) - 1) * gap[0]) / parts)
        group: list[ImageArea] = []
        group_part = 0
        height = 2 * cls.border
        top = 0
        for area in areas:
            part = int((top + area.height / 2) // share)
            top += area.height + gap[0]
            if group and (part != group_part or height + gap[0] + area.height > max_height):
                composites.append(cls(group, gap))
                group = []
                height = 2 * cls.border

            height += (gap[0] if group else 0) + area.height
            group.append(area)
            group_part = part

        if group:
            composites.append(cls(group, gap))

        return composites

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self) -> str:
        return f'{self.data.shape}]'


def check_tesseract() -> Check:
    path = shutil.which('tesseract')
    try:
        version = tess.get_tesseract_version()
    except Exception as e:
        logger.debug('Cannot get the tesseract version: <%s> %s', type(e).__name__, e)
        return Check('tesseract', f'not found: <{type(e).__name__}> {e}', ok=False, hint=TESSERACT_HINT)

    return Check('tesseract', f'{version} ({path or "unknown path"})')


def check_languages() -> Check:
    try:
        codes = sorted(tess.get_languages())
    except Exception as e:
        logger.debug('Cannot list the tesseract languages: <%s> %s', type(e).__name__, e)
        return Check('tesseract languages', f'unknown: <{type(e).__name__}> {e}', ok=False, hint=TESSERACT_HINT)

    if not codes:
        return Check('tesseract languages', 'none installed, pgsrip downloads the ones it needs')

    listed = codes[:MAX_REPORTED_LANGUAGES]
    remaining = len(codes) - len(listed)

    return Check('tesseract languages', f'{", ".join(listed)}{f" and {remaining} more" if remaining else ""}')


def check_tessdata(tessdata: Tessdata) -> list[Check]:
    checks = [
        Check('tessdata directory', str(tessdata.directory or 'not set')),
        Check('TESSDATA_PREFIX', os.getenv('TESSDATA_PREFIX') or 'not set'),
        Check('tessdata repository', tessdata.repository),
        Check('tessdata download', 'enabled' if tessdata.download else 'disabled'),
    ]
    try:
        checks.append(Check('tessdata download directory', tessdata.target_dir))
    except TessdataError as e:
        checks.append(
            Check('tessdata download directory', str(e), ok=False, hint='Set --tesseract-dir to a writable directory')
        )

    return checks


class TesseractEngine(OcrEngine):
    """The first engine of auto. One engine reads all the tracks of a rip."""

    options: typing.ClassVar[tuple[PluginOption, ...]] = (
        PluginOption(
            'threshold',
            click.IntRange(0, 100),
            help=f'A cue with a word below this tesseract confidence goes to the next --engine. '
            f'Default: {DEFAULT_THRESHOLD}.',
        ),
        PluginOption(
            'dir',
            click.Path(),
            help='Directory where tesseract data is stored. Defaults to TESSDATA_PREFIX or a user cache directory.',
        ),
        PluginOption(
            'repository', click.Choice(sorted(REPOSITORIES)), help='Repository to download missing tesseract data from.'
        ),
        PluginOption(
            'download',
            flag=True,
            default=True,
            help='Download missing tesseract data. With --no-tesseract-download, use only the installed data.',
        ),
    )

    @classmethod
    def from_settings(cls, settings: dict[str, typing.Any], workers: int | None) -> TesseractEngine:
        return cls(workers=workers, tessdata=cls.tessdata_from(settings), threshold=settings['threshold'])

    @classmethod
    def check(cls, settings: dict[str, typing.Any]) -> list[Check]:
        """The tesseract program, its languages, and the tesseract data, for `pgsrip doctor`."""
        return [check_tesseract(), check_languages(), *check_tessdata(cls.tessdata_from(settings))]

    @staticmethod
    def tessdata_from(settings: dict[str, typing.Any]) -> Tessdata:
        return Tessdata(directory=settings['dir'], repository=settings['repository'], download=settings['download'])

    def __init__(
        self,
        confidence: int | None = None,
        width: int | None = None,
        oem: TesseractEngineMode | None = None,
        psm: TesseractPageSegmentationMode | None = None,
        workers: int | None = None,
        tessdata: Tessdata | None = None,
        threshold: int | None = None,
    ):
        self.confidence = min(max(confidence or DEFAULT_CONFIDENCE, 0), 100)
        self.threshold = min(max(DEFAULT_THRESHOLD if threshold is None else threshold, 0), 100)
        self.max_width = min(max(width or MAX_TESS_DIMENSION, 10 * 1024), MAX_TESS_DIMENSION)
        self.workers = workers or default_workers()
        self.oem = oem or TesseractEngineMode.NEURAL
        self.psm = psm or TesseractPageSegmentationMode.SINGLE_UNIFORM_BLOCK_OF_TEXT
        self.tessdata = tessdata or Tessdata()
        #: the tesseract data that `prepare` could not download
        self.failed_codes: set[str] = set()

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self) -> str:
        return (
            f'confidence:{self.confidence}, '
            f'threshold:{self.threshold}, '
            f'max_width:{self.max_width}, '
            f'workers:{self.workers}, '
            f'oem:{self.oem}, '
            f'psm:{self.psm}, '
            f'tessdata:[{self.tessdata}]'
        )

    def prepare(
        self, languages: typing.Iterable[Language], reporter: typing.Callable[[str], None] | None = None
    ) -> None:
        """Download the tesseract data of every language, before any ripping starts.

        A failed download does not stop the rip: the tracks of the other languages can still be ripped.
        """

        def report(code: str) -> None:
            if reporter:
                reporter(f'Downloading tesseract data for {code}...')

        # one code at a time: a failed download does not stop the downloads of the other codes
        for code in sorted(get_required_codes(languages, self.psm.value)):
            try:
                self.tessdata.ensure({code}, reporter=report)
            except TessdataError as e:
                self.failed_codes.add(code)
                if reporter:
                    reporter(str(e))

    def supports(self, language: Language) -> bool:
        """True when tesseract runs, and has or can get the data of the language."""
        return all(
            code not in self.failed_codes and self.tessdata.available(code)
            for code in get_required_codes([language], self.psm.value)
        )

    def recognize(self, pgs: Pgs, items: list[PgsSubtitleItem]) -> None:
        max_height = max([item.height for item in pgs.items]) // 2
        gap = (max_height // 2 + 30, max_height // 2 + 100)
        tessdata_dir = self.tessdata.ensure(get_required_codes([pgs.language], self.psm.value))
        confidence, max_width = self.confidence, self.max_width
        previous_size = len(items)
        while previous_size > 0:
            items = self.process(pgs, items, confidence, max_width, gap, tessdata_dir)
            if not items:
                break

            current_size = len(items)
            if current_size < 20:
                max_width = min(sum([item.width + gap[1] for item in items]), self.max_width)
                confidence = 0
                self.process(pgs, items, confidence, max_width, gap, tessdata_dir)
                break
            elif current_size > previous_size * 0.8:
                last_pass = (confidence, max_width)
                max_width = min(sum([item.width + gap[1] for item in items]), self.max_width) // 2
                confidence = max(0, confidence - 5)
                # the same pass on the same items reads nothing new: the remaining items stay unread
                if (confidence, max_width) == last_pass:
                    break
            previous_size = current_size

    def process(
        self,
        pgs: Pgs,
        items: list[PgsSubtitleItem],
        confidence: int,
        max_width: int,
        gap: tuple[int, int],
        tessdata_dir: str | None,
    ) -> list[PgsSubtitleItem]:
        """Run one OCR pass and return the items that it could not read."""
        oem, psm = self.oem, self.psm
        config: dict[str, typing.Any] = {
            'output_type': tess.Output.DICT,
            'config': f'{get_config_arg(tessdata_dir)} --psm {psm.value} --oem {oem.value}'.strip(),
        }

        language_code = get_tesseract_code(pgs.language)
        if language_code:
            config.update({'lang': language_code})

        # one tesseract process per composite, in parallel: one process with OpenMP threads uses about one core.
        os.environ['OMP_THREAD_LIMIT'] = '1'

        composites = FullImage.from_items(items, gap, max_width, MAX_TESS_DIMENSION, self.workers)
        prefix = f'{os.path.basename(str(pgs.media_path.translate(extension="srt")))}-{len(items)}'
        if pgs.options.keep_temp_files:
            for index, full_image in enumerate(composites):
                png_file = os.path.join(pgs.temp_folder, f'{prefix}-{index}-psm{psm.value}-{oem.name}-{confidence}.png')
                logger.debug('Writing temporary png file %s', png_file)
                cv2.imwrite(png_file, full_image.data)

        with tessdata_env(tessdata_dir), ThreadPoolExecutor(self.workers) as pool:
            results = list(pool.map(lambda image: tess.image_to_data(image.data, **config), composites))

        remaining: list[PgsSubtitleItem] = []
        for index, (full_image, result) in enumerate(zip(composites, results, strict=True)):
            data = TsvData(result, confidence=confidence)
            if pgs.options.keep_temp_files:
                results_file = os.path.join(pgs.temp_folder, f'{prefix}-{index}-{confidence}.json')
                logger.debug('Writing temporary results file %s', results_file)
                with open(results_file, mode='w', encoding='utf8') as f:
                    json.dump([i.__dict__ for i in data.items], f, indent=2, ensure_ascii=False)

            # item.place is relative to the composite the item was drawn in: match it against that one only.
            for item in full_image.items:
                if self.accept(data, item, confidence) is None:
                    remaining.append(item)

        return remaining

    def accept(self, data: TsvData, item: PgsSubtitleItem, confidence: int) -> str | None:
        rows = data.select(item.place) if item.place else []
        lines: list[str] = []
        words: list[str] = []
        last_row: TsvDataItem | None = None
        for row in rows:
            if row.conf < confidence:
                if not data.has_word(row.text):
                    return None

            if (
                last_row is not None
                and (
                    last_row.page_num < row.page_num
                    or last_row.block_num < row.block_num
                    or last_row.par_num < row.par_num
                    or last_row.line_num < row.line_num
                )
                and len(words) > 0
            ):
                lines.append(' '.join(words))
                words.clear()
            words.append(row.text)
            last_row = row

        if len(words) > 0:
            lines.append(' '.join(words))
            words.clear()

        item.text = '\n'.join(lines).strip()
        lowest = min((row.conf for row in rows), default=100)
        item.doubtful = lowest < self.threshold
        item.confidence = lowest / 100
        return item.text
