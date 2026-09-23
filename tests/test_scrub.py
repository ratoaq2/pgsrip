import os

import numpy as np
import pytest
from babelfish import Language

from pgsrip.media_path import MediaPath
from pgsrip.pgs import ObjectDefinitionSegment, PgsImage, PgsReader, SegmentType
from pgsrip.scrub import Redaction, encode_runs, output_path, scrub_data, to_runs
from pgsrip.track_flags import TrackFlags

WIDTH = 64
HEIGHT = 8
# a bright entry is decoded as ink, a dark one as background
PALETTES = ((1, 255, 128, 128, 255), (2, 16, 128, 128, 255))


def segment(segment_type, data, pts=0):
    return (
        b'PG' + pts.to_bytes(4, 'big') + b'\x00' * 4 + bytes([segment_type.value]) + len(data).to_bytes(2, 'big') + data
    )


def pcs(width=1920, height=1080, number=0, state=0x80):
    data = width.to_bytes(2, 'big') + height.to_bytes(2, 'big') + b'\x10' + number.to_bytes(2, 'big')

    return data + bytes([state, 0, 0, 0])


def wds(x=100, y=900, width=WIDTH, height=HEIGHT):
    data = b'\x01\x00' + x.to_bytes(2, 'big') + y.to_bytes(2, 'big')

    return data + width.to_bytes(2, 'big') + height.to_bytes(2, 'big')


def pds(palettes=PALETTES):
    return b'\x00\x00' + b''.join(bytes(palette) for palette in palettes)


def ods(image_data, width=WIDTH, height=HEIGHT, sequence_type=0xC0):
    data = b'\x00\x00\x00' + bytes([sequence_type]) + (len(image_data) + 4).to_bytes(3, 'big')

    return data + width.to_bytes(2, 'big') + height.to_bytes(2, 'big') + image_data


def text_image_data():
    """Run length data of an image with ink on it, standing in for a real subtitle."""
    rows = [[(0, WIDTH)] if row % 2 else [(0, 8), (1, WIDTH - 16), (0, 8)] for row in range(HEIGHT)]

    return encode_runs(rows)


def display_set(number=0, pts=0, image_data=None, sequence_type=0xC0):
    return b''.join(
        [
            segment(SegmentType.PCS, pcs(number=number), pts=pts),
            segment(SegmentType.WDS, wds(), pts=pts),
            segment(SegmentType.PDS, pds(), pts=pts),
            segment(SegmentType.ODS, ods(image_data or text_image_data(), sequence_type=sequence_type), pts=pts),
            segment(SegmentType.END, b'', pts=pts),
        ]
    )


@pytest.fixture
def media_path():
    return MediaPath('mymedia.en.sup')


@pytest.fixture
def stream():
    return b''.join(display_set(number=i, pts=i * 90000) for i in range(3))


def decode(data, media_path):
    return list(PgsReader.decode(data, media_path))


def images(display_sets):
    data = []
    for ds in display_sets:
        image_data = b''.join(s.img_data for s in ds.segments if isinstance(s, ObjectDefinitionSegment))
        data.append(PgsImage(image_data, list(ds.pds_segments[0].palettes)))

    return data


def test_encoded_runs_are_decoded_back(media_path):
    rows = [[(0, 3), (1, 5), (0, 92)], [(1, 100)], [(0, 100)]]

    image = PgsImage(encode_runs(rows), [(0, 0, 0, 0)] * 256)

    assert image.shape == (3, 100)


def test_to_runs_groups_equal_values():
    assert to_runs(np.array([0, 0, 1, 1, 1, 0], dtype=np.uint8)) == [(0, 2), (1, 3), (0, 1)]


def test_scrub_keeps_every_display_set(stream, media_path):
    scrubbed, stats = scrub_data(stream, media_path)

    assert stats.display_sets == 3
    assert stats.written_display_sets == 3
    assert stats.redacted_objects == 3
    assert len(decode(scrubbed, media_path)) == 3


def test_scrub_keeps_timing_and_geometry(stream, media_path):
    scrubbed, _ = scrub_data(stream, media_path)

    original = decode(stream, media_path)
    result = decode(scrubbed, media_path)
    assert [ds.pcs.to_json() for ds in result] == [ds.pcs.to_json() for ds in original]
    assert [ds.wds.to_json() for ds in result] == [ds.wds.to_json() for ds in original]
    assert [ds.pds_segments[0].palettes for ds in result] == [ds.pds_segments[0].palettes for ds in original]
    assert [ds.ods_segments[0].width for ds in result] == [ds.ods_segments[0].width for ds in original]
    assert [ds.ods_segments[0].height for ds in result] == [ds.ods_segments[0].height for ds in original]


def test_scrub_removes_the_text(stream, media_path):
    scrubbed, _ = scrub_data(stream, media_path)

    assert images(decode(stream, media_path))[0].data.min() == 0
    for image in images(decode(scrubbed, media_path)):
        assert image.shape == (HEIGHT, WIDTH)
        # nothing is left to recognize: every pixel is background
        assert image.data.min() == 255


def test_scrub_is_smaller_than_the_original(stream, media_path):
    scrubbed, stats = scrub_data(stream, media_path)

    assert stats.size == len(scrubbed)
    assert len(scrubbed) < len(stream)


