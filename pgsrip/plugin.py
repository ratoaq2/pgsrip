from __future__ import annotations

import dataclasses
import typing


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
