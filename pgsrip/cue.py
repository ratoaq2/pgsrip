from __future__ import annotations

import dataclasses
import typing

from pgsrip.utils import format_time

if typing.TYPE_CHECKING:
    from pgsrip.formats.pgs import Item


@dataclasses.dataclass
class Cue:
    """The result of the OCR chain for one subtitle item. The post-processors change the cues."""

    index: int
    #: in milliseconds
    start: int
    #: in milliseconds
    end: int
    #: None when no engine could read the item
    text: str | None
    #: from 0 to 1, None when the engine gives no confidence
    confidence: float | None
    doubtful: bool
    #: the class name of the engine that gave the text
    engine: str | None
    #: the item with the image
    item: Item

    def to_json(self) -> dict[str, typing.Any]:
        return {
            'index': self.index,
            'start': format_time(self.start),
            'end': format_time(self.end),
            'text': self.text,
            'confidence': self.confidence,
            'doubtful': self.doubtful,
            'engine': self.engine,
        }
