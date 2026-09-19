"""Rip your PGS subtitles."""

from importlib import metadata

__title__ = metadata.metadata(__package__)['name']
__version__ = metadata.version(__package__)
__short_version__ = '.'.join(__version__.split('.')[:2])
__author__ = metadata.metadata(__package__)['author']
__license__ = metadata.metadata(__package__)['license-expression']
__url__ = 'https://github.com/ratoaq2/pgsrip'

del metadata

from . import api as pgsrip
from .media import Media as Media
from .media import Pgs as Pgs
from .mkv import Mkv as Mkv
from .options import Options as Options
from .sup import Sup as Sup
