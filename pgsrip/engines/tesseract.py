"""OCR with tesseract: many subtitle bitmaps in a few composite images (see docs/ocr_batching.md)."""

from __future__ import annotations

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
from pgsrip.engines.base import OcrEngine, OcrEngineFactory, Reading
from pgsrip.engines.tessdata import (
    DEFAULT_REPOSITORY,
    REPOSITORIES,
    Tessdata,
    TessdataError,
    config_arg,
    required_codes,
    tesseract_code,
    tesseract_env,
)
from pgsrip.engines.tsv import TsvResult, TsvWord
from pgsrip.formats.pgs import Box
from pgsrip.plugin import PluginOption
from pgsrip.utils import default_workers

if typing.TYPE_CHECKING:
    from babelfish import Language

    from pgsrip.formats.pgs import Item

logger = logging.getLogger(__name__)

#: tesseract refuses any image dimension above INT16_MAX; stay under it with room for the border.
MAX_TESS_DIMENSION = 31 * 1024
#: the smallest value of --tesseract-width
MIN_WIDTH = 10 * 1024
#: white margin around the rows of a composite
BORDER = 100
#: the gaps between 2 rows and between 2 items of a row, in addition to a quarter of the tallest item
ROW_GAP = 30
ITEM_GAP = 100
#: confidence of the first pass. The retry passes go lower, down to 0.
DEFAULT_CONFIDENCE = 65
#: the confidence of each retry pass is this much lower than the pass before it
CONFIDENCE_STEP = 5
#: a pass that leaves more than this share of its items unread: the next pass uses smaller composites
SLOW_PASS = 0.8
#: with fewer unread items, one last pass reads them with the confidence 0
LAST_PASS_SIZE = 20
#: the LSTM engine. 0 and 2 need the legacy models, which tessdata_best does not have.
OEM = 1
#: one uniform block of text: one composite is one block. The other modes break the batching.
PSM = 6
#: a cue with a word below this confidence is doubtful: the next engine of the chain reads it again.
DEFAULT_THRESHOLD = 80
TESSERACT_HINT = 'Install tesseract-ocr and make sure that it is in the PATH'
MAX_REPORTED_LANGUAGES = 20


def same_row(item: Item, other: Item) -> bool:
    """True when the vertical middle of the other item is inside the rows of the item."""
    box, other_box = item.box, other.box
    return box.top <= other_box.top + (other_box.bottom - other_box.top) // 2 <= box.bottom


class Gap(typing.NamedTuple):
    """The space in pixels between 2 rows of a composite, and between 2 items of a row."""

    row: int
    item: int


class Row:
    """Items side by side, with the same vertical middle."""

    def __init__(self, items: list[Item], item_gap: int):
        self.item_gap = item_gap
        self.width = sum(item.box.right - item.box.left for item in items) + (len(items) - 1) * item_gap
        self.box = Box(
            min(item.box.top for item in items),
            items[0].box.left,
            max(item.box.bottom for item in items),
            min(item.box.left for item in items) + self.width,
        )
        self.items = items

    def __str__(self) -> str:
        return str(self.box)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'

    @property
    def height(self) -> int:
        return self.box.bottom - self.box.top

    def draw(self, start: tuple[int, int]) -> tuple[npt.NDArray[np.uint8], list[tuple[Item, Box]]]:
        """The image of the row, and the box of each item in the composite that starts the row at start."""
        image = np.full((self.height, self.width), 255, dtype=np.uint8)

        placed = []
        current_width = 0
        for item in self.items:
            box = self.item_box(item, current_width)
            placed.append(
                (item, Box(start[0] + box.top, start[1] + box.left, start[0] + box.bottom, start[1] + box.right))
            )
            image[box.top : box.bottom, box.left : box.right] = item.bitmap
            current_width += item.width + self.item_gap

        return image, placed

    def item_box(self, item: Item, current_width: int) -> Box:
        """The box of the item in the image of the row."""
        top = item.box.top - self.box.top
        return Box(top, current_width, top + item.height, current_width + item.width)


