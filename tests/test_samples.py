"""Decode a committed subtitle sample, the way a scrubbed bug report is read back.

Nothing here needs tesseract or MKVToolNix: it covers the PGS format itself.
"""

import os

import pytest

from pgsrip.media import PgsSubtitleItem
from pgsrip.media_path import MediaPath
from pgsrip.pgs import CompositionState, PgsReader, SegmentType
from pgsrip.scrub import scrub_data

SAMPLE = 'placeholder.en.sup'
WIDTH = 480
HEIGHT = 48


@pytest.fixture
def media_path():
    return MediaPath(os.path.join(os.path.dirname(__file__), 'samples', SAMPLE))


@pytest.fixture
def data(media_path):
    return media_path.get_data()


@pytest.fixture
def display_sets(data, media_path):
    return list(PgsReader.decode(data, media_path))


def test_sample_is_read_as_display_sets(display_sets):
    assert len(display_sets) == 6
    assert all(ds.is_valid() for ds in display_sets)
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


def test_sample_is_decoded_as_three_subtitle_items(display_sets, media_path):
    items = PgsSubtitleItem.create_items(media_path, display_sets)

    assert len(items) == 3
    assert [(str(item.start), str(item.end)) for item in items] == [
        ('00:00:01,000', '00:00:03,000'),
        ('00:00:04,000', '00:00:06,000'),
        ('00:00:07,000', '00:00:09,000'),
    ]


def test_sample_images_are_decoded_with_their_window_size(display_sets, media_path):
    items = PgsSubtitleItem.create_items(media_path, display_sets)

    for item in items:
        assert item.shape == (900, 100, 900 + HEIGHT, 100 + WIDTH)
        assert item.image is not None
        assert item.image.shape == (HEIGHT, WIDTH)
        # the placeholder text is decoded as ink on a light background
        assert item.image.data.min() == 0
        assert item.image.data.max() == 255


def test_sample_can_be_scrubbed_again(data, media_path):
    scrubbed, stats = scrub_data(data, media_path)

    assert stats.written_display_sets == 6
    assert len(scrubbed) < len(data)
    items = PgsSubtitleItem.create_items(media_path, PgsReader.decode(scrubbed, media_path))
    assert [(str(item.start), str(item.end)) for item in items] == [
        ('00:00:01,000', '00:00:03,000'),
        ('00:00:04,000', '00:00:06,000'),
        ('00:00:07,000', '00:00:09,000'),
    ]
