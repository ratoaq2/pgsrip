from __future__ import annotations

import os
import typing

import click
from cleanit import Config

from pgsrip.diagnostics import Check
from pgsrip.plugin import PluginOption

if typing.TYPE_CHECKING:
    from pgsrip.media import Pgs
    from pgsrip.ripper import Cue


class CleanitPostProcessor:
    """The default post-processor: applies the cleanit rules of the track language to each cue."""

    options: typing.ClassVar[tuple[PluginOption, ...]] = (
        PluginOption('config', click.Path(), help='cleanit configuration path to be used.'),
        PluginOption(
            'tag',
            multiple=True,
            aliases=('-t', '--tag'),
            help='Rule tags to be used, e.g. ocr, tidy, no-sdh, no-style, no-lyrics, no-spam '
            '(can be used multiple times). Default: default.',
        ),
    )

    def __init__(self, config_path: str | None = None, tags: typing.Collection[str] | None = None):
        self.config = Config.from_path(config_path) if config_path else Config()
        self.tags = set(tags or {'default'})

    @classmethod
    def from_settings(cls, settings: dict[str, typing.Any]) -> CleanitPostProcessor:
        path: str | None = settings['config']
        if path and not os.path.isfile(path):
            raise ValueError(f'Invalid cleanit configuration: {path}')

        post_processor = cls(path, settings['tag'])
        if not post_processor.config.select_rules(tags=post_processor.tags):
            raise ValueError(f'No cleanit rules defined for {", ".join(sorted(post_processor.tags))}')

        return post_processor

    @classmethod
    def check(cls, settings: dict[str, typing.Any]) -> list[Check]:
        """The cleanit configuration file, for `pgsrip doctor`."""
        path: str | None = settings['config']
        if not path:
            return [Check('cleanit config', 'default')]
        if not os.path.isfile(path):
            return [Check('cleanit config', f'{path} (not found)', ok=False, hint='Set --cleanit-config to a file')]

        return [Check('cleanit config', path)]

    def process(self, pgs: Pgs, cues: list[Cue]) -> list[Cue]:
        rules = self.config.select_rules(tags=self.tags, languages={pgs.language})
        for cue in cues:
            if cue.text:
                cue.text = rules.apply(cue.text, '')[0]

        return cues

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [tags:{self.tags}]>'
