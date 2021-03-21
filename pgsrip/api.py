# -*- coding: utf-8 -*-
import logging
from typing import List

from .media import Media, Pgs
from . import core
from .options import Options


logger = logging.getLogger(__name__)


def scan_path(path: str, options: Options = None):
    collected: List[Media] = []
    filtered_out: List[str] = []
    discarded: List[str] = []
    core.scan_path(path, collected, filtered_out, discarded, options=options or Options())

    return collected, filtered_out, discarded


def rip(media: Media, options: Options = None):
    return core.rip(media, options or Options())


def rip_pgs(pgs: Pgs, options: Options = None):
    return core.rip_pgs(pgs, options or Options())
