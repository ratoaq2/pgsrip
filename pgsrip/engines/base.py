from __future__ import annotations

import typing

from pgsrip.errors import PgsripError
from pgsrip.plugin import PluginOption

if typing.TYPE_CHECKING:
    from babelfish import Language

    from pgsrip.diagnostics import Check
    from pgsrip.formats.pgs import Item


class OcrError(PgsripError):
    """Raised when an OCR engine cannot read the subtitles."""


class Reading(typing.NamedTuple):
    """What an OCR engine read in one item."""

    #: None when the engine could not read the item
    text: str | None
    #: from 0 to 1, None when the engine gives no confidence
    confidence: float | None = None
    #: the text can be wrong: the next engine of the chain reads the item again
    doubtful: bool = False


class OcrEngine(typing.Protocol):
    """Reads the text of subtitle bitmaps: `pgsrip.engines.auto.AutoEngine` is the default engine.

    Subclass it to get the default `engine_for`.
    """

    def prepare(
        self, languages: typing.Iterable[Language], reporter: typing.Callable[[str], None] | None = None
    ) -> None:
        """Get ready to read these languages, before any ripping starts. Tell the user through reporter.

        Raise OcrError only when the engine cannot rip at all: the rip then stops before it starts.
        """

    def supports(self, language: Language) -> bool:
        """True when the engine can read this language. pgsrip calls it after `prepare`."""

    def engine_for(self, language: Language) -> OcrEngine | None:
        """The engine that reads a track in this language, or None when no engine can read it.

        The default is this engine when it supports the language. An engine that sends each language to another
        engine overrides it.
        """
        return self if self.supports(language) else None

    def recognize(self, items: list[Item], language: Language, debug_dir: str | None) -> list[Reading]:
        """Read the items: one `Reading` for each item, in the same order. Raise OcrError on failure.

        The engine does not change the items. The next engine of the chain gets the items with no text or
        with a doubtful text. With a `debug_dir`, the engine can write its debug files in it.
        """


class OcrEngineFactory(typing.Protocol):
    """An OCR engine that the CLI can create. Its class is the value of a `pgsrip.engines` entry point."""

    options: typing.ClassVar[tuple[PluginOption, ...]]

    @classmethod
    def from_settings(cls, settings: dict[str, typing.Any]) -> OcrEngine:
        """Create the engine. `settings` has a value for each option, by name.

        An option named `workers` with no value gets the value of `-w`, or None. Raise ValueError when a
        value is wrong.
        """

    @classmethod
    def check(cls, settings: dict[str, typing.Any]) -> list[Check]:
        """The lines of `pgsrip doctor` for this engine, with the option values. `[]` when there is nothing to
        check. A check must not fail when an option has no value."""
