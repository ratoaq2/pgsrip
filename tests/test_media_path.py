import itertools
import warnings
from datetime import timedelta

import pytest
from babelfish import Language

from pgsrip.media import Extraction, Media, Subtitle
from pgsrip.media_path import MediaPath
from pgsrip.sources.base import Track
from pgsrip.sources.raw import RawSource
from pgsrip.track_flags import TrackFlags
from pgsrip.writers.srt import SrtWriter

FLAG_FIELDS = ('forced', 'hearing_impaired', 'closed_caption', 'commentary', 'descriptive')

FLAG_COMBINATIONS = [
    TrackFlags(**dict(zip(FLAG_FIELDS, values, strict=True)), alternate=alternate)
    for values in itertools.product([False, True], repeat=len(FLAG_FIELDS))
    for alternate in [False, True]
]


def test_media_path_reads_a_language_suffix():
    media_path = MediaPath('/media/movie.en.mkv')

    assert media_path.language == Language('eng')
    assert media_path.base_path == '/media/movie'
    assert media_path.extension == 'mkv'
    assert media_path.flags == TrackFlags()
    assert media_path.track_number is None


def test_media_path_keeps_a_release_tag_that_looks_like_a_language():
    media_path = MediaPath('/media/Title.YYYY.S01E10.1080p.BluRay.AVC.DTS.mkv')

    assert media_path.language == Language('und')
    assert media_path.base_path == '/media/Title.YYYY.S01E10.1080p.BluRay.AVC.DTS'
    assert str(media_path) == '/media/Title.YYYY.S01E10.1080p.BluRay.AVC.DTS.mkv'
    assert media_path.flags == TrackFlags()
    assert media_path.track_number is None


def test_media_path_defaults_to_undetermined_language():
    media_path = MediaPath('/media/movie.mkv')

    assert media_path.language == Language('und')
    assert media_path.base_path == '/media/movie'


@pytest.mark.parametrize('flags', FLAG_COMBINATIONS)
def test_media_path_round_trips_every_flag_combination(flags):
    built = MediaPath('/media/movie.en.mkv').replace(flags=flags, extension='srt')

    parsed = MediaPath(str(built))

    assert parsed.base_path == '/media/movie'
    assert parsed.language == Language('eng')
    assert parsed.flags == flags
    assert parsed.track_number is None
    assert str(parsed) == str(built)


def test_media_path_renders_and_parses_a_track_number():
    built = MediaPath('/media/movie.en.mkv').replace(
        flags=TrackFlags(hearing_impaired=True), track_number=7, extension='srt'
    )

    assert str(built) == '/media/movie.en.sdh.track7.srt'

    parsed = MediaPath(str(built))

    assert parsed.base_path == '/media/movie'
    assert parsed.language == Language('eng')
    assert parsed.flags == TrackFlags(hearing_impaired=True)
    assert parsed.track_number == 7


@pytest.mark.parametrize(
    'tag',
    ['en-US', 'es-419', 'zh-Hans', 'pt-BR'],
)
def test_media_path_round_trips_regional_and_script_language_tags(tag):
    media_path = MediaPath(f'/media/movie.{tag}.srt')

    assert str(media_path.language) == tag
    assert media_path.base_path == '/media/movie'
    assert str(media_path) == f'/media/movie.{tag}.srt'


def test_media_path_replace_leaves_flags_and_track_number_as_is_when_not_given():
    media_path = MediaPath('/media/movie.en.sdh.track7.srt')

    replaced = media_path.replace(extension='srt')

    assert replaced.flags == media_path.flags
    assert replaced.track_number == media_path.track_number
    assert str(replaced) == str(media_path)


def test_output_path_keeps_the_flags_and_the_track_number_and_takes_the_writer_extension():
    media_path = MediaPath('/media/movie.mkv').replace(
        language=Language('eng'), flags=TrackFlags(forced=True), track_number=7
    )
    track = Track(7, None, media_path.language, media_path.flags)
    subtitle = Subtitle(track, media_path, media_path, Extraction(RawSource(), media_path))

    assert str(subtitle.output_path(SrtWriter())) == '/media/movie.en.forced.track7.srt'


@pytest.mark.parametrize('code', ['fre', 'ger', 'chi', 'dut'])
def test_media_path_keeps_the_name_of_a_source_with_a_three_letter_language(code):
    media_path = MediaPath(f'/media/movie.{code}.sup')

    assert str(media_path) == f'/media/movie.{code}.sup'


def test_media_reads_a_sup_with_a_three_letter_language(tmp_path):
    path = tmp_path / 'movie.fre.sup'
    path.write_bytes(b'PG')

    assert str(Media(str(path)).path) == str(path)


def test_media_path_translates_a_three_letter_language_to_the_canonical_name():
    media_path = MediaPath('/media/movie.fre.sup')

    assert str(media_path.replace(extension='srt')) == '/media/movie.fr.srt'


def test_media_path_age_uses_no_deprecated_call(tmp_path):
    path = tmp_path / 'movie.en.srt'
    path.write_bytes(b'')

    with warnings.catch_warnings():
        warnings.simplefilter('error')
        age = MediaPath(str(path)).age

    assert timedelta(0) <= age < timedelta(minutes=1)
