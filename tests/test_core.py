import json
import os
from subprocess import CalledProcessError

import pytest
from babelfish import Language

from pgsrip.api import rip_pgs, scan_path
from pgsrip.core import get_reason
from pgsrip.media import Pgs
from pgsrip.media_path import MediaPath
from pgsrip.mkv import Mkv
from pgsrip.options import Options


@pytest.fixture
def mkvmerge(monkeypatch):
    def use(tracks=(), error=None):
        def check_output(cmd, *args, **kwargs):
            if error:
                raise error
            return json.dumps({'tracks': list(tracks)}).encode()

        monkeypatch.setattr('pgsrip.mkv.check_output', check_output)

    return use


def pgs_track(track_id=0, language='eng', **properties):
    return {
        'id': track_id,
        'type': 'subtitles',
        'codec': 'HDMV PGS',
        'properties': {'language': language, 'enabled_track': True, **properties},
    }


def create_file(directory, name):
    path = os.path.join(str(directory), name)
    with open(path, 'wb') as f:
        f.write(b'')

    return path


def test_scan_path_discards_non_existent_path():
    collected, filtered_out, discarded = scan_path('/no/such/media.mkv')

    assert not collected
    assert not filtered_out
    assert get_reason(discarded[0]) == 'path does not exist'


def test_scan_path_discards_unsupported_extension(tmp_path):
    path = create_file(tmp_path, 'mymedia.mp4')

    collected, _, discarded = scan_path(path)

    assert not collected
    assert discarded == [path]
    assert get_reason(discarded[0]) == 'unsupported extension, expected one of .mks, .mkv, .sup'


def test_scan_path_discards_when_mkvmerge_is_missing(tmp_path, mkvmerge):
    mkvmerge(error=FileNotFoundError('mkvmerge'))
    path = create_file(tmp_path, 'mymedia.mkv')

    collected, _, discarded = scan_path(path)

    assert not collected
    assert get_reason(discarded[0]) == 'mkvmerge not found, install MKVToolNix and make sure that it is in the PATH'


def test_scan_path_discards_when_mkvmerge_fails(tmp_path, mkvmerge):
    mkvmerge(error=CalledProcessError(2, 'mkvmerge'))
    path = create_file(tmp_path, 'mymedia.mkv')

    collected, _, discarded = scan_path(path)

    assert not collected
    assert get_reason(discarded[0]) == 'mkvmerge could not read the file (exit code 2)'


def test_scan_path_filters_out_other_languages(tmp_path, mkvmerge):
    mkvmerge(tracks=[pgs_track(language='eng'), pgs_track(track_id=1, language='deu')])
    path = create_file(tmp_path, 'mymedia.mkv')

    collected, filtered_out, discarded = scan_path(path, Options(languages={Language('fra')}))

    assert not collected
    assert not discarded
    assert get_reason(filtered_out[0]) == 'no track for the selected languages (available: de, en)'


def test_scan_path_collects_supported_media(tmp_path, mkvmerge):
    mkvmerge(tracks=[pgs_track()])
    path = create_file(tmp_path, 'mymedia.mkv')

    collected, filtered_out, discarded = scan_path(path)

    assert [str(m.media_path) for m in collected] == [path]
    assert not filtered_out
    assert not discarded


def test_scan_path_walks_directories_without_discarding_other_files(tmp_path, mkvmerge):
    mkvmerge(tracks=[pgs_track()])
    create_file(tmp_path, 'mymedia.mkv')
    create_file(tmp_path, 'mymedia.nfo')

    collected, filtered_out, discarded = scan_path(str(tmp_path))

    assert len(collected) == 1
    assert not filtered_out
    assert not discarded


def test_rip_pgs_reports_the_error_it_failed_with(tmp_path):
    temp_folder = tmp_path / 'temp'
    temp_folder.mkdir()
    media_path = MediaPath(str(tmp_path / 'mymedia.en.sup'))
    pgs = Pgs(media_path, Options(), lambda: b'', str(temp_folder))
    errors = []

    assert rip_pgs(pgs, Options(), on_error=lambda p, e: errors.append((p, e))) is False
    assert [(p, type(e)) for p, e in errors] == [(pgs, ValueError)]


def test_rip_pgs_points_at_the_media_the_subtitle_came_from(tmp_path):
    media_path = MediaPath(str(tmp_path / 'mymedia.en.sup'))

    pgs = Pgs(media_path, Options(), lambda: b'', str(tmp_path))

    assert str(pgs.source_path) == str(media_path)


