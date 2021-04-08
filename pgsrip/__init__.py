# -*- coding: utf-8 -*-
"""Rip your PGS subtitles."""
from . import api as pgsrip
from .options import Options
from .media import Media, Pgs
from .sup import Sup
from .mkv import Mkv

__title__ = 'pgsrip'
__version__ = '0.1.1'
__short_version__ = '.'.join(__version__.split('.')[:2])
__author__ = 'Rato AQ2'
__license__ = 'MIT'
__copyright__ = 'Copyright 2021, Rato AQ2'
__url__ = 'https://github.com/ratoaq2/pgsrip'
