import typing

from pgsrip.diagnostics import Check
from pgsrip.media_path import MediaPath
from pgsrip.sources.base import Source, Track


class RawSource(Source):
    """A .sup file: the file is the data of its only track, and the file name gives the language and the flags."""

    install_hint: typing.ClassVar[str] = ''
    extensions: typing.ClassVar[tuple[str, ...]] = ('.sup',)

    @classmethod
    def check(cls) -> list[Check]:
        return []

    def probe(self, path: str) -> list[Track]:
        media_path = MediaPath(path)
        return [Track(0, None, media_path.language, media_path.flags)]

    def extract(self, path: str, targets: dict[int, str]) -> dict[int, str]:
        return {0: path}
