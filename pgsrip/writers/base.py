from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from pgsrip.cue import Cue
    from pgsrip.sources.base import Track


class Writer(typing.Protocol):
    """Writes the cues of a track to a file. `pgsrip.writers.WRITERS` is the built-in list."""

    #: the value of --format
    name: typing.ClassVar[str]
    #: the file extension, without the dot
    extension: typing.ClassVar[str]

    def write(self, path: str, cues: list[Cue], track: Track, encoding: str | None) -> None:
        """Write the cues. A cue with no text is left out. The writer prepares the text for its format."""