def test_get_pgs_medias_disambiguates_only_a_real_language_and_flags_collision(tmp_path, mkvmerge):
    mkvmerge(
        tracks=[
            pgs_track(track_id=0, language='eng'),
            pgs_track(track_id=1, language='eng', flag_hearing_impaired=True),
            pgs_track(track_id=2, language='eng'),
            pgs_track(track_id=3, language='deu'),
        ]
    )
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(Mkv(path).get_pgs_medias(Options(one_per_lang=False)))

    assert sorted(os.path.basename(str(m.srt_path)) for m in medias) == sorted(
        ['movie.en.track0.srt', 'movie.en.sdh.srt', 'movie.en.track2.srt', 'movie.de.srt']
    )


def test_get_pgs_medias_keeps_different_flag_combinations_for_the_same_language_by_default(tmp_path, mkvmerge):
    mkvmerge(
        tracks=[
            pgs_track(track_id=0, language='eng'),
            pgs_track(track_id=1, language='eng', flag_hearing_impaired=True),
        ]
    )
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(Mkv(path).get_pgs_medias(Options()))

    assert sorted(os.path.basename(str(m.srt_path)) for m in medias) == ['movie.en.sdh.srt', 'movie.en.srt']


def test_get_pgs_medias_track_id_is_stable_regardless_of_one_per_lang(tmp_path, mkvmerge):
    mkvmerge(
        tracks=[
            pgs_track(track_id=0, language='eng'),
            pgs_track(track_id=2, language='eng'),
        ]
    )
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(Mkv(path).get_pgs_medias(Options(one_per_lang=True)))

    assert [os.path.basename(str(m.srt_path)) for m in medias] == ['movie.en.track0.srt']


def test_get_pgs_medias_excludes_flagged_tracks(tmp_path, mkvmerge):
    mkvmerge(
        tracks=[
            pgs_track(track_id=0, language='eng'),
            pgs_track(track_id=1, language='eng', flag_commentary=True),
        ]
    )
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(Mkv(path).get_pgs_medias(Options(one_per_lang=False, exclude_flags=frozenset({'commentary'}))))

    assert [os.path.basename(str(m.srt_path)) for m in medias] == ['movie.en.srt']


def test_get_pgs_medias_includes_forced_or_full_tracks(tmp_path, mkvmerge):
    mkvmerge(
        tracks=[
            pgs_track(track_id=0, language='eng', forced_track=True),
            pgs_track(track_id=1, language='eng', flag_hearing_impaired=True),
            pgs_track(track_id=2, language='eng'),
        ]
    )
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(Mkv(path).get_pgs_medias(Options(one_per_lang=False, include_flags=frozenset({'forced', 'full'}))))

    assert sorted(os.path.basename(str(m.srt_path)) for m in medias) == ['movie.en.forced.srt', 'movie.en.srt']


def test_get_pgs_medias_includes_sdh_for_the_selected_language_only(tmp_path, mkvmerge):
    mkvmerge(
        tracks=[
            pgs_track(track_id=0, language='eng', flag_hearing_impaired=True),
            pgs_track(track_id=1, language='eng'),
            pgs_track(track_id=2, language='deu', flag_hearing_impaired=True),
        ]
    )
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(Mkv(path).get_pgs_medias(Options(languages={Language('eng')}, include_flags=frozenset({'sdh'}))))

    assert [os.path.basename(str(m.srt_path)) for m in medias] == ['movie.en.sdh.srt']


def test_get_pgs_medias_exclude_wins_over_include(tmp_path, mkvmerge):
    mkvmerge(tracks=[pgs_track(track_id=0, language='eng', forced_track=True, flag_commentary=True)])
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(
        Mkv(path).get_pgs_medias(Options(include_flags=frozenset({'forced'}), exclude_flags=frozenset({'commentary'})))
    )

    assert not medias


def test_get_pgs_medias_track_id_is_stable_regardless_of_with_without_filtering(tmp_path, mkvmerge):
    mkvmerge(
        tracks=[
            pgs_track(track_id=0, language='eng'),
            pgs_track(track_id=2, language='eng'),
            pgs_track(track_id=5, language='eng', flag_commentary=True),
        ]
    )
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(Mkv(path).get_pgs_medias(Options(one_per_lang=False, exclude_flags=frozenset({'commentary'}))))

    assert sorted(os.path.basename(str(m.srt_path)) for m in medias) == ['movie.en.track0.srt', 'movie.en.track2.srt']


def test_get_pgs_medias_one_per_language_ignores_flags(tmp_path, mkvmerge):
    mkvmerge(
        tracks=[
            pgs_track(track_id=0, language='eng'),
            pgs_track(track_id=1, language='eng', flag_hearing_impaired=True),
        ]
    )
    path = create_file(tmp_path, 'movie.mkv')

    medias = list(Mkv(path).get_pgs_medias(Options(one_per_language=True)))

    assert [os.path.basename(str(m.srt_path)) for m in medias] == ['movie.en.srt']
