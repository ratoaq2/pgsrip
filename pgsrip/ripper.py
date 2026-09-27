from __future__ import annotations

import dataclasses
import logging
import time
import typing

from pysrt import SubRipFile, SubRipItem, SubRipTime

from pgsrip.engines.base import OcrError

if typing.TYPE_CHECKING:
    from pgsrip.media import Pgs, PgsSubtitleItem
    from pgsrip.options import Options

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class Cue:
    """The result of the OCR chain for one subtitle item. The post-processors change the cues."""

    index: int
    start: SubRipTime | None
    end: SubRipTime | None
    #: None when no engine could read the item
    text: str | None
    #: from 0 to 1, None when the engine gives no confidence
    confidence: float | None
    doubtful: bool
    #: the class name of the engine that gave the text
    engine: str | None
    #: the item with the image
    item: PgsSubtitleItem

    def to_json(self) -> dict[str, typing.Any]:
        return {
            'index': self.index,
            'start': str(self.start),
            'end': str(self.end),
            'text': self.text,
            'confidence': self.confidence,
            'doubtful': self.doubtful,
            'engine': self.engine,
        }


class PgsToSrtRipper:
    def __init__(self, pgs: Pgs, options: Options):
        self.pgs = pgs
        self.engines = options.engines
        #: the time of each engine of the chain, in seconds
        self.seconds: dict[str, float] = {}

    def rip(self) -> list[Cue]:
        """Read the items with the chain of OCR engines. An item with no ink gives no cue."""
        if not self.pgs.items:
            # a track with no image is corrupted: do not write an empty srt as if it was ripped
            raise ValueError(f'No subtitle image in {self.pgs}')

        language = self.pgs.language
        chain = [e for e in (engine.engine_for(language) for engine in self.engines) if e is not None]
        if not chain:
            raise OcrError(f'No OCR engine of the chain can read {language}')

        # an item with no ink has no text to read
        items = [item for item in self.pgs.items if item.height]
        engines: dict[PgsSubtitleItem, str] = {}
        for engine in chain:
            pending = [
                (item, item.text, item.doubtful, item.confidence)
                for item in items
                if item.text is None or item.doubtful
            ]
            if not pending:
                break

            for item, _, _, _ in pending:
                item.text, item.doubtful, item.confidence = None, False, None
            name = type(engine).__name__
            started = time.perf_counter()
            engine.recognize(self.pgs, [item for item, _, _, _ in pending])
            self.seconds[name] = time.perf_counter() - started
            # an engine that reads nothing does not remove the text of the engine before it
            for item, text, doubtful, confidence in pending:
                if not item.text and text:
                    item.text, item.doubtful, item.confidence = text, doubtful, confidence
                elif item.text is not None:
                    engines[item] = name

        unresolved = [item for item in items if item.text is None]
        if unresolved:
            logger.warning('Subtitles were not ripped: %r', unresolved)

        return [
            Cue(
                item.index,
                item.start,
                item.end,
                item.text,
                item.confidence,
                item.doubtful,
                engines.get(item),
                item,
            )
            for item in items
        ]


def create_srt(path: str, cues: list[Cue]) -> SubRipFile:
    """The SRT of the cues. A cue with no text is left out."""
    subs = SubRipFile(path=path)
    for cue in cues:
        if cue.text:
            subs.append(SubRipItem(0, cue.start, cue.end, cue.text))
    subs.clean_indexes()

    return subs
