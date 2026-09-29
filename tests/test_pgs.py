import numpy as np
import pytest

from pgsrip.formats.pgs import (
    PaletteEntry,
    SegmentType,
    decode_rle_image,
    read_display_sets,
    read_items,
    read_segments,
    to_time,
)

from .test_media import clear_set
from .test_scrub import display_set, ods, pcs, pds, segment, text_image_data, wds

DISPLAY_SETS = 200
SEGMENTS_PER_DISPLAY_SET = 5


class CountingBytes(bytes):
    """Bytes that add up how much data every slice of them, and of their slices, copies."""

    def __new__(cls, data, copied=None):
        instance = super().__new__(cls, data)
        instance.copied = copied if copied is not None else [0]

        return instance

    def __getitem__(self, index):
        value = super().__getitem__(index)
        if not isinstance(index, slice):
            return value

        self.copied[0] += len(value)

        return CountingBytes(value, self.copied)


@pytest.fixture
def name():
    return 'mymedia.en.sup'


def test_read_segments_copies_each_byte_a_constant_number_of_times(name):
    """Regression for #136: dropping the parsed prefix with `b = b[size:]` copied the rest of the
    stream once per segment. That is quadratic, and it hung on 30 MB files."""
    data = CountingBytes(b''.join(display_set(number=i, pts=i * 90000) for i in range(DISPLAY_SETS)))

    segments = list(read_segments(data, name))

    assert len(segments) == DISPLAY_SETS * SEGMENTS_PER_DISPLAY_SET
    assert data.copied[0] < 2 * len(data)


# palette 0 is dark (background, 255), palette 1 is bright (ink, 0)
PALETTES = [PaletteEntry(16, 128, 128, 0), PaletteEntry(255, 128, 128, 255)] + [PaletteEntry(0, 0, 0, 0)] * 254
# every run form: 1 pixel of color 1, 3 of color 0, 2 of color 1, 256 of color 0, 256 of color 1
FIRST_ROW = b'\x01' + b'\x00\x03' + b'\x00\x82\x01' + b'\x00\x41\x00' + b'\x00\xc1\x00\x01' + b'\x00\x00'
FIRST_ROW_PIXELS = [0] + [255] * 3 + [0] * 2 + [255] * 256 + [0] * 256
WIDTH = len(FIRST_ROW_PIXELS)


def test_every_run_form_is_decoded():
    second_row = b'\x00' + bytes([0x40 | (WIDTH >> 8), WIDTH & 0xFF]) + b'\x00\x00'

    image = decode_rle_image(FIRST_ROW + second_row, PALETTES)

    assert image.dtype == np.uint8
    assert image.tolist() == [FIRST_ROW_PIXELS, [255] * WIDTH]


def test_a_truncated_image_is_padded_with_palette_0():
    image = decode_rle_image(FIRST_ROW + b'\x01' * 10, PALETTES)

    assert image.tolist() == [FIRST_ROW_PIXELS, [0] * 10 + [255] * (WIDTH - 10)]


def test_to_time_truncates_to_int_milliseconds() -> None:
    assert to_time(100000 / 90) == 1111
    assert to_time(None) is None


def unknown_segment(pts=0):
    return b'PG' + pts.to_bytes(4, 'big') + b'\x00' * 4 + b'\x99' + b'\x00\x00'


@pytest.mark.parametrize(
    'corrupted, count',
    [
        # reading stops at a segment of an unknown type, like at a bad PG marker
        (unknown_segment(pts=4 * 90000) + segment(SegmentType.END, b'', pts=4 * 90000), 1),
        # a display set with no PCS
        (segment(SegmentType.WDS, wds(), pts=4 * 90000) + segment(SegmentType.END, b'', pts=4 * 90000), 2),
        # a composition state that does not exist
        (segment(SegmentType.PCS, pcs(state=0x20), pts=4 * 90000) + segment(SegmentType.END, b'', pts=4 * 90000), 2),
        # a window segment with no data
        (
            segment(SegmentType.PCS, pcs(number=2), pts=4 * 90000)
            + segment(SegmentType.WDS, b'', pts=4 * 90000)
            + segment(SegmentType.END, b'', pts=4 * 90000),
            2,
        ),
    ],
    ids=['unknown segment type', 'no PCS', 'bad composition state', 'empty WDS'],
)
def test_a_corrupted_display_set_is_dropped_with_a_warning(corrupted, count, name, caplog):
    data = b''.join(
        [
            display_set(number=0, pts=0),
            clear_set(number=1, pts=3 * 90000),
            corrupted,
            display_set(number=3, pts=5 * 90000),
            clear_set(number=4, pts=7 * 90000),
        ]
    )

    display_sets = list(read_display_sets(data, name))
    items = read_items(display_sets, name)

    assert [item.start for item in items] == [0, 5000][:count]
    assert [record.levelname for record in caplog.records] == ['WARNING']
    assert all(ds.to_json() for ds in display_sets)


def test_a_display_set_with_no_palette_is_dropped_with_a_warning(name, caplog):
    no_palette = b''.join(
        [
            segment(SegmentType.PCS, pcs(number=2), pts=4 * 90000),
            segment(SegmentType.WDS, wds(), pts=4 * 90000),
            segment(SegmentType.ODS, ods(text_image_data()), pts=4 * 90000),
            segment(SegmentType.END, b'', pts=4 * 90000),
        ]
    )
    data = b''.join(
        [
            display_set(number=0, pts=0),
            clear_set(number=1, pts=3 * 90000),
            no_palette,
            clear_set(number=3, pts=5 * 90000),
            display_set(number=4, pts=6 * 90000),
            clear_set(number=5, pts=8 * 90000),
        ]
    )

    items = read_items(read_display_sets(data, name), name)

    assert [item.start for item in items] == [0, 6000]
    assert all(item.height for item in items)
    assert [record.levelname for record in caplog.records] == ['WARNING']


def test_the_palette_is_the_one_of_the_composition(name):
    # palette 0 shows entry 1 as background, palette 1 shows it as ink. The PCS uses palette 1.
    data = b''.join(
        [
            segment(SegmentType.PCS, pcs(palette_id=1), pts=0),
            segment(SegmentType.WDS, wds(), pts=0),
            segment(SegmentType.PDS, pds([(1, 16, 128, 128, 255)], palette_id=0), pts=0),
            segment(SegmentType.PDS, pds([(1, 255, 128, 128, 255)], palette_id=1), pts=0),
            segment(SegmentType.ODS, ods(text_image_data()), pts=0),
            segment(SegmentType.END, b'', pts=0),
            clear_set(number=1, pts=3 * 90000),
        ]
    )

    (item,) = read_items(read_display_sets(data, name), name)

    assert item.height
