# -*- coding: utf-8 -*-
"""Rip your PGS subtitles."""
from importlib import metadata

from . import api as pgsrip
from .options import Options
from .media import Media, Pgs
from .sup import Sup
from .mkv import Mkv


__title__ = metadata.metadata(__package__)['name']
__version__ = metadata.version(__package__)
__short_version__ = '.'.join(__version__.split('.')[:2])
__author__ = metadata.metadata(__package__)['author']
__license__ = metadata.metadata(__package__)['license']
__url__ = metadata.metadata(__package__)['home_page']

del metadata
