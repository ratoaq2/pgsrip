from __future__ import annotations

import typing

from pysrt import SubRipFile, SubRipItem, SubRipTime

from pgsrip.writers.base import Writer

if typing.TYPE_CHECKING:
    from pgsrip.cue import Cue
    from pgsrip.sources.base import Track


class SrtWriter(Writer):
    """Writes a SubRip file with pysrt. The cues are sorted by time."""

    name: typing.ClassVar[str] = 'srt'
    extension: typing.ClassVar[str] = 'srt'

    def write(self, path: str, cues: list[Cue], track: Track, encoding: str | None) -> None:
        subs = SubRipFile(path=path)
        for cue in cues:
            if cue.text:
                subs.append(
                    SubRipItem(0, SubRipTime.from_ordinal(cue.start), SubRipTime.from_ordinal(cue.end), cue.text)
                )
        subs.clean_indexes()
        subs.save(encoding=encoding)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}>'
