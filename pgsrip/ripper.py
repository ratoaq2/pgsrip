from __future__ import annotations

import logging
import typing

from pysrt import SubRipFile, SubRipItem

if typing.TYPE_CHECKING:
    from babelfish import Language

    from pgsrip.media import Pgs, PgsSubtitleItem
    from pgsrip.options import Options

logger = logging.getLogger(__name__)


class OcrError(Exception):
    """Raised when an OCR engine cannot read the subtitles."""


class OcrEngine(typing.Protocol):
    """Reads the text of subtitle bitmaps: `pgsrip.tesseract.TesseractEngine` is the default engine."""

    def prepare(
        self, languages: typing.Iterable[Language], reporter: typing.Callable[[str], None] | None = None
    ) -> None:
        """Get ready to read these languages, before any ripping starts. Tell the user through reporter.

        Raise OcrError only when the engine cannot rip at all: the rip then stops before it starts.
        """

    def recognize(self, pgs: Pgs, items: list[PgsSubtitleItem]) -> None:
        """Set the text of each item, or leave it None when it cannot be read. Raise OcrError on failure.

        Set `item.doubtful` when the text can be wrong. The next engine of the chain gets the items that are
        still None or doubtful.
        """


class PgsToSrtRipper:
    def __init__(self, pgs: Pgs, options: Options):
        self.pgs = pgs
        self.engines = options.engines

    def rip(self, post_process: typing.Callable[[str], str] | None) -> SubRipFile:
        if not self.pgs.items:
            # a track with no image is corrupted: do not write an empty srt as if it was ripped
            raise ValueError(f'No subtitle image in {self.pgs}')

        subs = SubRipFile(path=str(self.pgs.media_path.translate(extension='srt')))
        # an item with no ink has no text to read
        items = [item for item in self.pgs.items if item.height]
        for engine in self.engines:
            pending = [(item, item.text, item.doubtful) for item in items if item.text is None or item.doubtful]
            if not pending:
                break

            for item, _, _ in pending:
                item.text, item.doubtful = None, False
            engine.recognize(self.pgs, [item for item, _, _ in pending])
            # an engine that reads nothing does not remove the text of the engine before it
            for item, text, doubtful in pending:
                if not item.text and text:
                    item.text, item.doubtful = text, doubtful

        unresolved = [item for item in items if item.text is None]
        if unresolved:
            logger.warning('Subtitles were not ripped: %r', unresolved)

        for item in items:
            text = item.text
            if text is None:
                continue

            if post_process:
                text = post_process(text)
            if text:
                subs.append(SubRipItem(0, item.start, item.end, text))

        subs.clean_indexes()

        return subs
