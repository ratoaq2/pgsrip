import os

import pytest

from .fabricate import BACKENDS


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
