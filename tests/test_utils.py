import os

import pytest

from pgsrip.utils import cache_dir, format_time


@pytest.mark.parametrize(
    ('ms', 'text'),
    [
        pytest.param(0, '00:00:00,000', id='zero'),
        pytest.param(1, '00:00:00,001', id='one ms'),
        pytest.param(3_599_999, '00:59:59,999', id='last ms of the first hour'),
        pytest.param(3_600_001, '01:00:00,001', id='more than one hour'),
        pytest.param(360_000_000, '100:00:00,000', id='100 hours'),
        pytest.param(None, None, id='none'),
    ],
)
def test_format_time_gives_the_srt_format(ms: int | None, text: str | None) -> None:
    assert format_time(ms) == text


def test_the_cache_dir_is_in_the_user_cache_directory_of_pgsrip() -> None:
    # the same place as before appdirs, so that the downloaded data stays where it is
    assert cache_dir('tessdata').endswith(os.path.join('', 'pgsrip', 'tessdata'))
    assert 'Cache' not in cache_dir('tessdata').split(os.sep)
