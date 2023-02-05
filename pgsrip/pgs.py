import logging
import typing

import cv2

import numpy as np
from numpy import ndarray

from pgsrip.media_path import MediaPath

logger = logging.getLogger(__name__)


# Constants for Segments
PDS = int('0x14', 16)
ODS = int('0x15', 16)
PCS = int('0x16', 16)
WDS = int('0x17', 16)
END = int('0x80', 16)


def from_hex(b: bytes):
    return int(b.hex(), base=16)


def safe_get(b: bytes, i: int, default_value=0):
    try:
        return b[i]
    except IndexError:
        return default_value


class Palette(typing.NamedTuple):
    y: int
    cr: int
    cb: int
    alpha: int


class PgsReader:

    @classmethod
    def read_segments(cls, data: bytes, media_path: MediaPath):
        count = 0
        b = data
        while b:
            if b[:2] != b'PG':
                logger.warning('%s Ignoring invalid PGS segment data: %s', media_path, b)
                break

            if len(b) < 13:
                logger.warning('%s Ignoring invalid PGS segment data with less than 13 bytes: %s', media_path, b)
                break

            size = 13 + from_hex(b[11:13])
            segment_type = SEGMENT_TYPE[b[10]]
            yield segment_type(b[:size])
            count += size
            b = b[size:]

    @classmethod
    def decode(cls, data: bytes, media_path: MediaPath):
        ds = []
        for s in cls.read_segments(data, media_path):
            ds.append(s)
            if s.type == 'END':
                yield DisplaySet(ds)
                ds = []


