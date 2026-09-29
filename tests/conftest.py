import os
import shutil
import tempfile
import typing

import pytest

from .fabricate import BACKENDS, SAMPLE


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        '--media-backend',
        choices=(*BACKENDS, 'both'),
        default=os.environ.get('PGSRIP_MEDIA_BACKEND', 'fake'),
        help='Which MKV backend test_rip_e2e.py fabricates media with.',
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if 'media_backend' not in metafunc.fixturenames:
        return

    selected = metafunc.config.getoption('--media-backend')
    backends = BACKENDS if selected == 'both' else (selected,)
    metafunc.parametrize('media_backend', backends)


@pytest.fixture(autouse=True)
def user_config_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: typing.Any) -> typing.Any:
    """Never read the pgsrip configuration file of the user who runs the tests."""
    path = tmp_path / 'user-config'
    monkeypatch.setattr('pgsrip.cli.AppDirs.user_config_dir', str(path))
    return path


@pytest.fixture
def media_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: typing.Any) -> typing.Any:
    """A directory with the placeholder sample (3 cues), and a temporary directory of its own."""
    temp_dir = tmp_path / 'temp'
    temp_dir.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(temp_dir))
    media = tmp_path / 'media'
    media.mkdir()
    shutil.copy(SAMPLE, media)
    return media
