import dataclasses
import typing

from pgsrip.diagnostics import Check
from pgsrip.media_path import MediaPath
from pgsrip.sources.base import Track


class RawSource:
    """A .sup file: the file is the data of its only track, and the file name gives the language and the flags."""

    missing: typing.ClassVar[str] = ''
    extensions: typing.ClassVar[tuple[str, ...]] = ('.sup',)

    @classmethod
    def check(cls) -> list[Check]:
        return []

    def probe(self, path: str) -> list[Track]:
        media_path = MediaPath(path)
        flags = {f.name: getattr(media_path.flags, f.name) or None for f in dataclasses.fields(media_path.flags)}
        return [Track(0, language=media_path.language, **flags)]

    def extract(self, path: str, targets: dict[int, str]) -> dict[int, str]:
        return {0: path}
