from __future__ import annotations

import enum
import functools
import logging
import typing

import numpy as np
import numpy.typing as npt

from pgsrip.errors import PgsripError
from pgsrip.utils import format_time

logger = logging.getLogger(__name__)

#: every segment starts with: 'PG', PTS (4 bytes), DTS (4 bytes), type (1 byte), size (2 bytes)
SEGMENT_HEADER_SIZE = 13
PTS_FIELD = slice(2, 6)
DTS_FIELD = slice(6, 10)
TYPE_FIELD_OFFSET = 10
SIZE_FIELD_OFFSET = 11
#: the PTS and the DTS count 90 ticks in each millisecond
TICKS_PER_MS = 90
#: the first object segment starts with: id (2), version (1), sequence (1), data length (3), width (2), height (2)
OBJECT_HEADER_SIZE = 11
#: a palette entry at least this bright is ink (black in the decoded image), else background (white)
MIN_INK_LUMINANCE = 128
#: a subtitle with no end time ends before the next one, when the next one starts within this gap
MAX_END_FIX_GAP_MS = 10_000


class CorruptDataError(PgsripError):
    """The PGS data of a track has no subtitle that pgsrip can read."""


class Box(typing.NamedTuple):
    """A rectangle in pixels. The bottom row and the right column are not in it."""

    top: int
    left: int
    bottom: int
    right: int


def to_int(b: bytes) -> int | None:
    """The big-endian int of the bytes, or None for no bytes (corrupted data)."""
    return int.from_bytes(b, 'big') if b else None


def safe_get(b: bytes, i: int) -> int:
    """The byte at i, or 0 after the end of corrupted data."""
    try:
        return b[i]
    except IndexError:
        return 0


def to_time(value: float | None) -> int | None:
    """The time in int milliseconds. It truncates, as `SubRipTime.from_ordinal` does."""
    return int(value) if value is not None else None


@enum.unique
class SegmentType(enum.Enum):
    PDS = 0x14
    ODS = 0x15
    PCS = 0x16
    WDS = 0x17
    END = 0x80


@enum.unique
class CompositionState(enum.Enum):
    NORMAL_CASE = 0x00
    ACQUISITION_POINT = 0x40
    EPOCH_START = 0x80


@enum.unique
class ObjectSequenceType(enum.Enum):
    MIDDLE = 0x00
    LAST = 0x40
    FIRST = 0x80
    FIRST_AND_LAST = 0xC0


class PaletteEntry(typing.NamedTuple):
    y: int
    cr: int
    cb: int
    alpha: int


def read_segments(data: bytes, name: str) -> typing.Iterator[Segment]:
    offset = 0
    length = len(data)
    while offset < length:
        if length - offset < SEGMENT_HEADER_SIZE:
            logger.warning(
                '%s Ignoring invalid PGS segment data with less than %d bytes at offset %d',
                name,
                SEGMENT_HEADER_SIZE,
                offset,
            )
            break

        if data[offset : offset + 2] != b'PG':
            logger.warning('%s Ignoring invalid PGS segment data at offset %d', name, offset)
            break

        try:
            segment_class = SEGMENT_CLASSES[SegmentType(data[offset + TYPE_FIELD_OFFSET])]
        except ValueError as e:
            logger.warning('%s Ignoring invalid PGS segment data at offset %d: %s', name, offset, e)
            break

        size_field = to_int(data[offset + SIZE_FIELD_OFFSET : offset + SEGMENT_HEADER_SIZE])
        assert size_field is not None
        size = SEGMENT_HEADER_SIZE + size_field
        yield segment_class(data[offset : offset + size])
        offset += size


def read_display_sets(data: bytes, name: str) -> typing.Iterator[DisplaySet]:
    segments: list[Segment] = []
    index = 0
    for s in read_segments(data, name):
        segments.append(s)
        if s.type == SegmentType.END:
            yield DisplaySet(index, segments)
            segments = []
            index += 1


class PgsImage(typing.NamedTuple):
    """The RLE data of a subtitle image, and its palette."""

    rle_data: bytes
    palette: list[PaletteEntry]


def decode_rle_image(data: bytes, palette: list[PaletteEntry]) -> npt.NDArray[np.uint8]:
    """The image of the RLE data: 0 (ink) or 255 (background) for each pixel."""
    # parse the runs only: the pixels are built at once with np.repeat, not one by one.
    lengths: list[int] = []
    colors: list[int] = []
    total = 0
    cols = 1
    i = 0
    while i < len(data):
        length, color, count = decode_rle_position(data, i)
        if not length and cols < 2:
            cols = total
        lengths.append(length)
        colors.append(color)
        total += length
        i += count

    rows = (total + cols - 1) // cols
    # corrupted image: pad the missing pixels with palette 0
    lengths.append(cols * rows - total)
    colors.append(0)
    color_indexes = np.array(colors, dtype=np.intp)

    lut = np.array([pixel_color(entry) for entry in palette], dtype=np.uint8)
    return np.repeat(lut[color_indexes], lengths).reshape(rows, cols)


