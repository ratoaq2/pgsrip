import logging

from pgsrip import core
from pgsrip.media import Media, Pgs
from pgsrip.options import Options

logger = logging.getLogger(__name__)


def scan_path(path: str, options: Options | None = None) -> tuple[list[Media], list[str], list[str]]:
    collected: list[Media] = []
    filtered_out: list[str] = []
    discarded: list[str] = []
    core.scan_path(path, collected, filtered_out, discarded, options=options or Options())

    return collected, filtered_out, discarded


def rip(media: Media, options: Options | None = None) -> int:
    return core.rip(media, options or Options())


def rip_pgs(pgs: Pgs, options: Options | None = None) -> bool:
    return core.rip_pgs(pgs, options or Options())
