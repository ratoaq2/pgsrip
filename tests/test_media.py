import pytest
from pysrt import SubRipTime

from pgsrip.media import PgsSubtitleItem
from pgsrip.media_path import MediaPath
from pgsrip.pgs import PgsReader, SegmentType

from .test_scrub import HEIGHT, WIDTH, display_set, ods, pcs, pds, segment, text_image_data, wds


@pytest.fixture
def media_path():
    return MediaPath('mymedia.en.sup')


def clear_set(number=0, pts=0):
    """A display set that removes the subtitle from the screen: it ends the cue shown before it."""
    return b''.join(
        [
            segment(SegmentType.PCS, pcs(number=number, state=0x00), pts=pts),
            segment(SegmentType.WDS, wds(), pts=pts),
            segment(SegmentType.END, b'', pts=pts),
        ]
    )


@pytest.fixture
def stream():
    """Two cues, each a start set and a clear set. The first cue starts at PTS 0."""
    return b''.join(
        [
            display_set(number=0, pts=0),
            clear_set(number=1, pts=3 * 90000),
            display_set(number=2, pts=4 * 90000),
            clear_set(number=3, pts=6 * 90000),
        ]
    )


def create_items(data, media_path):
    return PgsSubtitleItem.create_items(media_path, PgsReader.decode(data, media_path))


def test_a_cue_at_pts_0_does_not_stop_the_rip(stream, media_path):
    """Regression for #135: PTS 0 was read as a None timestamp, and min() over None and a
    SubRipTime raised TypeError, which stopped the rip of the whole file."""
    items = create_items(stream, media_path)

    assert len(items) == 2
    assert items[1].start == SubRipTime(seconds=4)
    assert items[1].end == SubRipTime(seconds=6)


def test_a_cue_at_pts_0_keeps_its_timestamps(stream, media_path):
    """PTS 0 is a valid timestamp: the cue must not take the time of its clear set as start."""
    items = create_items(stream, media_path)

    assert items[0].start == SubRipTime(0)
    assert items[0].end == SubRipTime(seconds=3)


def palette_update_set(number=0, pts=0):
    """A display set that only changes the palette, for example to fade a subtitle. It has no WDS."""
    return b''.join(
        [
            segment(SegmentType.PCS, pcs(number=number, state=0x00), pts=pts),
            segment(SegmentType.PDS, pds(), pts=pts),
            segment(SegmentType.END, b'', pts=pts),
        ]
    )


def test_a_palette_update_without_window_does_not_stop_the_rip(media_path):
    """Regression for #120: a display set without WDS raised IndexError."""
    data = b''.join(
        [
            display_set(number=0, pts=0),
            palette_update_set(number=1, pts=90000),
            clear_set(number=2, pts=3 * 90000),
            display_set(number=3, pts=4 * 90000),
            clear_set(number=4, pts=6 * 90000),
        ]
    )

    items = create_items(data, media_path)

    assert len(items) == 2
    assert (items[0].x_offset, items[0].y_offset) == (100, 900)


def test_an_object_split_over_three_segments_is_decoded(media_path):
    """Regression for #120: the middle segment of an object has the sequence type 0x00."""
    image_data = text_image_data()
    first, middle, last = image_data[:4], image_data[4:8], image_data[8:]
    data = b''.join(
        [
            segment(SegmentType.PCS, pcs()),
            segment(SegmentType.WDS, wds()),
            segment(SegmentType.PDS, pds()),
            # the first segment has the header of the full object: its data length, width and height
            segment(SegmentType.ODS, ods(image_data, sequence_type=0x80)[:11] + first),
            segment(SegmentType.ODS, b'\x00\x00\x00\x00' + middle),
            segment(SegmentType.ODS, b'\x00\x00\x00\x40' + last),
            segment(SegmentType.END, b''),
            clear_set(number=1, pts=3 * 90000),
        ]
    )

    items = create_items(data, media_path)

    assert len(items) == 1
    image = items[0].image
    assert image is not None
    assert image.rle_data == image_data
    assert image.shape == (HEIGHT, WIDTH)
