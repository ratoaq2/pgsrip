from pgsrip.diagnostics import Check
from pgsrip.sources.base import Source
from pgsrip.sources.mkvtoolnix import MkvToolNixSource
from pgsrip.sources.raw import RawSource

#: the built-in sources, in order of preference: a media uses the first one that is installed
SOURCES: tuple[type[Source], ...] = (MkvToolNixSource, RawSource)
EXTENSIONS = tuple(dict.fromkeys(extension for source in SOURCES for extension in source.extensions))


def source_checks() -> list[Check]:
    """The lines of `pgsrip doctor` for all the sources."""
    return [check for source in SOURCES for check in source.check()]
