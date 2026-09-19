"""Create a small copy of a PGS subtitle that can reproduce a bug without sharing the media.

A PGS stream is made of two very different parts: the segments that describe when and where a
subtitle is shown, and the run length encoded bitmaps that hold the text itself. Only the bitmaps
carry the content of the media, and almost every bug is in the first part. Scrubbing replaces the
bitmaps and keeps everything else byte for byte, so the result is a real .sup file that pgsrip
reads through the very same code path.
"""

from __future__ import annotations

import enum
import hashlib
import logging
import os
import typing

import cv2
import numpy as np
import numpy.typing as npt

from pgsrip.media_path import MediaPath
from pgsrip.pgs import (
    BaseSegment,
    DisplaySet,
    ObjectDefinitionSegment,
    ObjectSequenceType,
    PgsReader,
)

logger = logging.getLogger(__name__)

# a run length is stored in 14 bits, a segment size in 2 bytes
MAX_RUN_LENGTH = 0x3FFF
MAX_SEGMENT_SIZE = 0xFFFF
# a palette entry is only used as text when it is bright enough to be decoded as ink
MIN_TEXT_LUMINANCE = 128
PLACEHOLDER_TEXT = 'Lorem ipsum dolor sit amet'
SUP_EXTENSION = '.sup'
TEXT_FONT = cv2.FONT_HERSHEY_SIMPLEX


class ScrubError(Exception):
    """Raised when a PGS stream cannot be scrubbed."""


@enum.unique
class Redaction(enum.Enum):
    """What happens to the subtitle bitmaps."""

    ALL = 'all'
    SYNTHETIC = 'synthetic'
    NONE = 'none'


class ScrubStats(typing.NamedTuple):
    """What the scrubbed stream ended up with."""

    display_sets: int
    written_display_sets: int
    objects: int
    redacted_objects: int
    size: int

    def __str__(self) -> str:
        return (
            f'{self.written_display_sets}/{self.display_sets} display sets, '
            f'{self.redacted_objects}/{self.objects} images redacted, '
            f'{self.size} bytes'
        )


def encode_run(color: int, length: int) -> bytes:
    """Encode a single run of pixels of the same palette entry."""
    if color and length == 1:
        return bytes([color])

    if not color:
        if length < 64:
            return bytes([0, length])

        return bytes([0, 0x40 | (length >> 8), length & 0xFF])

    if length < 64:
        return bytes([0, 0x80 | length, color])

    return bytes([0, 0xC0 | (length >> 8), length & 0xFF, color])


def encode_runs(rows: typing.Iterable[typing.Iterable[tuple[int, int]]]) -> bytes:
    """Encode rows of (palette entry, length) runs as PGS run length data."""
    data = bytearray()
    for row in rows:
        for color, length in row:
            while length > 0:
                run = min(length, MAX_RUN_LENGTH)
                data += encode_run(color, run)
                length -= run

        # every row ends with a zero length run
        data += b'\x00\x00'

    return bytes(data)


def to_runs(row: npt.NDArray[np.uint8]) -> list[tuple[int, int]]:
    """Turn a row of palette entries into runs."""
    changes = np.flatnonzero(np.diff(row.astype(np.int16))) + 1
    starts = np.concatenate(([0], changes))
    ends = np.concatenate((changes, [len(row)]))

    return [(int(row[start]), int(end - start)) for start, end in zip(starts, ends, strict=True)]


def blank_rows(width: int, height: int) -> list[list[tuple[int, int]]]:
    """Rows of a fully transparent image of the given size."""
    return [[(0, width)]] * height


