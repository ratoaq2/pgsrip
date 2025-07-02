"""Rip your PGS subtitles."""
try:
    from importlib import metadata
    __title__ = metadata.metadata(__package__)['name']
    __version__ = metadata.version(__package__)
    __short_version__ = '.'.join(__version__.split('.')[:2])
    __author__ = metadata.metadata(__package__)['author']
    __license__ = metadata.metadata(__package__)['license']
    __url__ = metadata.metadata(__package__)['home_page']
    del metadata
except:
    # Fallback for development environment
    __title__ = 'pgsrip'
    __version__ = '1.0.0'
    __short_version__ = '1.0'
    __author__ = 'pgsrip'
    __license__ = 'MIT'
    __url__ = 'https://github.com/ratoaq2/pgsrip'

from . import api as pgsrip
from .media import Media, Pgs
from .mkv import Mkv
from .options import Options, SubtitleTypeFilter
from .sup import Sup
