from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from pgsrip.media import Pgs
    from pgsrip.ripper import Cue


class Writer(typing.Protocol):
    """Writes the cues of a track to a file. `pgsrip.writers.WRITERS` is the built-in list."""

    #: the value of --format
    name: typing.ClassVar[str]
    #: the file extension, without the dot
    extension: typing.ClassVar[str]

    def write(self, path: str, pgs: Pgs, cues: list[Cue], encoding: str | None) -> None:
        """Write the cues. A cue with no text is left out. The writer prepares the text for its format."""
