from __future__ import annotations

import dataclasses
import typing
from collections.abc import Sequence
from datetime import timedelta

from babelfish import Language

if typing.TYPE_CHECKING:
    from pgsrip.engines.base import OcrEngine
    from pgsrip.postprocessors.base import PostProcessor
    from pgsrip.writers.base import Writer


@dataclasses.dataclass(frozen=True)
class Options:
    """The options of one run. A field has the name of its CLI option, with these exceptions:
    `languages` is `-l/--language`, `all_tracks` is `--all`, `with_flags` is `--with` and `without_flags` is
    `--without`.

    None in `engines`, `post_processors` or `writers` means the default of `pgsrip.api`: auto, cleanit, srt.
    An empty list is a value: for example, no post-processor.
    """

    languages: frozenset[Language] = frozenset()
    encoding: str | None = None
    #: write again the files that exist
    force: bool = False
    #: keep the duplicates: the tracks with the same language and the same flags
    all_tracks: bool = False
    #: one track for each language, whatever its flags
    one_per_language: bool = False
    with_flags: frozenset[str] = frozenset()
    without_flags: frozenset[str] = frozenset()
    #: rip only the media files that are newer
    age: timedelta | None = None
    #: with `force`, do not write again an output file that is newer
    output_age: timedelta | None = None
    #: a chain: each engine reads the items that the engines before it left unread
    engines: Sequence[OcrEngine] | None = None
    #: a chain: each post-processor changes the cues of the one before it
    post_processors: Sequence[PostProcessor] | None = None
    #: each writer writes one file for each track
    writers: Sequence[Writer] | None = None
