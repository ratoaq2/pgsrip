from __future__ import annotations

import json
import logging
import os
import re
import typing
from datetime import timedelta
from types import TracebackType

import click
import yaml
from appdirs import AppDirs
from babelfish import Error as BabelfishError
from babelfish import Language

from pgsrip import Pgs, __url__, __version__, api
from pgsrip.cli.plugins import (
    AUTO,
    AUTO_ENGINES,
    ENGINE,
    ENGINE_KIND,
    POST_PROCESSOR,
    POST_PROCESSOR_KIND,
    PluginCommand,
    create_engines,
    create_post_processors,
    engine_names,
    installed_plugins,
    plugin_checks,
    post_processor_names,
)
from pgsrip.core import get_reason
from pgsrip.diagnostics import format_checks, run_checks
from pgsrip.engines.auto import check_auto
from pgsrip.engines.base import OcrError
from pgsrip.formats.scrub import Redaction, output_path, scrub_data
from pgsrip.options import Options
from pgsrip.sources import source_checks
from pgsrip.sources.base import Media
from pgsrip.track_flags import FLAG_CHOICES
from pgsrip.writers import WRITERS

if typing.TYPE_CHECKING:
    from click._termui_impl import ProgressBar

logger = logging.getLogger('pgsrip')


T = typing.TypeVar('T')


class DebugProgressBar(typing.Generic[T]):
    def __init__(self, debug: bool, iterable: typing.Iterable[T], **kwargs: typing.Any):
        self.debug = debug
        self.iterable = iterable
        self.progressbar: ProgressBar[T] = click.progressbar(iterable, **kwargs)

    def __iter__(self) -> typing.Iterator[T]:
        if not self.debug:
            yield from self.progressbar.__iter__()
            return

        yield from self.iterable

    def __enter__(self) -> ProgressBar[T] | DebugProgressBar[T]:
        if not self.debug:
            return self.progressbar.__enter__()

        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        if not self.debug:
            return self.progressbar.__exit__(exc_type, exc, traceback)

    def update(self, n_steps: int, current_item: T | None = None) -> None:
        if not self.debug:
            return self.progressbar.update(n_steps, current_item)


class LanguageParamType(click.ParamType[Language, str]):
    name = 'language'

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> Language:
        try:
            return Language.fromietf(value)
        except (BabelfishError, ValueError):
            self.fail(f'{click.style(f"{value}", bold=True)} is not a valid language')


class AgeParamType(click.ParamType[timedelta, str]):
    name = 'age'

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> timedelta:
        match = re.match(r'^(?:(?P<weeks>\d+?)w)?(?:(?P<days>\d+?)d)?(?:(?P<hours>\d+?)h)?$', value)
        if not match:
            self.fail(f'{value} is not a valid age')

        return timedelta(**{k: int(v) for k, v in match.groupdict('0').items()})


class RangeParamType(click.ParamType[frozenset[int], str]):
    name = 'range'

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> frozenset[int]:
        match = re.match(r'^(?P<start>\d+)(?:-(?P<end>\d+))?$', value.strip())
        if not match:
            self.fail(f'{click.style(value, bold=True)} is not a valid display set range, e.g. 412 or 400-420')

        start = int(match.group('start'))
        end = int(match.group('end') or start)
        if end < start:
            self.fail(f'{click.style(value, bold=True)} ends before it starts')

        return frozenset(range(start, end + 1))


LANGUAGE = LanguageParamType()
AGE = AgeParamType()
WRITERS_BY_NAME = {w.name: w for w in WRITERS}
RANGE = RangeParamType()


def merge_ranges(values: tuple[frozenset[int], ...]) -> set[int]:
    """Collect every display set of every given range."""
    return {index for value in values for index in value}


def quote(path: str) -> str:
    """Quote a path so that it can be pasted back into a shell."""
    return f'"{path}"' if ' ' in path else path


