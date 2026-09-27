from __future__ import annotations

import typing

from pgsrip.plugin import PluginOption

if typing.TYPE_CHECKING:
    from babelfish import Language

    from pgsrip.media import Pgs, PgsSubtitleItem


class OcrError(Exception):
    """Raised when an OCR engine cannot read the subtitles."""


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

    def recognize(self, pgs: Pgs, items: list[PgsSubtitleItem]) -> None:
        """Set the text of each item, or leave it None when it cannot be read. Raise OcrError on failure.

        Set `item.doubtful` when the text can be wrong. The next engine of the chain gets the items that are
        still None or doubtful. Set `item.confidence` (0-1) when the engine has one.
        """


class OcrEngineFactory(typing.Protocol):
    """An OCR engine that the CLI can create. Its class is the value of a `pgsrip.engines` entry point.

    The class can also have a `check(settings) -> list[Check]` classmethod for `pgsrip doctor`.
    """

    options: typing.ClassVar[tuple[PluginOption, ...]]

    @classmethod
    def from_settings(cls, settings: dict[str, typing.Any], workers: int | None) -> OcrEngine:
        """Create the engine. `settings` has a value for each option, by name. `workers` is None for the default."""