def synthetic_rows(width: int, height: int, color: int, index: int) -> list[list[tuple[int, int]]]:
    """Rows of an image of the given size holding placeholder text instead of the original one."""
    image = np.zeros((height, width), dtype=np.uint8)
    text = f'{PLACEHOLDER_TEXT} {index}'
    thickness = max(1, height // 40)
    (text_width, text_height), _ = cv2.getTextSize(text, TEXT_FONT, 1.0, thickness)
    if text_width and text_height:
        scale = min(width * 0.9 / text_width, height * 0.6 / text_height)
        origin = (int(width * 0.05), int(height / 2 + text_height * scale / 2))
        # LINE_8 keeps every pixel on an existing palette entry, anti aliasing would not
        cv2.putText(image, text, origin, TEXT_FONT, scale, color, thickness, cv2.LINE_8)

    return [to_runs(row) for row in image]


def find_text_color(display_set: DisplaySet) -> int | None:
    """Return the palette entry to draw placeholder text with, or None when there is no usable one."""
    brightest: tuple[int, int] | None = None
    for pds in display_set.pds_segments:
        for index, palette in enumerate(pds.palettes):
            if index and palette.alpha and (brightest is None or palette.y > brightest[1]):
                brightest = (index, palette.y)

    return brightest[0] if brightest and brightest[1] >= MIN_TEXT_LUMINANCE else None


def create_image_data(width: int, height: int, index: int, color: int | None) -> bytes:
    """Build the run length data that replaces an original subtitle bitmap."""
    if color:
        data = encode_runs(synthetic_rows(width, height, color, index))
        if len(data) + 11 <= MAX_SEGMENT_SIZE:
            return data

        logger.debug('Placeholder text does not fit in a segment for display set %d, using a blank image', index)

    return encode_runs(blank_rows(width, height))


def rebuild_segment(segment: BaseSegment, data: bytes) -> bytes:
    """Return the segment with new data, with its size field updated."""
    if len(data) > MAX_SEGMENT_SIZE:
        raise ScrubError(f'Redacted segment is too large: {len(data)} bytes')

    return segment.bytes[:11] + len(data).to_bytes(2, 'big') + data


def redact_object(segment: ObjectDefinitionSegment, index: int, color: int | None) -> bytes:
    """Replace the bitmap of an object segment, keeping its identity and its size."""
    data = segment.data
    try:
        sequence_type = segment.sequence_type
    except ValueError:
        # the segment is corrupted, and that is exactly what has to be reproduced: keep its header
        logger.debug('Keeping the header of a corrupted object segment in display set %d', index)
        return rebuild_segment(segment, data[:4])

    if sequence_type == ObjectSequenceType.LAST:
        # the object continues here, the replacement bitmap goes in the segment that starts it
        return rebuild_segment(segment, data[:4])

    width, height = segment.width, segment.height
    if not width or not height:
        return rebuild_segment(segment, data[:11])

    image_data = create_image_data(width, height, index, color)
    header = bytearray(data[:11])
    # the object data length counts the width and height fields too
    header[4:7] = (len(image_data) + 4).to_bytes(3, 'big')

    return rebuild_segment(segment, bytes(header) + image_data)


def redact_display_set(display_set: DisplaySet, redaction: Redaction) -> tuple[bytes, int]:
    """Return the bytes of a display set without its original bitmaps, and how many were replaced."""
    color = find_text_color(display_set) if redaction == Redaction.SYNTHETIC else None
    data = bytearray()
    redacted = 0
    for segment in display_set.segments:
        if isinstance(segment, ObjectDefinitionSegment):
            data += redact_object(segment, display_set.index, color)
            redacted += 1
        else:
            data += segment.bytes

    return bytes(data), redacted


def scrub_display_sets(
    display_sets: typing.Iterable[DisplaySet],
    redaction: Redaction = Redaction.ALL,
    keep_images: typing.Container[int] = frozenset(),
    only: typing.Container[int] | None = None,
) -> tuple[bytes, ScrubStats]:
    """Rewrite display sets without their original bitmaps.

    Display sets in keep_images keep their bitmaps, and only, when it is given, selects the display
    sets that are written at all.
    """
    data = bytearray()
    display_set_count = 0
    written = 0
    objects = 0
    redacted = 0
    for display_set in display_sets:
        display_set_count += 1
        if only is not None and display_set.index not in only:
            continue

        written += 1
        objects += len([s for s in display_set.segments if isinstance(s, ObjectDefinitionSegment)])
        if redaction == Redaction.NONE or display_set.index in keep_images:
            data += b''.join(segment.bytes for segment in display_set.segments)
            continue

        display_set_data, redacted_count = redact_display_set(display_set, redaction)
        data += display_set_data
        redacted += redacted_count

    return bytes(data), ScrubStats(display_set_count, written, objects, redacted, len(data))


def verify(data: bytes, media_path: MediaPath, expected: int) -> bool:
    """Check that the scrubbed stream can be read back as the same number of display sets."""
    try:
        found = len(list(PgsReader.decode(data, media_path)))
    except Exception as e:
        logger.warning('Cannot read the scrubbed stream back: <%s> [%s]', type(e).__name__, e)
        return False

    if found != expected:
        logger.warning('Scrubbed stream has %d display sets instead of %d', found, expected)
        return False

    return True


def scrub_data(
    data: bytes,
    media_path: MediaPath,
    redaction: Redaction = Redaction.ALL,
    keep_images: typing.Container[int] = frozenset(),
    only: typing.Container[int] | None = None,
) -> tuple[bytes, ScrubStats]:
    """Scrub a whole PGS stream."""
    display_sets = list(PgsReader.decode(data, media_path))
    scrubbed, stats = scrub_display_sets(display_sets, redaction, keep_images, only)
    verify(scrubbed, media_path, stats.written_display_sets)

    return scrubbed, stats


def default_name(media_path: MediaPath, keep_name: bool) -> str:
    """Name the scrubbed file after the media, or after a hash of its name."""
    name = os.path.splitext(os.path.basename(str(media_path)))[0]
    if keep_name:
        return name

    return f'pgsrip-{hashlib.sha256(name.encode("utf8")).hexdigest()[:8]}'


def output_path(media_path: MediaPath, language: str, output: str | None, keep_name: bool, used: set[str]) -> str:
    """Build the path of the scrubbed file, without ever reusing one."""
    if output and output.lower().endswith(SUP_EXTENSION):
        base = output[: -len(SUP_EXTENSION)]
    elif output and (os.path.isdir(output) or output.endswith(('/', os.sep))):
        base = os.path.join(output, default_name(media_path, keep_name))
    elif output:
        base = output
    else:
        base = default_name(media_path, keep_name)

    path = f'{base}.{language}{SUP_EXTENSION}'
    index = 1
    while path in used:
        path = f'{base}.{language}.{index}{SUP_EXTENSION}'
        index += 1

    used.add(path)

    return path