def pixel_color(entry: PaletteEntry) -> int:
    """Black ink for a bright palette entry, else white."""
    return 0 if entry.y >= MIN_INK_LUMINANCE else 255


def decode_rle_position(data: bytes, i: int) -> tuple[int, int, int]:
    """The run at i: the number of pixels, the palette index, and the number of bytes."""
    first = safe_get(data, i)
    if first:
        return 1, first, 1

    second = safe_get(data, i + 1)
    if second < 64:
        return second, 0, 2

    third = safe_get(data, i + 2)
    if second < 128:
        return ((second - 64) << 8) + third, 0, 3
    elif second < 192:
        return second - 128, third, 3

    fourth = safe_get(data, i + 3)
    return ((second - 192) << 8) + third, fourth, 4


class Segment:
    def __init__(self, b: bytes):
        self.bytes = b

    @property
    def presentation_timestamp(self) -> int | None:
        value = to_int(self.bytes[PTS_FIELD])
        return to_time(value / TICKS_PER_MS) if value is not None else None

    @property
    def decoding_timestamp(self) -> int | None:
        value = to_int(self.bytes[DTS_FIELD])
        return to_time(value / TICKS_PER_MS) if value is not None else None

    @property
    def type(self) -> SegmentType:
        return SegmentType(self.bytes[TYPE_FIELD_OFFSET])

    @property
    def size(self) -> int:
        value = to_int(self.bytes[SIZE_FIELD_OFFSET:SEGMENT_HEADER_SIZE])
        assert value is not None
        return value

    @property
    def data(self) -> bytes:
        return self.bytes[SEGMENT_HEADER_SIZE:]

    def to_json(self) -> dict[str, typing.Any]:
        attributes: dict[str, str] = {
            'type': 'type',
            'pts': 'presentation_timestamp',
            'dts': 'decoding_timestamp',
            'size': 'size',
            **self.attributes(),
        }

        def to_value(k: str, v: typing.Any) -> typing.Any:
            if k in ('pts', 'dts'):
                return format_time(v)
            return v.name if isinstance(v, enum.Enum) else v

        values: dict[str, typing.Any] = {}
        for k, v in attributes.items():
            try:
                value = getattr(self, v)
            except (ValueError, IndexError):
                # corrupted data: the debug files show it
                value = 'invalid'
            if value is not None:
                values[k] = to_value(k, value)

        return values

    def attributes(self) -> dict[str, str]:
        raise NotImplementedError

    def __str__(self) -> str:
        strings = []
        for k, v in self.to_json().items():
            if v is not None:
                strings.append(f'{k}={v}')

        return ', '.join(strings)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'


class PresentationCompositionSegment(Segment):
    @property
    def width(self) -> int | None:
        return to_int(self.data[0:2])

    @property
    def height(self) -> int | None:
        return to_int(self.data[2:4])

    @property
    def frame_rate(self) -> int:
        return self.data[4]

    @property
    def composition_number(self) -> int | None:
        return to_int(self.data[5:7])

    @property
    def composition_state(self) -> CompositionState:
        return CompositionState(self.data[7])

    @property
    def palette_update(self) -> bool:
        return bool(self.data[8])

    @property
    def palette_id(self) -> int:
        return self.data[9]

    @property
    def object_count(self) -> int:
        return self.data[10]

    def attributes(self) -> dict[str, str]:
        return {
            'width': 'width',
            'height': 'height',
            'frame_rate': 'frame_rate',
            'composition_number': 'composition_number',
            'state': 'composition_state',
            'palette_update': 'palette_update',
            'palette_id': 'palette_id',
            'object_count': 'object_count',
        }

    def is_start(self) -> bool:
        return self.composition_state in (CompositionState.EPOCH_START, CompositionState.ACQUISITION_POINT)


class WindowDefinitionSegment(Segment):
    @property
    def window_count(self) -> int:
        return self.data[0]

    @property
    def window_id(self) -> int | None:
        return self.data[1] if len(self.data) > 1 else None

    @property
    def x_offset(self) -> int | None:
        return to_int(self.data[2:4])

    @property
    def y_offset(self) -> int | None:
        return to_int(self.data[4:6])

    @property
    def width(self) -> int | None:
        return to_int(self.data[6:8])

    @property
    def height(self) -> int | None:
        return to_int(self.data[8:10])

    def attributes(self) -> dict[str, str]:
        return {
            'window_count': 'window_count',
            'window_id': 'window_id',
            'x_offset': 'x_offset',
            'y_offset': 'y_offset',
            'width': 'width',
            'height': 'height',
        }


