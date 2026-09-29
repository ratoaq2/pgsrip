"""Decode a committed subtitle sample, the way a scrubbed bug report is read back.

Nothing here needs tesseract or MKVToolNix: it covers the PGS format itself.
"""

import os

import pytest

from pgsrip.formats.pgs import CompositionState, SegmentType, decode_rle_image, read_display_sets, read_items
from pgsrip.formats.scrub import scrub_data
from pgsrip.utils import format_time

SAMPLE = 'placeholder.en.sup'
WIDTH = 480
HEIGHT = 48


@pytest.fixture
def name():
    return str(os.path.join(os.path.dirname(__file__), 'samples', SAMPLE))


@pytest.fixture
def data(name):
    with open(name, 'rb') as f:
        return f.read()


@pytest.fixture
def display_sets(data, name):
    return list(read_display_sets(data, name))


def test_sample_is_read_as_display_sets(display_sets):
    assert len(display_sets) == 6
    assert [ds.index for ds in display_sets] == [0, 1, 2, 3, 4, 5]


def test_sample_alternates_between_a_subtitle_and_an_empty_screen(display_sets):
    states = [ds.pcs.composition_state for ds in display_sets]

    assert states[::2] == [CompositionState.EPOCH_START] * 3
    assert states[1::2] == [CompositionState.NORMAL_CASE] * 3


def test_sample_holds_one_object_per_subtitle(display_sets):
    objects = [len(ds.ods_segments) for ds in display_sets]

    assert objects == [1, 0, 1, 0, 1, 0]
    assert [s.type for s in display_sets[0].segments] == [
        SegmentType.PCS,
        SegmentType.WDS,
        SegmentType.PDS,
        SegmentType.ODS,
        SegmentType.END,
    ]


def test_sample_is_decoded_as_three_subtitle_items(display_sets, name):
    items = read_items(display_sets, name)

    assert len(items) == 3
    assert [(format_time(item.start), format_time(item.end)) for item in items] == [
        ('00:00:01,000', '00:00:03,000'),
        ('00:00:04,000', '00:00:06,000'),
        ('00:00:07,000', '00:00:09,000'),
    ]


def test_sample_images_are_decoded_with_their_window_size(display_sets, name):
    items = read_items(display_sets, name)

    for item in items:
        assert item.image is not None
        image = decode_rle_image(item.image.rle_data, item.image.palette)
        assert image.shape == (HEIGHT, WIDTH)
        # the placeholder text is decoded as ink on a light background
        assert image.min() == 0
        assert image.max() == 255


def test_sample_items_are_cropped_to_their_ink(display_sets, name):
    items = read_items(display_sets, name)

    for item in items:
        assert item.image is not None
        top, left, bottom, right = item.box
        # the window is at (900, 100): the ink box is inside it, and its position on screen is kept
        assert 900 < top < bottom < 900 + HEIGHT
        assert 100 < left < right < 100 + WIDTH
        image = decode_rle_image(item.image.rle_data, item.image.palette)
        window_box = image[top - 900 : bottom - 900, left - 100 : right - 100]
        assert (item.bitmap == window_box).all()
        # no blank row or column is left on any side
        ink = item.bitmap == 0
        assert ink[0].any() and ink[-1].any() and ink[:, 0].any() and ink[:, -1].any()


def test_sample_can_be_scrubbed_again(data, name):
    scrubbed, stats = scrub_data(data, name)

    assert stats.written_display_sets == 6
    assert len(scrubbed) < len(data)
    items = read_items(read_display_sets(scrubbed, name), name)
    assert [(format_time(item.start), format_time(item.end)) for item in items] == [
        ('00:00:01,000', '00:00:03,000'),
        ('00:00:04,000', '00:00:06,000'),
        ('00:00:07,000', '00:00:09,000'),
    ]


def test_a_redacted_item_has_no_ink_to_crop(data, name):
    scrubbed, _ = scrub_data(data, name)

    items = read_items(read_display_sets(scrubbed, name), name)

    assert [(item.height, item.width) for item in items] == [(0, 0)] * 3
