from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import re
import typing
from datetime import timedelta

import click
import yaml
from appdirs import AppDirs
from babelfish import Error as BabelfishError
from babelfish import Language

from pgsrip import __url__, __version__, api
from pgsrip.api import ScanResult, Skipped
from pgsrip.cli.plugins import (
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
from pgsrip.diagnostics import format_checks, run_checks
from pgsrip.engines.auto import AUTO, AUTO_ENGINES, AutoEngine
from pgsrip.engines.base import OcrError
from pgsrip.formats.scrub import Redaction, scrub_data
from pgsrip.media import Media, Subtitle, Workspace
from pgsrip.media_path import MediaPath
from pgsrip.options import Options
from pgsrip.sources import source_checks
from pgsrip.track_flags import FLAG_CHOICES
from pgsrip.utils import MAX_DEFAULT_WORKERS
from pgsrip.writers import WRITERS

logger = logging.getLogger('pgsrip')


#: the arguments that the group handles. The default command gets all the other arguments
GROUP_ARGUMENTS = frozenset({'--help', '-h', '--version'})
#: how many paths a report lists before it cuts the list
MAX_REPORTED_PATHS = 10
CONFIG_EXTENSIONS = ('.json', '.yml', '.yaml')
SUP_EXTENSION = '.sup'
WRITERS_BY_NAME = {w.name: w for w in WRITERS}


class LanguageParamType(click.ParamType[Language, str]):
    name = 'language'

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> Language:
        try:
            return Language.fromietf(value)
        except (BabelfishError, ValueError):
            self.fail(f'{click.style(value, bold=True)} is not a valid language')


class AgeParamType(click.ParamType[timedelta, str]):
    name = 'age'

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> timedelta:
        match = re.match(r'^(?:(?P<weeks>\d+)w)?(?:(?P<days>\d+)d)?(?:(?P<hours>\d+)h)?$', value)
        if not value or not match:
            self.fail(f'{click.style(value, bold=True)} is not a valid age')

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
RANGE = RangeParamType()


def merge_ranges(values: tuple[frozenset[int], ...]) -> set[int]:
    """Collect every display set of every given range."""
    return {index for value in values for index in value}


def quote(path: str) -> str:
    """Quote a path so that it can be pasted back into a shell."""
    return f'"{path}"' if ' ' in path else path


def echo_failures(failures: list[tuple[Subtitle, Exception]], log_file: str | None) -> None:
    """Report the subtitles that could not be ripped, and how to report them."""
    if not failures:
        return

    click.echo()
    click.echo(
        f'{click.style(str(len(failures)), bold=True, fg="red")} '
        f'PGS subtitle{"s" if len(failures) > 1 else ""} could not be ripped:'
    )
    for subtitle, error in failures[:MAX_REPORTED_PATHS]:
        click.echo(f'  {subtitle}: <{type(error).__name__}> {error}')

    # a scrubbed sample cannot reproduce an OCR engine failure, e.g. missing tesseract data
    sources = sorted({str(subtitle.source_path) for subtitle, error in failures if not isinstance(error, OcrError)})
    if not sources:
        return

    click.echo('To report this, run:')
    for source in sources[:MAX_REPORTED_PATHS]:
        click.echo(f'  {click.style(f"pgsrip scrub {quote(source)}", bold=True)}')
    if not log_file:
        click.echo(f'  {click.style(f"pgsrip --log-file pgsrip.log {quote(sources[0])}", bold=True)}')

    click.echo('The scrubbed subtitle holds no image, only what is needed to reproduce the error.')
    click.echo(f'Attach it to a new issue: {click.style(f"{__url__}/issues", bold=True)}')


def echo_paths(paths: list[Skipped], label: str, color: str, limit: int | None) -> None:
    """Print each path with the reason why it was not ripped."""
    for path, reason in paths[:limit] if limit else paths:
        click.echo(f'{click.style(path, fg=color, bold=True)} {label}: {reason}')

    remaining = len(paths) - limit if limit else 0
    if remaining > 0:
        click.echo(f'... and {remaining} more, use {click.style("-v", bold=True)} to see them all')


def configure_logging(ctx: click.Context, debug: bool, log_file: str | None) -> None:
    """Send debug messages to the console, to a log file, or to both, until the command ends."""
    if not debug and not log_file:
        return

    level = logger.level
    handlers: list[logging.Handler] = []

    def restore() -> None:
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        logger.setLevel(level)

    ctx.call_on_close(restore)
    logger.setLevel(logging.DEBUG)
    if debug:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
        handlers.append(stream_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf8')
        file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
        handlers.append(file_handler)

    for handler in handlers:
        logger.addHandler(handler)


def log_environment(ctx: click.Context | None = None) -> None:
    """Record the installed versions, and the checks of the selected plug-ins, at the top of the debug log."""
    if not logger.isEnabledFor(logging.DEBUG):
        return

    checks = source_checks()
    if ctx:
        checks += (
            plugin_checks(ctx, ENGINE_KIND, engine_names(ctx.params))
            + (AutoEngine.check({}) if ctx.params['engine'] == (AUTO,) else [])
            + plugin_checks(ctx, POST_PROCESSOR_KIND, post_processor_names(ctx.params))
        )
    for line in format_checks(run_checks(checks)).splitlines():
        logger.info(line)


def scan_paths(paths: tuple[str, ...], options: Options) -> ScanResult:
    """The media files of all the paths, in one result."""
    result = ScanResult([], [], [])
    for path in paths:
        media, filtered_out, ignored = api.scan(path, options)
        result.media.extend(media)
        result.filtered_out.extend(filtered_out)
        result.ignored.extend(ignored)

    return result


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
        os.path.join(directory, f'{name}{extension}')
        for directory, name in ((AppDirs('pgsrip').user_config_dir, 'config'), (os.getcwd(), 'pgsrip'))
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
    help='Configuration file (.json, .yml or .yaml) with default option values (can be used multiple times).',
)
language_option = click.option(
    '-l',
    '--language',
    type=LANGUAGE,
    multiple=True,
    help='Language as IETF code, e.g. en, pt-BR (can be used multiple times).',
)
#: the help of --all is different for each command
all_option = functools.partial(click.option, '--all', 'all_tracks', is_flag=True, default=False)
debug_option = click.option(
    '--debug', is_flag=True, help='Print useful information for debugging and for reporting bugs.'
)
log_file_option = click.option(
    '--log-file',
    type=click.Path(dir_okay=False, writable=True),
    help='Write a full debug log to this file, to attach it to a bug report.',
)


@pgsrip.command(cls=PluginCommand)
@config_option
@language_option
@click.option('-e', '--encoding', help='Write the subtitle files with this encoding.')
@click.option('-a', '--age', type=AGE, help='Rip only the videos that are newer than AGE, e.g. 12h, 1w2d.')
@click.option(
    '-A',
    '--output-age',
    type=AGE,
    help='With --force, do not write again a subtitle file newer than AGE, e.g. 12h, 1w2d.',
)
@click.option(
    '--format',
    'formats',
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
    help='Rip again and replace the subtitle files that exist.',
)
@all_option(help='Rip all the selected tracks. Do not remove duplicates.')
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
    '--workers',
    type=click.IntRange(1, 50),
    default=None,
    help='Number of OCR jobs to run in parallel, e.g. tesseract processes. '
    f'Default: the number of CPUs, at most {MAX_DEFAULT_WORKERS}.',
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
@click.option('--no-post-processor', is_flag=True, help='Do not change the text after the OCR engines.')
@click.option(
    '--keep-temp-files',
    is_flag=True,
    help='Do not delete the temporary files, e.g. the extracted .sup files, the PNG files and other debug files.',
)
@debug_option
@log_file_option
@click.option(
    '-v',
    '--verbose',
    count=True,
    help='List all the ignored paths. Use -vv to also list the filtered-out paths.',
)
@click.argument('path', type=click.Path(), required=True, nargs=-1)
@click.pass_context
def rip(
    ctx: click.Context,
    /,
    language: tuple[Language, ...],
    encoding: str | None,
    age: timedelta | None,
    output_age: timedelta | None,
    formats: tuple[str, ...],
    force: bool,
    all_tracks: bool,
    with_flags: tuple[str, ...],
    without_flags: tuple[str, ...],
    one_per_language: bool,
    debug: bool,
    log_file: str | None,
    workers: int | None,
    engine: tuple[str, ...],
    post_processor: tuple[str, ...],
    no_post_processor: bool,
    keep_temp_files: bool,
    verbose: int,
    path: tuple[str, ...],
    **plugin_params: typing.Any,
) -> None:
    """Rip the PGS subtitles of each media PATH into subtitle files."""
    try:
        configure_logging(ctx, debug, log_file)
    except OSError as e:
        raise click.FileError(str(log_file), hint=str(e)) from e

    options = Options(
        languages=frozenset(language),
        encoding=encoding,
        force=force,
        all_tracks=all_tracks,
        one_per_language=one_per_language,
        with_flags=frozenset(with_flags),
        without_flags=frozenset(without_flags),
        age=age,
        output_age=output_age,
        engines=create_engines(ctx),
        post_processors=create_post_processors(ctx),
        # one writer for each format, in the order of the option
        writers=[WRITERS_BY_NAME[name]() for name in dict.fromkeys(formats)],
    )
    # the temporary directory of the run is removed when the command ends, also on an error
    workspace = ctx.with_resource(Workspace(keep=keep_temp_files))

    log_environment(ctx)

    media_files, filtered_out_paths, ignored_paths = scan_paths(path, options)

    if verbose > 1:
        echo_paths(filtered_out_paths, 'filtered out', 'yellow', limit=None)
    echo_paths(ignored_paths, 'ignored', 'red', limit=None if debug or verbose else MAX_REPORTED_PATHS)

    collected_subtitles: list[Subtitle] = []
    # the plain lists and the debug messages replace the progress bars
    hidden = debug or verbose > 0
    medias_progressbar = click.progressbar(
        media_files,
        label='Collecting PGS subtitles',
        item_show_func=lambda item: str(item or ''),
        hidden=hidden,
    )

    with medias_progressbar as bar:
        for m in bar:
            collected_subtitles.extend(api.pending(m.subtitles(options, workspace), options))

    # report collected medias
    report = (
        f'{click.style(str(len(collected_subtitles)), bold=True, fg="green")} '
        f'PGS subtitle{"s" if len(collected_subtitles) > 1 else ""} collected '
        f'from {click.style(str(len(media_files)), bold=True, fg="green")} '
        f'file{"s" if len(media_files) > 1 else ""}'
    )
    if filtered_out_paths:
        report += (
            f' / {click.style(str(len(filtered_out_paths)), bold=True, fg="yellow")} '
            f'file{"s" if len(filtered_out_paths) > 1 else ""} filtered out'
        )
    if ignored_paths:
        report += (
            f' / {click.style(str(len(ignored_paths)), bold=True, fg="red")} '
            f'path{"s" if len(ignored_paths) > 1 else ""} ignored'
        )
    click.echo(report)

    try:
        api.prepare(collected_subtitles, options, reporter=click.echo)
    except OcrError as e:
        click.echo(click.style(str(e), fg='red'))
        raise SystemExit(1) from e

    subtitles_progressbar = click.progressbar(
        collected_subtitles,
        label='Ripping subtitles',
        update_min_steps=0,
        item_show_func=lambda s: click.style(str(s or ''), bold=True),
        hidden=hidden,
    )

    ripped_count = 0
    failures: list[tuple[Subtitle, Exception]] = []
    with subtitles_progressbar as bar:
        for subtitle in bar:
            bar.update(0, subtitle)
            try:
                ripped_count += api.rip(subtitle, options)
            except Exception as e:
                logger.warning(
                    'Cannot rip %s: <%s> %s',
                    subtitle,
                    type(e).__name__,
                    e,
                    exc_info=logger.isEnabledFor(logging.DEBUG),
                )
                failures.append((subtitle, e))

    # report ripped subtitles
    click.echo(
        f'{click.style(str(ripped_count), bold=True, fg="green")} '
        f'PGS subtitle{"s" if ripped_count > 1 else ""} ripped from '
        f'{click.style(str(len(media_files)), bold=True, fg="blue")} '
        f'file{"s" if len(media_files) > 1 else ""}'
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
    (auto,) = AutoEngine.check({})
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
@language_option
@all_option(help='Scrub all the selected tracks. Do not remove duplicates.')
@click.option(
    '--keep-name',
    is_flag=True,
    default=False,
    help='Name the output after the media file, instead of after a hash of its name.',
)
@debug_option
@log_file_option
@click.argument('path', type=click.Path(), required=True, nargs=-1)
@click.pass_context
def scrub(
    ctx: click.Context,
    /,
    output: str | None,
    redact: str,
    keep_images: tuple[frozenset[int], ...],
    only: tuple[frozenset[int], ...],
    language: tuple[Language, ...],
    all_tracks: bool,
    keep_name: bool,
    debug: bool,
    log_file: str | None,
    path: tuple[str, ...],
) -> None:
    """Copy the PGS subtitles of each media PATH without the subtitle images.

    The result is a .sup file that pgsrip reads like any other one. It keeps the timing, the
    layout and the palettes, which is what almost every bug is about, and it is small enough to
    attach to a bug report.
    """
    try:
        configure_logging(ctx, debug, log_file)
    except OSError as e:
        raise click.FileError(str(log_file), hint=str(e)) from e

    redaction = Redaction(redact)
    options = Options(languages=frozenset(language), all_tracks=all_tracks)
    workspace = ctx.with_resource(Workspace())
    log_environment()

    media_files, _, ignored_paths = scan_paths(path, options)

    echo_paths(ignored_paths, 'ignored', 'red', limit=None if debug else MAX_REPORTED_PATHS)
    if not media_files:
        click.echo(click.style('No media to scrub', fg='red'))
        raise SystemExit(1)

    written, failed = scrub_media_files(
        media_files, options, workspace, redaction, keep_images, only, output, keep_name
    )
    if written:
        if redaction == Redaction.NONE:
            click.echo(click.style('The scrubbed files hold the original subtitle images.', fg='yellow'))
        else:
            click.echo('The scrubbed files hold no subtitle image, only timing, layout and palettes.')

        click.echo(f'Attach them to a new issue: {click.style(f"{__url__}/issues", bold=True)}')

    if failed:
        raise SystemExit(1)


def scrub_media_files(
    medias: list[Media],
    options: Options,
    workspace: Workspace,
    redaction: Redaction,
    keep_images: tuple[frozenset[int], ...],
    only: tuple[frozenset[int], ...],
    output: str | None,
    keep_name: bool,
) -> tuple[list[str], int]:
    """Write a scrubbed .sup file for every PGS subtitle of every media. Return their paths, and the number of
    subtitles that could not be scrubbed."""
    kept = merge_ranges(keep_images)
    selected = merge_ranges(only) or None
    used: set[str] = set()
    written: list[str] = []
    failed = 0
    for media in medias:
        for subtitle in media.subtitles(options, workspace):
            with subtitle:
                try:
                    data, stats = scrub_data(subtitle.read(), str(subtitle), redaction, kept, selected)
                except Exception as e:
                    logger.debug('Cannot scrub %s', subtitle, exc_info=True)
                    click.echo(click.style(f'Cannot scrub {subtitle}: <{type(e).__name__}> {e}', fg='red'))
                    failed += 1
                    continue

                target = output_path(subtitle.output_base, output, keep_name, used)
                with open(target, 'wb') as f:
                    f.write(data)

                written.append(target)
                click.echo(f'{click.style(target, bold=True, fg="green")} written: {stats}')

    return written, failed


def default_name(media_path: MediaPath, keep_name: bool) -> str:
    """Name the scrubbed file after the media, or after a hash of its name."""
    name = os.path.basename(media_path.base_path)
    if keep_name:
        return name

    return f'pgsrip-{hashlib.sha256(name.encode("utf8")).hexdigest()[:8]}'


def output_path(media_path: MediaPath, output: str | None, keep_name: bool, used: set[str]) -> str:
    """Build the path of the scrubbed file, without ever reusing one or writing over the source .sup.

    `media_path` has the language, the flags and the track number of the subtitle, e.g. `Subtitle.output_base`.
    The scrubbed file has the same name format as a ripped .srt: <base>.<language>[.<flag>]*[.track<n>].sup.
    """
    source = os.path.normcase(os.path.abspath(str(media_path)))
    if output and output.lower().endswith(SUP_EXTENSION):
        base = output[: -len(SUP_EXTENSION)]
    elif output and (os.path.isdir(output) or output.endswith(('/', os.sep))):
        base = os.path.join(output, default_name(media_path, keep_name))
    elif output:
        base = output
    else:
        base = default_name(media_path, keep_name)

    target = media_path.replace(base_path=base, extension=SUP_EXTENSION[1:])
    path = str(target)
    while path in used or os.path.normcase(os.path.abspath(path)) == source:
        # the first free name is .track2, like the second track of a group in `Media.subtitles`
        target = target.replace(track_number=2 if target.track_number is None else target.track_number + 1)
        path = str(target)

    used.add(path)

    return path
