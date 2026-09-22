import pytest

from pgsrip.media_path import MediaPath
from pgsrip.pgs import PgsReader

from .test_scrub import display_set

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
def media_path():
    return MediaPath('mymedia.en.sup')


def test_read_segments_copies_each_byte_a_constant_number_of_times(media_path):
    """Regression for #136: dropping the parsed prefix with `b = b[size:]` copied the rest of the
    stream once per segment. That is quadratic, and it hung on 30 MB files."""
    data = CountingBytes(b''.join(display_set(number=i, pts=i * 90000) for i in range(DISPLAY_SETS)))

    segments = list(PgsReader.read_segments(data, media_path))

    assert len(segments) == DISPLAY_SETS * SEGMENTS_PER_DISPLAY_SET
    assert data.copied[0] < 2 * len(data)
