"""Rip your PGS subtitles."""
from importlib import metadata

__title__ = metadata.metadata(__package__)['name']
__version__ = metadata.version(__package__)
__short_version__ = '.'.join(__version__.split('.')[:2])
__author__ = metadata.metadata(__package__)['author']
__license__ = metadata.metadata(__package__)['license']
__url__ = metadata.metadata(__package__)['home_page']

del metadata

from . import api as pgsrip
from .media import Media, Pgs
from .mkv import Mkv
from .options import Options
from .sup import Sup
