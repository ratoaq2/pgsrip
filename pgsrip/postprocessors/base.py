from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from pgsrip.cue import Cue
    from pgsrip.diagnostics import Check
    from pgsrip.plugin import PluginOption
    from pgsrip.sources.base import Track


class PostProcessor(typing.Protocol):
    """Changes the cues of a track after the chain of OCR engines.

    `pgsrip.postprocessors.cleanit.CleanitPostProcessor` is the default.
    """

    def process(self, cues: list[Cue], track: Track) -> list[Cue]:
        """Return the new cues of the track. It can change, remove, add, or merge cues.

        A cue with `text=None` was not read by any engine. The SRT leaves out a cue with no text.
        """


class PostProcessorFactory(typing.Protocol):
    """A post-processor that the CLI can create. Its class is the value of a `pgsrip.postprocessors` entry point."""

    options: typing.ClassVar[tuple[PluginOption, ...]]

    @classmethod
    def from_settings(cls, settings: dict[str, typing.Any]) -> PostProcessor:
        """Create the post-processor. `settings` has a value for each option, by name. Raise ValueError when
        a value is wrong."""

    @classmethod
    def check(cls, settings: dict[str, typing.Any]) -> list[Check]:
        """The lines of `pgsrip doctor` for this post-processor, with the option values. `[]` when there is
        nothing to check. A check must not fail when an option has no value."""
