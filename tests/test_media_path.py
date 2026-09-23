import itertools

import pytest
from babelfish import Language

from pgsrip.media import Pgs
from pgsrip.media_path import MediaPath
from pgsrip.options import Options
from pgsrip.sup import Sup
from pgsrip.track_flags import TrackFlags

FLAG_FIELDS = ('forced', 'hearing_impaired', 'closed_caption', 'commentary', 'descriptive')

FLAG_COMBINATIONS = [
    TrackFlags(**dict(zip(FLAG_FIELDS, values, strict=True)), version=version)
    for values in itertools.product([False, True], repeat=len(FLAG_FIELDS))
    for version in [None, 'alternate']
]


def test_media_path_reads_a_language_suffix():
    media_path = MediaPath('/media/movie.en.mkv')

    assert media_path.language == Language('eng')
    assert media_path.base_path == '/media/movie'
    assert media_path.extension == 'mkv'
    assert media_path.flags == TrackFlags()
    assert media_path.track_id is None


def test_media_path_keeps_a_release_tag_that_looks_like_a_language():
    media_path = MediaPath('/media/Title.YYYY.S01E10.1080p.BluRay.AVC.DTS.mkv')

    assert media_path.language == Language('und')
    assert media_path.base_path == '/media/Title.YYYY.S01E10.1080p.BluRay.AVC.DTS'
    assert str(media_path) == '/media/Title.YYYY.S01E10.1080p.BluRay.AVC.DTS.mkv'
    assert media_path.flags == TrackFlags()
    assert media_path.track_id is None


def test_media_path_defaults_to_undetermined_language():
    media_path = MediaPath('/media/movie.mkv')

    assert media_path.language == Language('und')
    assert media_path.base_path == '/media/movie'


@pytest.mark.parametrize('flags', FLAG_COMBINATIONS)
def test_media_path_round_trips_every_flag_combination(flags):
    built = MediaPath('/media/movie.en.mkv').translate(flags=flags, extension='srt')

    parsed = MediaPath(str(built))

    assert parsed.base_path == '/media/movie'
    assert parsed.language == Language('eng')
    assert parsed.flags == flags
    assert parsed.track_id is None
    assert str(parsed) == str(built)


def test_media_path_renders_and_parses_a_track_id():
    built = MediaPath('/media/movie.en.mkv').translate(
        flags=TrackFlags(hearing_impaired=True), track_id=7, extension='srt'
    )

    assert str(built) == '/media/movie.en.sdh.track7.srt'

    parsed = MediaPath(str(built))

    assert parsed.base_path == '/media/movie'
    assert parsed.language == Language('eng')
    assert parsed.flags == TrackFlags(hearing_impaired=True)
    assert parsed.track_id == 7


@pytest.mark.parametrize(
    'tag',
    ['en-US', 'es-419', 'zh-Hans', 'pt-BR'],
)
def test_media_path_round_trips_regional_and_script_language_tags(tag):
    media_path = MediaPath(f'/media/movie.{tag}.srt')

    assert str(media_path.language) == tag
    assert media_path.base_path == '/media/movie'
    assert str(media_path) == f'/media/movie.{tag}.srt'


def test_media_path_translate_leaves_flags_and_track_id_as_is_when_not_given():
    media_path = MediaPath('/media/movie.en.sdh.track7.srt')

    translated = media_path.translate(extension='srt')

    assert translated.flags == media_path.flags
    assert translated.track_id == media_path.track_id
    assert str(translated) == str(media_path)


def test_srt_path_matches_the_ripper_write_path_for_a_flagged_track():
    media_path = MediaPath('/media/movie.mkv').translate(
        language=Language('eng'), flags=TrackFlags(forced=True), track_id=7
    )
    pgs = Pgs(media_path, options=Options(), data_reader=lambda: b'', temp_folder='/tmp')

    # mirrors ripper.py's `SubRipFile(path=str(self.pgs.media_path.translate(extension='srt')))`
    ripper_write_path = pgs.media_path.translate(extension='srt')

    assert str(pgs.srt_path) == str(ripper_write_path)


@pytest.mark.parametrize('code', ['fre', 'ger', 'chi', 'dut'])
def test_media_path_keeps_the_name_of_a_source_with_a_three_letter_language(code):
    media_path = MediaPath(f'/media/movie.{code}.sup')

    assert str(media_path) == f'/media/movie.{code}.sup'


def test_sup_reads_a_source_with_a_three_letter_language(tmp_path):
    path = tmp_path / 'movie.fre.sup'
    path.write_bytes(b'PG')

    assert Sup(str(path)).media_path.get_data() == b'PG'


def test_media_path_translates_a_three_letter_language_to_the_canonical_name():
    media_path = MediaPath('/media/movie.fre.sup')

    assert str(media_path.translate(extension='srt')) == '/media/movie.fr.srt'
