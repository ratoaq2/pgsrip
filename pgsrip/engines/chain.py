"""The chain of OCR engines: each engine reads the items that the engines before it left unread or doubtful."""

from __future__ import annotations

import logging
import time
import typing

from pgsrip.cue import Cue
from pgsrip.engines.base import OcrError, Reading

if typing.TYPE_CHECKING:
    from collections.abc import Sequence

    from babelfish import Language

    from pgsrip.engines.base import OcrEngine
    from pgsrip.formats.pgs import Item

logger = logging.getLogger(__name__)

NOT_READ = Reading(None)


def read_cues(
    items: list[Item], language: Language, engines: Sequence[OcrEngine], debug_dir: str | None = None
) -> tuple[list[Cue], dict[str, float]]:
    """Read the items with the chain of OCR engines. Return the cues, and the time of each engine in seconds.

    An item with no ink gives no cue.
    """
    chain = [e for e in (engine.engine_for(language) for engine in engines) if e is not None]
    if not chain:
        raise OcrError(f'No OCR engine of the chain can read {language}')

    # an item with no ink has no text to read
    items = [item for item in items if item.height]
    readings: dict[Item, Reading] = {}
    names: dict[Item, str] = {}
    seconds: dict[str, float] = {}
    for engine in chain:
        to_read = [item for item in items if (r := readings.get(item, NOT_READ)).text is None or r.doubtful]
        if not to_read:
            break

        name = type(engine).__name__
        started = time.perf_counter()
        results = engine.recognize(to_read, language, debug_dir)
        seconds[name] = time.perf_counter() - started
        for item, reading in zip(to_read, results, strict=True):
            # an engine that reads nothing does not remove the text of the engine before it
            if not reading.text and readings.get(item, NOT_READ).text:
                continue
            readings[item] = reading
            if reading.text is not None:
                names[item] = name

    unresolved = [item for item in items if readings.get(item, NOT_READ).text is None]
    if unresolved:
        logger.warning('Subtitles were not ripped: %r', unresolved)

    cues = []
    for item in items:
        reading = readings.get(item, NOT_READ)
        cues.append(
            Cue(
                item.index,
                item.start,
                item.end,
                reading.text,
                reading.confidence,
                reading.doubtful,
                names.get(item),
                item,
            )
        )

    return cues, seconds
