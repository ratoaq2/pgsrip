from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from pgsrip.media import Pgs
    from pgsrip.plugin import PluginOption
    from pgsrip.ripper import Cue


class PostProcessor(typing.Protocol):
    """Changes the cues of a track after the chain of OCR engines.

    `pgsrip.postprocessors.cleanit.CleanitPostProcessor` is the default.
    """

    def process(self, pgs: Pgs, cues: list[Cue]) -> list[Cue]:
        """Return the new cues. It can change, remove, add, or merge cues.

        A cue with `text=None` was not read by any engine. The SRT leaves out a cue with no text.
        """


class PostProcessorFactory(typing.Protocol):
    """A post-processor that the CLI can create. Its class is the value of a `pgsrip.postprocessors` entry point.

    The class can also have a `check(settings) -> list[Check]` classmethod for `pgsrip doctor`.
    """

    options: typing.ClassVar[tuple[PluginOption, ...]]

    @classmethod
    def from_settings(cls, settings: dict[str, typing.Any]) -> PostProcessor:
        """Create the post-processor. `settings` has a value for each option, by name. Raise ValueError when
        a value is wrong."""
