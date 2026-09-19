import numpy as np
import pytest

from pgsrip.media_path import MediaPath
from pgsrip.pgs import ObjectDefinitionSegment, PgsImage, PgsReader, SegmentType
from pgsrip.scrub import Redaction, encode_runs, scrub_data, to_runs

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
    # an object sequence type of 0 is invalid and is what pgsrip has to be able to reproduce
    stream = display_set(sequence_type=0x00)

    scrubbed, stats = scrub_data(stream, media_path)

    assert stats.redacted_objects == 1
    corrupted = decode(scrubbed, media_path)[0].ods_segments[0]
    with pytest.raises(ValueError):
        _ = corrupted.sequence_type
    assert corrupted.data == b'\x00\x00\x00\x00'


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