def echo_failures(failures: list[tuple[Pgs, Exception]], log_file: str | None) -> None:
    """Report the subtitles that could not be ripped, and how to report them."""
    if not failures:
        return

    click.echo()
    click.echo(
        f'{click.style(str(len(failures)), bold=True, fg="red")} '
        f'PGS subtitle{"s" if len(failures) > 1 else ""} could not be ripped:'
    )
    for pgs, error in failures[:MAX_REPORTED_PATHS]:
        click.echo(f'  {pgs}: <{type(error).__name__}> [{error}]')

    # a scrubbed sample cannot reproduce an OCR engine failure, e.g. missing tesseract data
    sources = sorted({str(pgs.source_path) for pgs, error in failures if not isinstance(error, OcrError)})
    if not sources:
        return

    click.echo('To report this, run:')
    for source in sources[:MAX_REPORTED_PATHS]:
        click.echo(f'  {click.style(f"pgsrip scrub {quote(source)}", bold=True)}')
    if not log_file:
        click.echo(f'  {click.style(f"pgsrip --log-file pgsrip.log {quote(sources[0])}", bold=True)}')

    click.echo('The scrubbed subtitle holds no image, only what is needed to reproduce the error.')
    click.echo(f'Attach it to a new issue: {click.style(f"{__url__}/issues", bold=True)}')


# arguments that the group handles itself, everything else belongs to the default command
GROUP_ARGUMENTS = frozenset({'--help', '-h', '--version'})

# how many ignored paths are listed before the list is cut short
MAX_REPORTED_PATHS = 10


def echo_paths(paths: list[str], label: str, color: str, limit: int | None) -> None:
    """Print each path with the reason why it was not ripped."""
    for path in paths[:limit] if limit else paths:
        reason = get_reason(path)
        message = f'{click.style(str(path), fg=color, bold=True)} {label}'
        click.echo(f'{message}: {reason}' if reason else message)

    remaining = len(paths) - limit if limit else 0
    if remaining > 0:
        click.echo(f'... and {remaining} more, use {click.style("-vv", bold=True)} to see them all')