def test_scrub_draws_placeholder_text(stream, media_path):
    scrubbed, _ = scrub_data(stream, media_path, redaction=Redaction.SYNTHETIC)

    for image in images(decode(scrubbed, media_path)):
        assert image.shape == (HEIGHT, WIDTH)
        # there is ink on the image, but it is not the ink of the original subtitle
        assert image.data.min() == 0

    assert scrubbed != stream


def test_scrub_keeps_the_images_of_the_selected_display_sets(stream, media_path):
    scrubbed, stats = scrub_data(stream, media_path, keep_images={1})

    assert stats.redacted_objects == 2
    kept = images(decode(scrubbed, media_path))[1]
    assert kept.data.min() == 0


def test_scrub_writes_only_the_selected_display_sets(stream, media_path):
    scrubbed, stats = scrub_data(stream, media_path, only={1, 2})

    assert stats.display_sets == 3
    assert stats.written_display_sets == 2
    assert [ds.pcs.composition_number for ds in decode(scrubbed, media_path)] == [1, 2]


def test_scrub_keeps_nothing_out_when_redaction_is_none(stream, media_path):
    scrubbed, stats = scrub_data(stream, media_path, redaction=Redaction.NONE)

    assert scrubbed == stream
    assert stats.redacted_objects == 0


def test_scrub_keeps_a_corrupted_object_header(media_path):
    # an object sequence type of 1 is invalid and is what pgsrip has to be able to reproduce
    stream = display_set(sequence_type=0x01)

    scrubbed, stats = scrub_data(stream, media_path)

    assert stats.redacted_objects == 1
    corrupted = decode(scrubbed, media_path)[0].ods_segments[0]
    with pytest.raises(ValueError):
        _ = corrupted.sequence_type
    assert corrupted.data == b'\x00\x00\x00\x01'


def test_scrub_keeps_an_object_split_over_two_segments(media_path):
    first = segment(SegmentType.ODS, ods(text_image_data(), sequence_type=0x80))
    last = segment(SegmentType.ODS, b'\x00\x00\x00\x40' + text_image_data())
    stream = b''.join(
        [
            segment(SegmentType.PCS, pcs()),
            segment(SegmentType.WDS, wds()),
            segment(SegmentType.PDS, pds()),
            first,
            last,
            segment(SegmentType.END, b''),
        ]
    )

    scrubbed, stats = scrub_data(stream, media_path)

    assert stats.objects == 2
    assert stats.redacted_objects == 2
    result = decode(scrubbed, media_path)[0]
    assert len(result.ods_segments) == 2
    assert images([result])[0].shape == (HEIGHT, WIDTH)


def test_scrub_keeps_an_object_split_over_three_segments(media_path):
    """Regression for #120: the middle segment has the sequence type 0x00 and only a 4 byte header."""
    first = segment(SegmentType.ODS, ods(text_image_data(), sequence_type=0x80))
    middle = segment(SegmentType.ODS, b'\x00\x00\x00\x00' + text_image_data())
    last = segment(SegmentType.ODS, b'\x00\x00\x00\x40' + text_image_data())
    stream = b''.join(
        [
            segment(SegmentType.PCS, pcs()),
            segment(SegmentType.WDS, wds()),
            segment(SegmentType.PDS, pds()),
            first,
            middle,
            last,
            segment(SegmentType.END, b''),
        ]
    )

    scrubbed, stats = scrub_data(stream, media_path)

    assert stats.redacted_objects == 3
    result = decode(scrubbed, media_path)[0]
    assert [s.data for s in result.ods_segments[1:]] == [b'\x00\x00\x00\x00', b'\x00\x00\x00\x40']
    assert images([result])[0].shape == (HEIGHT, WIDTH)


@pytest.mark.parametrize(
    'path, keep_name, expected',
    [
        ('mymedia.en.sup', True, 'mymedia.en.sup'),
        ('mymedia.mkv', True, 'mymedia.en.sup'),
        (os.path.join('medias', 'mymedia.en.sup'), True, 'mymedia.en.sup'),
        ('mymedia.en.sup', False, 'pgsrip-b47da897.en.sup'),
    ],
)
def test_output_path_does_not_repeat_the_language(path, keep_name, expected):
    media_path = MediaPath(path).translate(language=Language('eng'))

    assert output_path(media_path, None, keep_name, set()) == expected


def test_output_path_keeps_the_subtitle_flags(tmp_path):
    media_path = MediaPath('mymedia.mkv').translate(language=Language('eng'), flags=TrackFlags(forced=True))

    assert output_path(media_path, None, True, set()) == 'mymedia.en.forced.sup'


def test_output_path_never_reuses_a_path():
    used = set()
    media_path = MediaPath('mymedia.mkv').translate(language=Language('eng'))

    paths = [output_path(media_path, None, True, used) for _ in range(3)]

    assert paths == ['mymedia.en.sup', 'mymedia.en.track0.sup', 'mymedia.en.track1.sup']


def test_output_path_uses_the_given_directory(tmp_path):
    media_path = MediaPath('mymedia.mkv').translate(language=Language('eng'))

    assert output_path(media_path, str(tmp_path), True, set()) == str(tmp_path / 'mymedia.en.sup')


def test_output_path_uses_the_given_file_name():
    media_path = MediaPath('mymedia.mkv').translate(language=Language('eng'))

    assert output_path(media_path, 'report.sup', True, set()) == 'report.en.sup'
