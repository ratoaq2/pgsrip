"""Rip your PGS subtitles."""

from importlib import metadata

from .api import ScanResult as ScanResult
from .api import Skipped as Skipped
from .api import pending as pending
from .api import prepare as prepare
from .api import rip as rip
from .api import scan as scan
from .errors import PgsripError as PgsripError
from .media import Media as Media
from .media import Subtitle as Subtitle
from .media import Workspace as Workspace
from .options import Options as Options

__version__ = metadata.version(__package__)
__url__ = 'https://github.com/ratoaq2/pgsrip'

del metadata