class Composite:
    """Rows one under the other in one image: one tesseract call."""

    def __init__(self, rows: list[Row], row_gap: int):
        border = BORDER
        total_height = sum(row.height for row in rows) + (len(rows) - 1) * row_gap + 2 * border
        total_width = max(row.width for row in rows) + 2 * border
        image = np.full((total_height, total_width), 255, dtype=np.uint8)
        #: each item, and its box in this composite
        self.placed: list[tuple[Item, Box]] = []
        h_start = border
        w_start = border
        for row in rows:
            h_end = h_start + row.height
            w_end = w_start + row.width
            image[h_start:h_end, w_start:w_end], placed = row.draw((h_start, w_start))
            self.placed.extend(placed)
            h_start = h_end + row_gap

        self.image = image

    @classmethod
    def from_items(
        cls, items: list[Item], gap: Gap, max_width: int, max_height: int, parts: int = 1
    ) -> list[Composite]:
        """Split items into at most `parts` composites of about the same height, to OCR them in parallel.

        No composite is taller than max_height, so a long track can give more than `parts` composites.
        A row taller than max_height on its own still gets a composite of its own.
        """
        rows: list[Row] = []
        remaining = list(items)
        remaining.sort(key=lambda x: x.height)
        while len(remaining) > 0:
            first_item = remaining.pop(0)
            row_items = [first_item] + [item for item in remaining if same_row(item, first_item)]
            remaining = [item for item in remaining if not same_row(item, first_item)]
            current_items: list[Item] = []
            current_width = 0
            for area_item in row_items:
                current_width += area_item.width + gap.item
                # an item wider than max_width gets a row of its own
                if current_width > max_width and current_items:
                    rows.append(Row(current_items, gap.item))
                    current_width = area_item.width
                    current_items = [area_item]
                else:
                    current_items.append(area_item)

            if len(current_items) > 0:
                rows.append(Row(current_items, gap.item))

        composites: list[Composite] = []
        # cut the stacked rows in `parts` slices of the same height: each row goes to the slice of its middle.
        share = max(1.0, (sum(row.height for row in rows) + (len(rows) - 1) * gap.row) / parts)
        group: list[Row] = []
        group_part = 0
        height = 2 * BORDER
        top = 0
        for row in rows:
            part = int((top + row.height / 2) // share)
            top += row.height + gap.row
            if group and (part != group_part or height + gap.row + row.height > max_height):
                composites.append(cls(group, gap.row))
                group = []
                height = 2 * BORDER

            height += (gap.row if group else 0) + row.height
            group.append(row)
            group_part = part

        if group:
            composites.append(cls(group, gap.row))

        return composites

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self) -> str:
        return str(self.image.shape)


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
        Check('tessdata directory', str(tessdata.data_dir or 'not set')),
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


