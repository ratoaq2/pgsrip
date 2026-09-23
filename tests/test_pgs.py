import numpy as np
import pytest

from pgsrip.media_path import MediaPath
from pgsrip.pgs import PgsImage, PgsReader

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


# palette 0 is dark (background, 255), palette 1 is bright (ink, 0)
PALETTES = [(16, 128, 128, 0), (255, 128, 128, 255)] + [(0, 0, 0, 0)] * 254
# every run form: 1 pixel of color 1, 3 of color 0, 2 of color 1, 256 of color 0, 256 of color 1
FIRST_ROW = b'\x01' + b'\x00\x03' + b'\x00\x82\x01' + b'\x00\x41\x00' + b'\x00\xc1\x00\x01' + b'\x00\x00'
FIRST_ROW_PIXELS = [0] + [255] * 3 + [0] * 2 + [255] * 256 + [0] * 256
WIDTH = len(FIRST_ROW_PIXELS)


def test_every_run_form_is_decoded():
    second_row = b'\x00' + bytes([0x40 | (WIDTH >> 8), WIDTH & 0xFF]) + b'\x00\x00'

    image = PgsImage.decode_rle_image(FIRST_ROW + second_row, PALETTES)

    assert image.dtype == np.uint8
    assert image.tolist() == [FIRST_ROW_PIXELS, [255] * WIDTH]


def test_a_truncated_image_is_padded_with_palette_0():
    image = PgsImage.decode_rle_image(FIRST_ROW + b'\x01' * 10, PALETTES)

    assert image.tolist() == [FIRST_ROW_PIXELS, [0] * 10 + [255] * (WIDTH - 10)]


def test_a_color_image_carries_the_palette_alpha():
    image = PgsImage.decode_rle_image(FIRST_ROW, PALETTES, binary=False)

    assert image.shape == (1, WIDTH, 4)
    assert image[0, :7, 3].tolist() == [255, 0, 0, 0, 255, 255, 0]
