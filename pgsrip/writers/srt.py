from __future__ import annotations

import typing

from pysrt import SubRipFile, SubRipItem, SubRipTime

if typing.TYPE_CHECKING:
    from pgsrip.media import Pgs
    from pgsrip.ripper import Cue


class SrtWriter:
    """Writes a SubRip file with pysrt. The cues are sorted by time."""

    name: typing.ClassVar[str] = 'srt'
    extension: typing.ClassVar[str] = 'srt'

    def write(self, path: str, pgs: Pgs, cues: list[Cue], encoding: str | None) -> None:
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