class PgsImage:

    def __init__(self, data: bytes, palettes: typing.List[Palette]):
        self.rle_data = data
        self.palettes = palettes
        self._data: typing.Optional[ndarray] = None

    @property
    def data(self):
        if self._data is None:
            self._data = self.decode_rle_image(self.rle_data, self.palettes)
        return self._data

    @classmethod
    def decode_rle_image(cls, data: bytes, palettes: typing.List[Palette], binary=True):
        image_array: typing.List[int] = []
        alpha_array: typing.List[int] = []
        dimension = 1 if binary else 3
        cols = 1
        i = 0
        while i < len(data):
            length, color, count = cls.decode_rle_position(data, i)
            if not length and cols < 2:
                cols = len(image_array) // dimension
            palette = palettes[color]
            image_color = cls.get_color(palette, binary)
            image_array.extend(image_color * length)
            if not binary:
                alpha_array.extend([palette[3]] * length)
            i += count

        rows = (len(image_array) // dimension + cols - 1) // cols
        if cols * rows * dimension != len(image_array):
            # corrupted image
            delta = cols * rows * dimension - len(image_array)
            image_array.extend((cls.get_color(palettes[0], binary) * dimension) * delta)

        image = np.array(image_array, dtype=np.uint8).reshape((rows, cols) if binary else (rows, cols, dimension))
        if binary:
            return image

        image = cv2.cvtColor(image, cv2.COLOR_YCR_CB2BGR)
        a_channel = np.array(alpha_array, dtype=np.uint8).reshape(rows, cols)
        b_channel, g_channel, r_channel = cv2.split(image)
        image = cv2.merge((b_channel, g_channel, r_channel, a_channel))
        return image

    @classmethod
    def get_color(cls, palette: Palette, binary: bool):
        return ([0] if palette[0] > 127 else [255]) if binary else palette[:3]

    @classmethod
    def decode_rle_position(cls, data: bytes, i: int):
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

    @property
    def shape(self):
        return self.data.shape


class BaseSegment:
    SEGMENT = {
        PDS: 'PDS',
        ODS: 'ODS',
        PCS: 'PCS',
        WDS: 'WDS',
        END: 'END'
    }

    def __init__(self, b: bytes):
        self.bytes = b

    def __len__(self):
        return self.size

    @property
    def presentation_timestamp(self):
        return from_hex(self.bytes[2:6]) / 90

    @property
    def decoding_timestamp(self):
        return from_hex(self.bytes[6:10]) / 90

    @property
    def type(self):
        return self.SEGMENT[self.bytes[10]]

    @property
    def size(self):
        return from_hex(self.bytes[11:13])

    @property
    def data(self):
        return self.bytes[13:]


class PresentationCompositionSegment(BaseSegment):
    STATE = {
        from_hex(b'\x00'): 'Normal',
        from_hex(b'\x40'): 'Acquisition Point',
        from_hex(b'\x80'): 'Epoch Start'
    }

    @property
    def width(self):
        return from_hex(self.data[0:2])

    @property
    def height(self):
        return from_hex(self.data[2:4])

    @property
    def frame_rate(self):
        return self.data[4]

    @property
    def _num(self):
        return from_hex(self.data[5:7])

    @property
    def _state(self):
        return self.STATE[self.data[7]]

    @property
    def palette_update(self):
        return bool(self.data[8])

    @property
    def palette_id(self):
        return self.data[9]

    @property
    def _num_comps(self):
        return self.data[10]


class WindowDefinitionSegment(BaseSegment):

    @property
    def num_windows(self):
        return self.data[0]

    @property
    def window_id(self):
        return self.data[1]

    @property
    def x_offset(self):
        return from_hex(self.data[2:4])

    @property
    def y_offset(self):
        return from_hex(self.data[4:6])

    @property
    def width(self):
        return from_hex(self.data[6:8])

    @property
    def height(self):
        return from_hex(self.data[8:10])


class PaletteDefinitionSegment(BaseSegment):

    def __init__(self, b: bytes):
        super().__init__(b)
        self.palettes = [Palette(0, 0, 0, 0)] * 256
        # Slice from byte 2 til end of segment. Divide by 5 to determine number of palette entries
        # Iterate entries. Explode the 5 bytes into namedtuple Palette. Must be exploded
        for entry in range(len(self.data[2:]) // 5):
            i = 2 + entry * 5
            self.palettes[self.data[i]] = Palette(*self.data[i + 1:i + 5])

    @property
    def palette_id(self):
        return self.data[0]

    @property
    def version(self):
        return self.data[1]


class ObjectDefinitionSegment(BaseSegment):
    SEQUENCE = {
        from_hex(b'\x40'): 'Last',
        from_hex(b'\x80'): 'First',
        from_hex(b'\xc0'): 'First and last'
    }

    @property
    def id(self):
        return from_hex(self.data[0:2])

    @property
    def version(self):
        return self.data[2]

    @property
    def in_sequence(self):
        return self.SEQUENCE[self.data[3]]

    @property
    def data_len(self):
        return from_hex(self.data[4:7])

    @property
    def width(self):
        return from_hex(self.data[7:9])

    @property
    def height(self):
        return from_hex(self.data[9:11])

    @property
    def img_data(self):
        return self.data[11:]

    def check_corruption(self):
        if len(self.img_data) != self.data_len - 4:
            return f'Found {len(self.img_data)} bytes for image, but {self.data_len - 4} were expected'


class EndSegment(BaseSegment):

    @property
    def is_end(self):
        return True


SEGMENT_TYPE = {
    PDS: PaletteDefinitionSegment,
    ODS: ObjectDefinitionSegment,
    PCS: PresentationCompositionSegment,
    WDS: WindowDefinitionSegment,
    END: EndSegment
}


class DisplaySet:

    def __init__(self, segments):
        self.segments = segments
        self.pds = [s for s in self.segments if s.type == 'PDS']
        self.ods = [s for s in self.segments if s.type == 'ODS']
        self.pcs = [s for s in self.segments if s.type == 'PCS']
        self.wds = [s for s in self.segments if s.type == 'WDS']
        self.end = [s for s in self.segments if s.type == 'END']
        self.has_image = bool(self.ods)
