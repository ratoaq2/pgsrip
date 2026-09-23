import pytest
from pysrt import SubRipTime

from pgsrip.media import PgsSubtitleItem
from pgsrip.media_path import MediaPath
from pgsrip.pgs import PgsReader, SegmentType

from .test_scrub import display_set, pcs, segment, wds


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


def create_items(data, media_path):
    return PgsSubtitleItem.create_items(media_path, PgsReader.decode(data, media_path))


def test_a_cue_at_pts_0_does_not_stop_the_rip(media_path):
    """Regression for #135: PTS 0 was read as a None timestamp, and min() over None and a
    SubRipTime raised TypeError, which stopped the rip of the whole file."""
    data = b''.join(
        [
            display_set(number=0, pts=0),
            clear_set(number=1, pts=3 * 90000),
            display_set(number=2, pts=4 * 90000),
            clear_set(number=3, pts=6 * 90000),
        ]
    )

    items = create_items(data, media_path)

    assert len(items) == 2
    assert items[1].start == SubRipTime(seconds=4)
    assert items[1].end == SubRipTime(seconds=6)