def configure_logging(debug: bool, log_file: str | None) -> None:
    """Send debug messages to the console, to a log file, or to both."""
    if not debug and not log_file:
        return

    logger.setLevel(logging.DEBUG)
    if debug:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
        logger.addHandler(handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf8')
        file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
        logger.addHandler(file_handler)


def log_environment(ctx: click.Context | None = None) -> None:
    """Record the installed versions, and the checks of the selected plug-ins, at the top of the debug log."""
    if not logger.isEnabledFor(logging.DEBUG):
        return

    checks = source_checks()
    if ctx:
        checks += (
            plugin_checks(ctx, ENGINE_KIND, engine_names(ctx.params))
            + ([check_auto()] if ctx.params['engine'] == (AUTO,) else [])
            + plugin_checks(ctx, POST_PROCESSOR_KIND, post_processor_names(ctx.params))
        )
    for line in format_checks(run_checks(checks)).splitlines():
        logger.info(line)


def prepare_engines(pgs_medias: list[Pgs], options: Options) -> bool:
    """Get the OCR engines ready for every collected subtitle, before any ripping starts."""
    if not pgs_medias:
        return True

    languages = list(dict.fromkeys(pgs.language for pgs in pgs_medias))
    try:
        for engine in options.engines:
            engine.prepare(languages, reporter=click.echo)
    except OcrError as e:
        click.echo(click.style(str(e), fg='red'))
        return False

    for engine in options.engines:
        unsupported = sorted(str(language) for language in languages if engine.engine_for(language) is None)
        if unsupported:
            click.echo(f'{type(engine).__name__} cannot read {", ".join(unsupported)}')

    return True


CONFIG_EXTENSIONS = ('.json', '.yml', '.yaml')


def read_config(path: str) -> dict[str, typing.Any]:
    """Read the option values of a .json, .yml or .yaml configuration file."""
    extension = os.path.splitext(path)[1].lower()
    if extension not in CONFIG_EXTENSIONS:
        raise click.BadParameter(f'{path} is not a .json, .yml or .yaml file')

    try:
        with open(path, encoding='utf-8') as f:
            values = json.load(f) if extension == '.json' else yaml.safe_load(f)
    except (OSError, ValueError, yaml.YAMLError) as e:
        raise click.BadParameter(f'Cannot read {path}: {e}') from e

    if values is None:
        return {}
    if not isinstance(values, dict):
        raise click.BadParameter(f'{path} must contain option names and values')

    # a section groups the options with the same prefix: `tesseract: {threshold: 90}` is `tesseract_threshold: 90`
    flat: dict[str, typing.Any] = {}
    for key, value in values.items():
        if isinstance(value, dict):
            flat.update({f'{key}_{name}': section_value for name, section_value in value.items()})
        else:
            flat[key] = value

    return flat


def set_default_config(ctx: click.Context, param: click.Parameter, configs: tuple[str, ...]) -> None:
    """Use the values of the configuration files as option defaults. A later file wins."""
    found = [
        os.path.join(folder, f'{name}{extension}')
        for folder, name in ((AppDirs('pgsrip').user_config_dir, 'config'), (os.getcwd(), 'pgsrip'))
        for extension in CONFIG_EXTENSIONS
    ]
    # the files hold rip options: a command with fewer options, e.g. doctor, reads only its own
    names = {p.name for p in rip.get_params(ctx) if isinstance(p, click.Option) and p.name != param.name}
    default_map: dict[str, typing.Any] = {}
    for path in [p for p in found if os.path.isfile(p)] + list(configs):
        values = read_config(path)
        unknown = sorted(set(values) - names)
        if unknown:
            raise click.BadParameter(f'Unknown option in {path}: {", ".join(unknown)}')
        default_map.update(values)

    ctx.default_map = default_map


class DefaultGroup(click.Group):
    """A group that runs a default command, so that `pgsrip MEDIA` keeps working."""

    def __init__(self, *args: typing.Any, default: str = '', **kwargs: typing.Any):
        super().__init__(*args, **kwargs)
        self.default = default

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if args and args[0] not in self.commands and args[0] not in GROUP_ARGUMENTS:
            args = [self.default, *args]

        return super().parse_args(ctx, args)


@click.group(cls=DefaultGroup, default='rip')
@click.version_option(__version__)
def pgsrip() -> None:
    """Rip your PGS subtitles."""


config_option = click.option(
    '--config',
    type=click.Path(exists=True, dir_okay=False),
    multiple=True,
    callback=set_default_config,
    is_eager=True,
    expose_value=False,
    help='pgsrip configuration file (.json, .yml or .yaml) with default option values (can be used multiple times).',
)


@pgsrip.command(cls=PluginCommand)
@config_option
@click.option(
    '-l',
    '--language',
    type=LANGUAGE,
    multiple=True,
    help='Language as IETF code, e.g. en, pt-BR (can be used multiple times).',
)
@click.option('-e', '--encoding', help='Save subtitles using the following encoding.')
@click.option('-a', '--age', type=AGE, help='Filter videos newer than AGE, e.g. 12h, 1w2d.')
@click.option(
    '-A', '--output-age', type=AGE, help='Filter videos whose subtitle files are newer than AGE, e.g. 12h, 1w2d.'
)
@click.option(
    '--format',
    type=click.Choice([w.name for w in WRITERS]),
    multiple=True,
    default=('srt',),
    show_default=True,
    help='Output format. Use it more than one time to write more than one file.',
)
@click.option(
    '-f',
    '--force',
    is_flag=True,
    default=False,
    help='re-rip and overwrite existing subtitle files, even if they already exist',
)
@click.option(
    '--all',
    is_flag=True,
    default=False,
    help='rip all tracks for a given language, even another track for that language was already ripped',
)
@click.option(
    '--with',
    'with_flags',
    type=click.Choice(FLAG_CHOICES),
    multiple=True,
    help='Only rip tracks carrying at least one of these flags, e.g. forced, sdh, full (can be used multiple times).',
)
@click.option(
    '--without',
    'without_flags',
    type=click.Choice(FLAG_CHOICES),
    multiple=True,
    help='Never rip tracks carrying any of these flags; wins over --with (can be used multiple times).',
)
@click.option(
    '--one-per-language',
    is_flag=True,
    default=False,
    help='Keep only one track per language, ignoring flags, e.g. skip a track that is only SDH '
    'if a plain track for that language was already selected.',
)
@click.option(
    '-w',
    '--max-workers',
    type=click.IntRange(1, 50),
    default=None,
    help='Number of OCR jobs to run in parallel, e.g. tesseract processes. Default: the number of CPUs, at most 4.',
)
@click.option(
    '--engine',
    type=ENGINE,
    multiple=True,
    default=(AUTO,),
    show_default=True,
    help='OCR engine that reads the subtitle images: tesseract, rapidocr, or an engine of an installed plug-in. '
    'auto uses tesseract for each language that it can read, else rapidocr. '
    'Use it more than one time for a chain: each engine reads the cues that the engines before it '
    'could not read or are not sure of.',
)
@click.option(
    '--post-processor',
    type=POST_PROCESSOR,
    multiple=True,
    default=('cleanit',),
    show_default=True,
    help='Post-processor that changes the text after the OCR engines: cleanit, or a post-processor of an installed '
    'plug-in. Use it more than one time for a chain: each post-processor gets the result of the one before it.',
)
@click.option('--no-post-process', is_flag=True, help='Do not change the text after the OCR engines.')
@click.option(
    '--keep-temp-files',
    is_flag=True,
    help='Do not delete temporary files created, '
    'e.g. extracted sup files, generated png files '
    'and other useful debug files',
)
@click.option('--debug', is_flag=True, help='Print useful information for debugging and for reporting bugs.')
@click.option(
    '--log-file',
    type=click.Path(dir_okay=False, writable=True),
    help='Write a full debug log to this file, to attach it to a bug report.',
)
@click.option('-v', '--verbose', count=True, help='Display debug messages')
@click.argument('path', type=click.Path(), required=True, nargs=-1)
@click.pass_context
def rip(
    ctx: click.Context,
    /,
    language: tuple[Language] | None,
    encoding: str | None,
    age: timedelta | None,
    output_age: timedelta | None,
    format: tuple[str, ...],
    force: bool,
    all: bool,
    with_flags: tuple[str, ...],
    without_flags: tuple[str, ...],
    one_per_language: bool,
    debug: bool,
    log_file: str | None,
    max_workers: int | None,
    engine: tuple[str, ...],
    post_processor: tuple[str, ...],
    no_post_process: bool,
    keep_temp_files: bool,
    verbose: int,
    path: tuple[str],
    **plugin_params: typing.Any,
) -> None:
    """Rip the PGS subtitles of each media PATH into subtitle files."""
    try:
        configure_logging(debug, log_file)
    except OSError as e:
        click.echo(click.style(f'Cannot write the log file: {e}', fg='red'))
        return

    # the temporary folder of the run is removed when the command ends, also on an error
    options = ctx.with_resource(
        Options(
            languages=set(language or []),
            encoding=encoding,
            overwrite=force,
            one_per_lang=not all,
            one_per_language=one_per_language,
            include_flags=frozenset(with_flags),
            exclude_flags=frozenset(without_flags),
            keep_temp_files=keep_temp_files,
            engines=create_engines(ctx),
            post_processors=create_post_processors(ctx),
            age=age,
            output_age=output_age,
            # one writer for each format, in the order of the option
            writers=[WRITERS_BY_NAME[name]() for name in dict.fromkeys(format)],
        )
    )

    log_environment(ctx)

    collected_medias: list[Media] = []
    filtered_out_paths: list[str] = []
    discarded_paths: list[str] = []
    for p in path:
        c, f, d = api.scan_path(p, options)
        collected_medias.extend(c)
        filtered_out_paths.extend(f)
        discarded_paths.extend(d)

    if verbose > 2:
        echo_paths(filtered_out_paths, 'filtered out', 'yellow', limit=None)
    echo_paths(discarded_paths, 'ignored', 'red', limit=None if debug or verbose > 1 else MAX_REPORTED_PATHS)

    collected_pgs_medias: list[Pgs] = []
    medias_progressbar = DebugProgressBar(
        debug or verbose > 1,
        collected_medias,
        label='Collecting pgs subtitles',
        item_show_func=lambda item: str(item or ''),
    )

    with medias_progressbar as bar:
        for m in bar:
            collected_pgs_medias.extend(list(m.get_pgs_medias(options)))

    # report collected medias
    report = (
        f'{click.style(str(len(collected_pgs_medias)), bold=True, fg="green")} '
        f'PGS subtitle{"s" if len(collected_pgs_medias) > 1 else ""} collected '
        f'from {click.style(str(len(collected_medias)), bold=True, fg="green")} '
        f'file{"s" if len(collected_medias) > 1 else ""}'
    )
    if filtered_out_paths:
        report += (
            f' / {click.style(str(len(filtered_out_paths)), bold=True, fg="yellow")} '
            f'file{"s" if len(filtered_out_paths) > 1 else ""} filtered out'
        )
    if discarded_paths:
        report += (
            f' / {click.style(str(len(discarded_paths)), bold=True, fg="red")} '
            f'path{"s" if len(discarded_paths) > 1 else ""} ignored'
        )
    click.echo(report)

    if not prepare_engines(collected_pgs_medias, options):
        raise SystemExit(1)

    pgs_progressbar = DebugProgressBar(
        debug or verbose > 1,
        collected_pgs_medias,
        label='Ripping subtitles',
        update_min_steps=0,
        item_show_func=lambda s: click.style(str(s or ''), bold=True),
    )

    ripped_count = 0
    failures: list[tuple[Pgs, Exception]] = []
    with pgs_progressbar as bar:
        for pgs in bar:
            bar.update(0, pgs)
            ripped_count += api.rip_pgs(pgs, options, on_error=lambda p, e: failures.append((p, e)))

    # report ripped subtitles
    click.echo(
        f'{click.style(str(ripped_count), bold=True, fg="green")} '
        f'PGS subtitle{"s" if ripped_count > 1 else ""} ripped from '
        f'{click.style(str(len(collected_medias)), bold=True, fg="blue")} '
        f'file{"s" if len(collected_medias) > 1 else ""}'
    )

    if log_file:
        click.echo(f'Debug log written to {click.style(log_file, bold=True)}')

    echo_failures(failures, log_file)
    if failures:
        raise SystemExit(1)


@pgsrip.command(cls=PluginCommand)
@config_option
@click.pass_context
def doctor(ctx: click.Context, /, **plugin_params: typing.Any) -> None:
    """Check that everything pgsrip needs is installed. Add the output to a bug report."""
    auto = check_auto()
    auto_checks = plugin_checks(ctx, ENGINE_KIND, AUTO_ENGINES)
    if auto.ok:
        # pgsrip can rip: a problem of one engine of auto is not a failure
        auto_checks = [check._replace(ok=True) for check in auto_checks]
    other_engines = [name for name in installed_plugins(ctx, ENGINE_KIND) if name not in AUTO_ENGINES]
    checks = run_checks(
        [
            *source_checks(),
            *auto_checks,
            auto,
            *plugin_checks(ctx, ENGINE_KIND, other_engines),
            *plugin_checks(ctx, POST_PROCESSOR_KIND, installed_plugins(ctx, POST_PROCESSOR_KIND)),
        ]
    )
    click.echo(format_checks(checks))

    failed = [check for check in checks if not check.ok]
    if not failed:
        click.echo()
        click.echo(click.style('Everything that pgsrip needs is installed.', fg='green'))
        return

    click.echo()
    for check in failed:
        click.echo(f'{click.style(check.name, fg="red", bold=True)}: {check.value}')
        if check.hint:
            click.echo(f'  {check.hint}')

    raise SystemExit(1)


@pgsrip.command()
@click.option(
    '-o',
    '--output',
    type=click.Path(),
    help='Path or directory to write the scrubbed .sup files to. Defaults to the current directory.',
)
@click.option(
    '--redact',
    type=click.Choice([redaction.value for redaction in Redaction]),
    default=Redaction.ALL.value,
    show_default=True,
    help='all: replace every subtitle image with an empty one. '
    'synthetic: replace them with placeholder text of the same size. '
    'none: keep the original images, which are the content of your media.',
)
@click.option(
    '--keep-images',
    type=RANGE,
    multiple=True,
    help='Display sets that keep their original images, e.g. 412 or 400-420 (can be used multiple times).',
)
@click.option(
    '--only',
    type=RANGE,
    multiple=True,
    help='Write only these display sets, e.g. 0-99 (can be used multiple times).',
)
@click.option(
    '-l',
    '--language',
    type=LANGUAGE,
    multiple=True,
    help='Language as IETF code, e.g. en, pt-BR (can be used multiple times).',
)
@click.option('--all', 'every_track', is_flag=True, default=False, help='scrub all tracks for a given language')
@click.option(
    '--keep-name',
    is_flag=True,
    default=False,
    help='Name the output after the media file, instead of after a hash of its name.',
)
@click.option('--debug', is_flag=True, help='Print useful information for debugging and for reporting bugs.')
@click.option(
    '--log-file',
    type=click.Path(dir_okay=False, writable=True),
    help='Write a full debug log to this file, to attach it to a bug report.',
)
@click.argument('path', type=click.Path(), required=True, nargs=-1)
def scrub(
    output: str | None,
    redact: str,
    keep_images: tuple[frozenset[int], ...],
    only: tuple[frozenset[int], ...],
    language: tuple[Language] | None,
    every_track: bool,
    keep_name: bool,
    debug: bool,
    log_file: str | None,
    path: tuple[str],
) -> None:
    """Copy the PGS subtitles of each media PATH without the subtitle images.

    The result is a .sup file that pgsrip reads like any other one. It keeps the timing, the
    layout and the palettes, which is what almost every bug is about, and it is small enough to
    attach to a bug report.
    """
    try:
        configure_logging(debug, log_file)
    except OSError as e:
        click.echo(click.style(f'Cannot write the log file: {e}', fg='red'))
        return

    redaction = Redaction(redact)
    options = click.get_current_context().with_resource(
        Options(languages=set(language or []), one_per_lang=not every_track, overwrite=True)
    )
    log_environment()

    collected_medias: list[Media] = []
    discarded_paths: list[str] = []
    for p in path:
        collected, _, discarded = api.scan_path(p, options)
        collected_medias.extend(collected)
        discarded_paths.extend(discarded)

    echo_paths(discarded_paths, 'ignored', 'red', limit=None if debug else MAX_REPORTED_PATHS)
    if not collected_medias:
        click.echo(click.style('No media to scrub', fg='red'))
        return

    written = scrub_medias(collected_medias, options, redaction, keep_images, only, output, keep_name)
    if not written:
        return

    if redaction == Redaction.NONE:
        click.echo(click.style('The scrubbed files hold the original subtitle images.', fg='yellow'))
    else:
        click.echo('The scrubbed files hold no subtitle image, only timing, layout and palettes.')

    click.echo(f'Attach them to a new issue: {click.style(f"{__url__}/issues", bold=True)}')


def scrub_medias(
    medias: list[Media],
    options: Options,
    redaction: Redaction,
    keep_images: tuple[frozenset[int], ...],
    only: tuple[frozenset[int], ...],
    output: str | None,
    keep_name: bool,
) -> list[str]:
    """Write a scrubbed .sup file for every PGS subtitle of every media, and return their paths."""
    kept = merge_ranges(keep_images)
    selected = merge_ranges(only) or None
    used: set[str] = set()
    written: list[str] = []
    for media in medias:
        for pgs in media.get_pgs_medias(options):
            with pgs:
                try:
                    data, stats = scrub_data(pgs.data_reader(), pgs.media_path, redaction, kept, selected)
                except Exception as e:
                    logger.debug('Cannot scrub %s', pgs, exc_info=True)
                    click.echo(click.style(f'Cannot scrub {pgs}: <{type(e).__name__}> [{e}]', fg='red'))
                    continue

                target = output_path(pgs.media_path, output, keep_name, used)
                with open(target, 'wb') as f:
                    f.write(data)

                written.append(target)
                click.echo(f'{click.style(target, bold=True, fg="green")} written: {stats}')

    return written
