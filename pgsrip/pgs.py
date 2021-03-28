# -*- coding: utf-8 -*-
import logging
from typing import NamedTuple, List, Optional

import cv2
import numpy as np
from numpy import ndarray

logger = logging.getLogger(__name__)


# Constants for Segments
PDS = int('0x14', 16)
ODS = int('0x15', 16)
PCS = int('0x16', 16)
WDS = int('0x17', 16)
END = int('0x80', 16)


class Palette(NamedTuple):
    y: int
    cr: int
    cb: int
    alpha: int


class PgsReader:

    @classmethod
    def read_segments(cls, data: bytes):
        count = 0
        b = data[:]
        while b:
            size = 13 + int(b[11:13].hex(), 16)
            yield SEGMENT_TYPE[b[10]](b[:size])
            count += size
            b = b[size:]

    @classmethod
    def create_display_sets(cls, segments):
        ds = []
        for s in segments:
            ds.append(s)
            if s.type == 'END':
                yield DisplaySet(ds)
                ds = []


class PgsImage:

    def __init__(self, data: bytes, palettes: List[Palette]):
        self.rle_data = data
        self.palettes = palettes
        self._data: Optional[ndarray] = None

    @property
    def data(self):
        if self._data is None:
            self._data = self.decode_rle_image(self.rle_data, self.palettes)
        return self._data

    @classmethod
    def decode_rle_image(cls, data: bytes, palettes: List[Palette], binary=True):
        image_array = []
        alpha_array = []
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
        if data[i]:
            return 1, data[i], 1
        if len(data) < i + 2:
            # corrupted image
            return 0, 0, 2

        check = data[i + 1]
        if check == 0:
            return 0, 0, 2
        elif check < 64:
            return check, 0, 2
        elif len(data) < i + 3:
            # corrupted image
            return 0, 0, 4
        elif check < 128:
            return ((check - 64) << 8) + data[i + 2], 0, 3
        elif check < 192:
            return check - 128, data[i + 2], 3

        return ((check - 192) << 8) + data[i + 2], data[i + 3], 4

    @property
    def shape(self):
        return self.data.shape


class InvalidSegmentError(Exception):
    """Raised when a segment does not match PGS specification"""


class BaseSegment:
    SEGMENT = {
        PDS: 'PDS',
        ODS: 'ODS',
        PCS: 'PCS',
        WDS: 'WDS',
        END: 'END'
    }

    def __init__(self, bytes_):
        self.bytes = bytes_
        if bytes_[:2] != b'PG':
            raise InvalidSegmentError
        self.pts = int(bytes_[2:6].hex(), base=16) / 90
        self.dts = int(bytes_[6:10].hex(), base=16) / 90
        self.type = self.SEGMENT[bytes_[10]]
        self.size = int(bytes_[11:13].hex(), base=16)
        self.data = bytes_[13:]

    def __len__(self):
        return self.size

    @property
    def presentation_timestamp(self):
        return self.pts

    @property
    def decoding_timestamp(self):
        return self.dts

    @property
    def segment_type(self):
        return self.type


class PresentationCompositionSegment(BaseSegment):
    STATE = {
        int('0x00', base=16): 'Normal',
        int('0x40', base=16): 'Acquisition Point',
        int('0x80', base=16): 'Epoch Start'
    }

    def __init__(self, bytes_):
        super().__init__(bytes_)
        self.width = int(self.data[0:2].hex(), base=16)
        self.height = int(self.data[2:4].hex(), base=16)
        self.frame_rate = self.data[4]
        self._num = int(self.data[5:7].hex(), base=16)
        self._state = self.STATE[self.data[7]]
        self.palette_update = bool(self.data[8])
        self.palette_id = self.data[9]
        self._num_comps = self.data[10]


class WindowDefinitionSegment(BaseSegment):

    def __init__(self, bytes_):
        BaseSegment.__init__(self, bytes_)
        self.num_windows = self.data[0]
        self.window_id = self.data[1]
        self.x_offset = int(self.data[2:4].hex(), base=16)
        self.y_offset = int(self.data[4:6].hex(), base=16)
        self.width = int(self.data[6:8].hex(), base=16)
        self.height = int(self.data[8:10].hex(), base=16)


class PaletteDefinitionSegment(BaseSegment):

    def __init__(self, bytes_):
        BaseSegment.__init__(self, bytes_)
        self.palette_id = self.data[0]
        self.version = self.data[1]
        self.palettes = [Palette(0, 0, 0, 0)] * 256
        # Slice from byte 2 til end of segment. Divide by 5 to determine number of palette entries
        # Iterate entries. Explode the 5 bytes into namedtuple Palette. Must be exploded
        for entry in range(len(self.data[2:]) // 5):
            i = 2 + entry * 5
            self.palettes[self.data[i]] = Palette(*self.data[i + 1:i + 5])


class ObjectDefinitionSegment(BaseSegment):
    SEQUENCE = {
        int('0x40', base=16): 'Last',
        int('0x80', base=16): 'First',
        int('0xc0', base=16): 'First and last'
    }

    def __init__(self, bytes_):
        BaseSegment.__init__(self, bytes_)
        self.id = int(self.data[0:2].hex(), base=16)
        self.version = self.data[2]
        self.in_sequence = self.SEQUENCE[self.data[3]]
        self.data_len = int(self.data[4:7].hex(), base=16)
        self.width = int(self.data[7:9].hex(), base=16)
        self.height = int(self.data[9:11].hex(), base=16)
        self.img_data = self.data[11:]

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
