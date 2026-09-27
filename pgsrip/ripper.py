from __future__ import annotations

import dataclasses
import logging
import time
import typing

from pysrt import SubRipFile, SubRipItem, SubRipTime

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
        still None or doubtful. Set `item.confidence` (0-1) when the engine has one.
        """


@dataclasses.dataclass(frozen=True)
class PluginOption:
    """One setting of an OCR engine or a post-processor.

    It is `--<plugin>-<name>` on the command line, and `<name>` in the `<plugin>` section of a config file.
    """

    name: str
    #: a Python type or a click type, e.g. `click.IntRange(0, 100)`
    type: typing.Any = str
    default: typing.Any = None
    help: str = ''
    #: an on/off option: `--<plugin>-<name>/--no-<plugin>-<name>`
    flag: bool = False
    #: the plug-in cannot work without it
    required: bool = False
    envvar: str | None = None
    #: the option can be used more than one time, the value is a tuple
    multiple: bool = False
    #: other command line flags for the option, e.g. `-t`
    aliases: tuple[str, ...] = ()


class OcrEngineFactory(typing.Protocol):
    """An OCR engine that the CLI can create. Its class is the value of a `pgsrip.engines` entry point.

    The class can also have a `check(settings) -> list[Check]` classmethod for `pgsrip doctor`.
    """

    options: typing.ClassVar[tuple[PluginOption, ...]]

    @classmethod
    def from_settings(cls, settings: dict[str, typing.Any], workers: int | None) -> OcrEngine:
        """Create the engine. `settings` has a value for each option, by name. `workers` is None for the default."""


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

        # an item with no ink has no text to read
        items = [item for item in self.pgs.items if item.height]
        engines: dict[PgsSubtitleItem, str] = {}
        for engine in self.engines:
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
