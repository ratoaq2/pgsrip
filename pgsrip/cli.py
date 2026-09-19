from __future__ import annotations

import logging
import os
import re
import typing
from datetime import timedelta
from types import TracebackType

import click
from babelfish import Error as BabelfishError
from babelfish import Language

from pgsrip import Pgs, __version__, api
from pgsrip.core import get_reason
from pgsrip.diagnostics import format_checks, run_checks
from pgsrip.media import Media
from pgsrip.options import Options
from pgsrip.tessdata import REPOSITORIES, Tessdata, TessdataError, get_required_codes

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


LANGUAGE = LanguageParamType()
AGE = AgeParamType()

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


def log_environment(options: Options) -> None:
    """Record the installed versions at the top of the debug log."""
    if not logger.isEnabledFor(logging.DEBUG):
        return

    for line in format_checks(run_checks(options)).splitlines():
        logger.info(line)


def download_tessdata(pgs_medias: list[Pgs], options: Options) -> None:
    """Download the tesseract data every collected subtitle needs, before any ripping starts."""
    if not pgs_medias:
        return

    def report(code: str) -> None:
        click.echo(f'Downloading tesseract data for {click.style(code, bold=True)}...')

    psm_value = options.tesseract_psm.value if options.tesseract_psm else None
    codes = get_required_codes([pgs.language for pgs in pgs_medias], psm_value)
    try:
        Tessdata.from_options(options).ensure(codes, reporter=report)
    except TessdataError as e:
        click.echo(click.style(str(e), fg='red'))


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


@pgsrip.command()
@click.option('-c', '--config', type=click.Path(), help='cleanit configuration path to be used')
@click.option(
    '-l',
    '--language',
    type=LANGUAGE,
    multiple=True,
    help='Language as IETF code, e.g. en, pt-BR (can be used multiple times).',
)
@click.option(
    '-t',
    '--tag',
    required=False,
    multiple=True,
    help='Rule tags to be used, e.g. ocr, tidy, no-sdh, no-style, no-lyrics, no-spam (can be used multiple times). ',
)
@click.option('-e', '--encoding', help='Save subtitles using the following encoding.')
@click.option('-a', '--age', type=AGE, help='Filter videos newer than AGE, e.g. 12h, 1w2d.')
@click.option('-A', '--srt-age', type=AGE, help='Filter videos which srt subtitles are newer than AGE, e.g. 12h, 1w2d.')
@click.option(
    '-f',
    '--force',
    is_flag=True,
    default=False,
    help='re-rip and overwrite existing srt subtitles, even if they already exist',
)
@click.option(
    '--all',
    is_flag=True,
    default=False,
    help='rip all tracks for a given language, even another track for that language was already ripped',
)
@click.option('-w', '--max-workers', type=click.IntRange(1, 50), default=None, help='Maximum number of threads to use.')
@click.option(
    '--tessdata-dir',
    type=click.Path(),
    help='Directory where tesseract data is stored. Defaults to TESSDATA_PREFIX or a user cache directory.',
)
@click.option(
    '--tessdata-repository',
    type=click.Choice(sorted(REPOSITORIES)),
    default=None,
    help='Repository to download missing tesseract data from.',
)
@click.option(
    '--no-tessdata-download',
    is_flag=True,
    default=False,
    help='Do not download missing tesseract data, only use what is already installed.',
)
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
def rip(
    config: str | None,
    language: tuple[Language] | None,
    tag: tuple[str] | None,
    encoding: str | None,
    age: timedelta | None,
    srt_age: timedelta | None,
    force: bool,
    all: bool,
    debug: bool,
    log_file: str | None,
    max_workers: int | None,
    tessdata_dir: str | None,
    tessdata_repository: str | None,
    no_tessdata_download: bool,
    keep_temp_files: bool,
    verbose: int,
    path: tuple[str],
) -> None:
    """Rip the PGS subtitles of each media PATH into SRT."""
    try:
        configure_logging(debug, log_file)
    except OSError as e:
        click.echo(click.style(f'Cannot write the log file: {e}', fg='red'))
        return

    if config and (not os.path.isfile(config) or os.path.isdir(config)):
        click.echo(f'Invalid configuration is defined: {click.style(config, bold=True)}')
        return

    options = Options(
        config_path=config,
        languages=set(language or []),
        tags=set(tag or []),
        encoding=encoding,
        overwrite=force,
        one_per_lang=not all,
        keep_temp_files=keep_temp_files,
        max_workers=max_workers,
        tessdata_dir=tessdata_dir,
        tessdata_repository=tessdata_repository,
        download_tessdata=not no_tessdata_download,
        age=age,
        srt_age=srt_age,
    )

    log_environment(options)

    rules = options.config.select_rules(tags=options.tags, languages=options.languages)
    if not rules:
        values = tuple(options.tags) + tuple(str(lang) for lang in options.languages)
        click.echo(f'No rules defined for {click.style(", ".join(values), bold=True)}')
        return

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

    download_tessdata(collected_pgs_medias, options)

    pgs_progressbar = DebugProgressBar(
        debug or verbose > 1,
        collected_pgs_medias,
        label='Ripping subtitles',
        update_min_steps=0,
        item_show_func=lambda s: click.style(str(s or ''), bold=True),
    )

    ripped_count = 0
    with pgs_progressbar as bar:
        for pgs in bar:
            bar.update(0, pgs)
            ripped_count += api.rip_pgs(pgs, options)

    # report ripped subtitles
    click.echo(
        f'{click.style(str(ripped_count), bold=True, fg="green")} '
        f'PGS subtitle{"s" if ripped_count > 1 else ""} ripped from '
        f'{click.style(str(len(collected_medias)), bold=True, fg="blue")} '
        f'file{"s" if len(collected_medias) > 1 else ""}'
    )

    if log_file:
        click.echo(f'Debug log written to {click.style(log_file, bold=True)}')


@pgsrip.command()
@click.option(
    '--tessdata-dir',
    type=click.Path(),
    help='Directory where tesseract data is stored. Defaults to TESSDATA_PREFIX or a user cache directory.',
)
@click.option(
    '--tessdata-repository',
    type=click.Choice(sorted(REPOSITORIES)),
    default=None,
    help='Repository to download missing tesseract data from.',
)
def doctor(tessdata_dir: str | None, tessdata_repository: str | None) -> None:
    """Check that everything pgsrip needs is installed. Add the output to a bug report."""
    checks = run_checks(Options(tessdata_dir=tessdata_dir, tessdata_repository=tessdata_repository))
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
