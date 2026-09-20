from babelfish import Language

from pgsrip.media_path import MediaPath


def test_media_path_reads_a_language_suffix():
    media_path = MediaPath('/media/movie.en.mkv')

    assert media_path.language == Language('eng')
    assert media_path.base_path == '/media/movie'
    assert media_path.extension == 'mkv'


def test_media_path_keeps_a_release_tag_that_looks_like_a_language():
    media_path = MediaPath('/media/Title.YYYY.S01E10.1080p.BluRay.AVC.DTS.mkv')

    assert media_path.language == Language('und')
    assert media_path.base_path == '/media/Title.YYYY.S01E10.1080p.BluRay.AVC.DTS'
    assert str(media_path) == '/media/Title.YYYY.S01E10.1080p.BluRay.AVC.DTS.mkv'


def test_media_path_defaults_to_undetermined_language():
    media_path = MediaPath('/media/movie.mkv')

    assert media_path.language == Language('und')
    assert media_path.base_path == '/media/movie'
