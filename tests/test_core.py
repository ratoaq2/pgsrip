import json
import os
from subprocess import CalledProcessError

import pytest
from babelfish import Language

from pgsrip.api import scan_path
from pgsrip.core import get_reason
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


def pgs_track(track_id=0, language='eng'):
    return {
        'id': track_id,
        'type': 'subtitles',
        'codec': 'HDMV PGS',
        'properties': {'language': language, 'enabled_track': True},
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
