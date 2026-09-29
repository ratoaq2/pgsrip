from __future__ import annotations

import dataclasses
import typing

from babelfish import Language
from trakit.api import trakit

from pgsrip.errors import PgsripError
from pgsrip.track_flags import ALTERNATE, TrackFlags

if typing.TYPE_CHECKING:
    from pgsrip.diagnostics import Check


class SourceError(PgsripError):
    """A source cannot read a media file, or no source for the file is installed."""


def _parse_language(code: str | None) -> Language | None:
    return Language.fromcleanit(code) or None if code else None


@dataclasses.dataclass(frozen=True)
class Track:
    """A PGS track of a media, with no detail of the tool that reads it."""

    id: int
    name: str | None
    language: Language
    flags: TrackFlags
    disabled: bool = False

    @classmethod
    def create(
        cls, id: int, name: str | None, language_tags: list[str | None], container_flags: dict[str, bool | None]
    ) -> Track:
        """Merge the facts of the container with the guess from the track name.

        `language_tags` is in order of preference: the first tag that parses wins, else `und`.
        """
        expected_language = next(
            (lang for lang in map(_parse_language, language_tags) if lang), Language.fromcleanit('und')
        )
        options = {'expected_language': expected_language} if expected_language else {}
        guess = trakit(name, options) if name else {}

        # container `true` wins; container `false`/absent falls back to the track-name guess.
        flags = TrackFlags(
            forced=bool(container_flags.get('forced') or guess.get('forced')),
            hearing_impaired=bool(container_flags.get('hearing_impaired') or guess.get('hearing_impaired')),
            closed_caption=bool(guess.get('closed_caption')),  # no container equivalent
            commentary=bool(container_flags.get('commentary') or guess.get('commentary')),
            descriptive=bool(container_flags.get('descriptive') or guess.get('descriptive')),
            default=bool(container_flags.get('default')),
            original=bool(container_flags.get('original')),
            alternate=guess.get('version') == ALTERNATE,
        )
        language = guess.get('language') or expected_language
        return cls(id, name, language, flags, disabled=bool(container_flags.get('disabled')))


class Source(typing.Protocol):
    """A tool that reads the PGS tracks of the media files with some extensions.

    `pgsrip.sources.SOURCES` is the built-in list, in order of preference.
    """

    #: the reason to show when the tool is not installed
    install_hint: typing.ClassVar[str]
    extensions: typing.ClassVar[tuple[str, ...]]

    @classmethod
    def check(cls) -> list[Check]:
        """The lines of `pgsrip doctor` for this tool."""

    def probe(self, path: str) -> list[Track]:
        """The PGS tracks of the file.

        Raise FileNotFoundError when the tool is not installed, and SourceError when the tool cannot read the file.
        """

    def extract(self, path: str, targets: dict[int, str]) -> dict[int, str]:
        """Extract the tracks with one call. `targets` maps a track id to a .sup path. Raise SourceError on failure.

        Return the .sup path of each track: a source can give another path than the target.
        """