class TesseractEngine(OcrEngine, OcrEngineFactory):
    """The first engine of auto. One engine reads all the tracks of a rip."""

    options: typing.ClassVar[tuple[PluginOption, ...]] = (
        PluginOption(
            'threshold',
            click.IntRange(0, 100),
            default=DEFAULT_THRESHOLD,
            help='A cue with a word below this tesseract confidence goes to the next --engine.',
        ),
        PluginOption(
            'confidence',
            click.IntRange(0, 100),
            default=DEFAULT_CONFIDENCE,
            help='Tesseract confidence of the words that the first pass accepts. The next passes go lower.',
        ),
        PluginOption(
            'width',
            click.IntRange(MIN_WIDTH, MAX_TESS_DIMENSION),
            default=MAX_TESS_DIMENSION,
            help='Maximum width in pixels of the images that go to tesseract.',
        ),
        PluginOption(
            'workers',
            click.IntRange(1, 50),
            default=None,
            help='Number of tesseract processes that run in parallel. Default: -w.',
        ),
        PluginOption(
            'dir',
            click.Path(),
            default=None,
            envvar='PGSRIP_TESSDATA_DIR',
            help='Directory where tesseract data is stored. Default: TESSDATA_PREFIX, else a user cache directory.',
        ),
        PluginOption(
            'repository',
            click.Choice(sorted(REPOSITORIES)),
            default=DEFAULT_REPOSITORY,
            envvar='PGSRIP_TESSDATA_REPO',
            help='Repository to download missing tesseract data from.',
        ),
        PluginOption(
            'download',
            flag=True,
            default=True,
            help='Download missing tesseract data. With --no-tesseract-download, use only the installed data.',
        ),
    )

    @classmethod
    def from_settings(cls, settings: dict[str, typing.Any]) -> TesseractEngine:
        return cls(
            confidence=settings['confidence'],
            width=settings['width'],
            workers=settings['workers'],
            tessdata=cls.tessdata_from(settings),
            threshold=settings['threshold'],
        )

    @classmethod
    def check(cls, settings: dict[str, typing.Any]) -> list[Check]:
        """The tesseract program, its languages, and the tesseract data, for `pgsrip doctor`."""
        return [check_tesseract(), check_languages(), *check_tessdata(cls.tessdata_from(settings))]

    @staticmethod
    def tessdata_from(settings: dict[str, typing.Any]) -> Tessdata:
        return Tessdata(data_dir=settings['dir'], repository=settings['repository'], download=settings['download'])

    def __init__(
        self,
        confidence: int = DEFAULT_CONFIDENCE,
        width: int = MAX_TESS_DIMENSION,
        workers: int | None = None,
        tessdata: Tessdata | None = None,
        threshold: int = DEFAULT_THRESHOLD,
    ):
        self.confidence = confidence
        self.threshold = threshold
        self.width = width
        self.workers = workers or default_workers()
        self.tessdata = tessdata or Tessdata()
        #: the tesseract data that `prepare` could not download
        self.failed_codes: set[str] = set()

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self) -> str:
        return (
            f'confidence:{self.confidence}, '
            f'threshold:{self.threshold}, '
            f'width:{self.width}, '
            f'workers:{self.workers}, '
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
        for code in sorted(required_codes(languages)):
            try:
                self.tessdata.ensure({code}, on_download=report)
            except TessdataError as e:
                self.failed_codes.add(code)
                if reporter:
                    reporter(str(e))

    def supports(self, language: Language) -> bool:
        """True when tesseract runs, and has or can get the data of the language."""
        return all(
            code not in self.failed_codes and self.tessdata.available(code) for code in required_codes([language])
        )

    def recognize(self, items: list[Item], language: Language, debug_dir: str | None) -> list[Reading]:
        all_items = items
        readings: dict[Item, Reading] = {}
        quarter_height = max(item.height for item in items) // 4
        gap = Gap(quarter_height + ROW_GAP, quarter_height + ITEM_GAP)
        tessdata_dir = self.tessdata.ensure(required_codes([language]))
        confidence, max_width = self.confidence, self.width
        previous_size = len(items)
        with tesseract_env(tessdata_dir):
            while previous_size > 0:
                read = self.read_pass(items, language, confidence, max_width, gap, tessdata_dir, debug_dir)
                readings.update(read)
                items = [item for item in items if item not in read]
                if not items:
                    break

                current_size = len(items)
                if current_size < LAST_PASS_SIZE:
                    max_width = min(sum(item.width + gap.item for item in items), self.width)
                    confidence = 0
                    readings.update(
                        self.read_pass(items, language, confidence, max_width, gap, tessdata_dir, debug_dir)
                    )
                    break
                elif current_size > previous_size * SLOW_PASS:
                    last_pass = (confidence, max_width)
                    max_width = min(sum(item.width + gap.item for item in items), self.width) // 2
                    confidence = max(0, confidence - CONFIDENCE_STEP)
                    # the same pass on the same items reads nothing new: the remaining items stay unread
                    if (confidence, max_width) == last_pass:
                        break
                previous_size = current_size

        return [readings.get(item, Reading(None)) for item in all_items]

    def read_pass(
        self,
        items: list[Item],
        language: Language,
        confidence: int,
        max_width: int,
        gap: Gap,
        tessdata_dir: str | None,
        debug_dir: str | None,
    ) -> dict[Item, Reading]:
        """Run one OCR pass. Return the reading of each item that it could read."""
        config: dict[str, typing.Any] = {
            'output_type': tess.Output.DICT,
            'config': f'{config_arg(tessdata_dir)} --psm {PSM} --oem {OEM}'.strip(),
        }

        language_code = tesseract_code(language)
        if language_code:
            config.update({'lang': language_code})

        composites = Composite.from_items(items, gap, max_width, MAX_TESS_DIMENSION, self.workers)
        prefix = f'tesseract-{len(items)}'
        if debug_dir:
            for index, composite in enumerate(composites):
                png_file = os.path.join(debug_dir, f'{prefix}-{index}-{confidence}.png')
                logger.debug('Writing temporary png file %s', png_file)
                cv2.imwrite(png_file, composite.image)

        # one tesseract process for each composite, in parallel (see `tesseract_env`)
        with ThreadPoolExecutor(self.workers) as pool:
            results = list(pool.map(lambda composite: tess.image_to_data(composite.image, **config), composites))

        read: dict[Item, Reading] = {}
        for index, (composite, result) in enumerate(zip(composites, results, strict=True)):
            tsv = TsvResult(result, confidence=confidence)
            if debug_dir:
                results_file = os.path.join(debug_dir, f'{prefix}-{index}-{confidence}.json')
                logger.debug('Writing temporary results file %s', results_file)
                with open(results_file, mode='w', encoding='utf8') as f:
                    json.dump([word.__dict__ for word in tsv.words], f, indent=2, ensure_ascii=False)

            # the box of an item is in the composite the item was drawn in: match it against that one only.
            for item, box in composite.placed:
                reading = self.read_item(tsv, box, confidence)
                if reading is not None:
                    read[item] = reading

        return read

    def read_item(self, tsv: TsvResult, box: Box, confidence: int) -> Reading | None:
        """The reading of the words in box. None when no word is in box, or when a word is below the confidence of
        the pass."""
        words = tsv.select(box)
        if not words:
            return None

        lines: list[str] = []
        texts: list[str] = []
        last_word: TsvWord | None = None
        for word in words:
            if word.conf < confidence:
                if not tsv.has_word(word.text):
                    return None

            if (
                last_word is not None
                and (
                    last_word.page_num < word.page_num
                    or last_word.block_num < word.block_num
                    or last_word.par_num < word.par_num
                    or last_word.line_num < word.line_num
                )
                and len(texts) > 0
            ):
                lines.append(' '.join(texts))
                texts.clear()
            texts.append(word.text)
            last_word = word

        if len(texts) > 0:
            lines.append(' '.join(texts))

        lowest = min(word.conf for word in words)
        return Reading('\n'.join(lines).strip(), lowest / 100, lowest < self.threshold)
