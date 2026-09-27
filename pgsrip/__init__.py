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
from .media import Pgs as Pgs
from .options import Options as Options
from .sources.base import Media as Media
from .sources.base import Source as Source
from .sources.base import Track as Track