class PaletteDefinitionSegment(Segment):
    def __init__(self, b: bytes):
        super().__init__(b)
        self.entries = [PaletteEntry(0, 0, 0, 0)] * 256
        # the entries start at byte 2. Each entry has 5 bytes: the palette index, then a PaletteEntry
        for entry in range(len(self.data[2:]) // 5):
            i = 2 + entry * 5
            self.entries[self.data[i]] = PaletteEntry(*self.data[i + 1 : i + 5])

    @property
    def palette_id(self) -> int:
        return self.data[0]

    @property
    def version(self) -> int:
        return self.data[1]

    def attributes(self) -> dict[str, str]:
        return {'palette_id': 'palette_id', 'version': 'version'}


class ObjectDefinitionSegment(Segment):
    @property
    def id(self) -> int | None:
        return to_int(self.data[0:2])

    @property
    def version(self) -> int:
        return self.data[2]

    @property
    def sequence_type(self) -> ObjectSequenceType:
        return ObjectSequenceType(self.data[3])

    @property
    def data_length(self) -> int | None:
        if self.sequence_type in (ObjectSequenceType.FIRST, ObjectSequenceType.FIRST_AND_LAST):
            return to_int(self.data[4:7])
        return None

    @property
    def width(self) -> int | None:
        if self.sequence_type in (ObjectSequenceType.FIRST, ObjectSequenceType.FIRST_AND_LAST):
            return to_int(self.data[7:9])
        return None

    @property
    def height(self) -> int | None:
        if self.sequence_type in (ObjectSequenceType.FIRST, ObjectSequenceType.FIRST_AND_LAST):
            return to_int(self.data[9:11])
        return None

    @property
    def image_data(self) -> bytes:
        if self.sequence_type in (ObjectSequenceType.MIDDLE, ObjectSequenceType.LAST):
            return self.data[4:]

        return self.data[OBJECT_HEADER_SIZE:]

    def attributes(self) -> dict[str, str]:
        return {
            'id': 'id',
            'version': 'version',
            'sequence_type': 'sequence_type',
            'data_length': 'data_length',
            'width': 'width',
            'height': 'height',
        }


class EndSegment(Segment):
    def attributes(self) -> dict[str, str]:
        return {}


SEGMENT_CLASSES: dict[SegmentType, type[Segment]] = {
    SegmentType.PDS: PaletteDefinitionSegment,
    SegmentType.ODS: ObjectDefinitionSegment,
    SegmentType.PCS: PresentationCompositionSegment,
    SegmentType.WDS: WindowDefinitionSegment,
    SegmentType.END: EndSegment,
}


class DisplaySet:
    def __init__(self, index: int, segments: list[Segment]):
        self.index = index
        self.segments = segments

    @property
    def pcs(self) -> PresentationCompositionSegment:
        return [s for s in self.segments if isinstance(s, PresentationCompositionSegment)][0]

    @property
    def wds(self) -> WindowDefinitionSegment | None:
        return next((s for s in self.segments if isinstance(s, WindowDefinitionSegment)), None)

    @property
    def pds_segments(self) -> list[PaletteDefinitionSegment]:
        return [s for s in self.segments if isinstance(s, PaletteDefinitionSegment)]

    @property
    def ods_segments(self) -> list[ObjectDefinitionSegment]:
        return [s for s in self.segments if isinstance(s, ObjectDefinitionSegment)]

    def is_start(self) -> bool:
        return self.pcs.is_start()

    def error(self) -> str | None:
        """Why the display set cannot be read, or None."""
        if not any(isinstance(s, PresentationCompositionSegment) for s in self.segments):
            return 'no PCS'
        try:
            # the enum properties raise ValueError on a value that does not exist, the others IndexError on no data
            _ = self.pcs.composition_state, self.pcs.palette_id, [ods.sequence_type for ods in self.ods_segments]
            _ = self.wds.window_count if self.wds else None
        except (ValueError, IndexError) as e:
            return str(e)

        return None

    def to_json(self) -> dict[str, typing.Any]:
        return {'index': self.index, 'segments': [s.to_json() for s in self.segments]}

    def __str__(self) -> str:
        strings = [f'DS[{self.index}]']
        for s in self.segments:
            strings.append(f'\t{s}')

        return '\n'.join(strings)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'


def first_image(display_sets: typing.Iterable[DisplaySet]) -> PgsImage | None:
    """The image of the first display set that starts a subtitle."""
    for ds in display_sets:
        if not ds.pcs.is_start():
            continue

        # the palette of the composition, else the last one. No palette: the item is dropped.
        palettes = {pds.palette_id: pds.entries for pds in ds.pds_segments}
        palette = palettes.get(ds.pcs.palette_id) or next(reversed(palettes.values()), [])
        image_data = b''
        for ods in ds.ods_segments:
            image_data += ods.image_data

        return PgsImage(image_data, palette)

    return None


def read_items(display_sets: typing.Iterable[DisplaySet], name: str) -> list[Item]:
    """Group the display sets into items. A corrupted item is fixed, or dropped."""
    groups: list[list[DisplaySet]] = []
    for ds in display_sets:
        error = ds.error()
        if error:
            logger.warning('%s Ignoring corrupted display set %d: %s', name, ds.index, error)
            continue

        if not groups or ds.is_start():
            groups.append([])
        groups[-1].append(ds)

    starts = [start_time(group) for group in groups]
    items = []
    for index, group in enumerate(groups):
        next_start = starts[index + 1] if index + 1 < len(starts) else None
        item = make_item(index, group, next_start, name)
        if item is not None:
            items.append(item)

    return items


def start_time(display_sets: list[DisplaySet]) -> int | None:
    return min((t for ds in display_sets if (t := ds.pcs.presentation_timestamp) is not None), default=None)


def make_item(index: int, display_sets: list[DisplaySet], next_start: int | None, name: str) -> Item | None:
    """The item of a group of display sets. Fix a missing end time with the start of the next item.

    None when the item is corrupted.
    """
    start = start_time(display_sets)
    end = max((t for ds in display_sets if (t := ds.pcs.presentation_timestamp) is not None), default=None)
    image = first_image(display_sets)
    windows = [w for ds in display_sets if (w := ds.wds) and w.window_count > 0]
    x_offset = min((x for w in windows if (x := w.x_offset) is not None), default=None)
    y_offset = min((y for w in windows if (y := w.y_offset) is not None), default=None)
    label = f'{name} [{format_time(start)} --> {format_time(end)}]'

    errors = []
    if image is None:
        errors.append('no image')
    elif not image.palette:
        errors.append('no palette')
    if y_offset is None:
        errors.append('no y_offset')
    if x_offset is None:
        errors.append('no x_offset')
    if start is None:
        errors.append('no start timestamp')
    elif end is None or end <= start:
        if next_start is not None and start + MAX_END_FIX_GAP_MS >= next_start:
            end = max(start + 1, next_start - 1)
            logger.info('Fixed item %s: the end timestamp is the start of the next item', label)
        else:
            errors.append('no valid end timestamp')

    for error in errors:
        logger.warning('Corrupted item %s: %s', label, error)
    if errors or image is None or start is None or end is None or x_offset is None or y_offset is None:
        return None

    return Item(index, start, end, image, x_offset, y_offset, name)


class Item:
    """One subtitle image, with its start and end time: the input of the OCR engines. `read_items` makes it."""

    def __init__(self, index: int, start: int, end: int, image: PgsImage, x_offset: int, y_offset: int, name: str):
        self.index = index
        #: in milliseconds
        self.start = start
        #: in milliseconds
        self.end = end
        self.image = image
        #: the position of the window on the screen
        self.x_offset = x_offset
        self.y_offset = y_offset
        #: the subtitle of the item, for the log messages
        self.name = name

    @functools.cached_property
    def _ink(self) -> tuple[tuple[int, int], npt.NDArray[np.uint8]]:
        """The (top, left) origin of the ink box in the image, and the image cropped to it.

        PGS objects often span the whole frame width: OCR only the ink. Only the cropped image is kept in
        memory.
        """
        data = decode_rle_image(self.image.rle_data, self.image.palette)
        ink = data == 0
        rows = np.flatnonzero(ink.any(axis=1))
        cols = np.flatnonzero(ink.any(axis=0))
        if not len(rows):
            return (0, 0), data[:0, :0].copy()

        return (int(rows[0]), int(cols[0])), data[rows[0] : rows[-1] + 1, cols[0] : cols[-1] + 1].copy()

    @property
    def bitmap(self) -> npt.NDArray[np.uint8]:
        return self._ink[1]

    @property
    def height(self) -> int:
        return int(self.bitmap.shape[0])

    @property
    def width(self) -> int:
        return int(self.bitmap.shape[1])

    @property
    def box(self) -> Box:
        """The box of the ink on the screen."""
        top, left = self._ink[0]
        top, left = self.y_offset + top, self.x_offset + left

        return Box(top, left, top + self.height, left + self.width)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self) -> str:
        return f'{self.name} [{format_time(self.start)} --> {format_time(self.end)}]'
