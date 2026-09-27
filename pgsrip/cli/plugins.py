from __future__ import annotations

import dataclasses
import importlib.metadata
import logging
import typing

import click
from click.core import ParameterSource

from pgsrip.diagnostics import Check
from pgsrip.engines.auto import AutoEngine
from pgsrip.engines.base import OcrEngine, OcrEngineFactory, OcrError
from pgsrip.engines.rapidocr import RapidOcrEngine
from pgsrip.engines.tesseract import TesseractEngine
from pgsrip.postprocessors.base import PostProcessor, PostProcessorFactory
from pgsrip.postprocessors.cleanit import CleanitPostProcessor

logger = logging.getLogger(__name__)


Factory = type[OcrEngineFactory] | type[PostProcessorFactory]

ENGINES: dict[str, Factory] = {'tesseract': TesseractEngine, 'rapidocr': RapidOcrEngine}
#: a reserved engine name, not a plug-in: tesseract for each language that it can read, else rapidocr
AUTO = 'auto'
AUTO_ENGINES = ('tesseract', 'rapidocr')
#: other packages add an OCR engine with an entry point in this group. See docs/usage.md.
ENGINE_ENTRY_POINTS = 'pgsrip.engines'
POST_PROCESSORS: dict[str, Factory] = {'cleanit': CleanitPostProcessor}
#: other packages add a post-processor with an entry point in this group. See docs/usage.md.
POST_PROCESSOR_ENTRY_POINTS = 'pgsrip.postprocessors'


@dataclasses.dataclass(frozen=True)
class PluginKind:
    """OCR engines or post-processors: the two kinds of plug-in share the option mechanism."""

    #: e.g. OCR engine
    label: str
    #: the article of the label, e.g. an
    article: str
    builtins: dict[str, Factory]
    #: the entry point group of the plug-ins of other packages
    group: str
    #: the click parameter name of the chain, e.g. engine
    chain: str
    #: each plug-in gets a --<plugin>-workers option
    workers: bool

    @property
    def flag(self) -> str:
        """The command line flag of the chain, e.g. --engine."""
        return f'--{self.chain}'.replace('_', '-')


ENGINE_KIND = PluginKind('OCR engine', 'an', ENGINES, ENGINE_ENTRY_POINTS, 'engine', workers=True)
POST_PROCESSOR_KIND = PluginKind(
    'post-processor', 'a', POST_PROCESSORS, POST_PROCESSOR_ENTRY_POINTS, 'post_processor', workers=False
)
KINDS = (ENGINE_KIND, POST_PROCESSOR_KIND)


def plugin_entry_points(kind: PluginKind) -> dict[str, importlib.metadata.EntryPoint]:
    """The plug-ins of other packages, by name. A built-in engine or post-processor wins over a plug-in with the
    same name: the two kinds share the --<name>- options. No plug-in can be named auto."""
    builtins = {AUTO, *(name for k in KINDS for name in k.builtins)}
    return {ep.name: ep for ep in importlib.metadata.entry_points(group=kind.group) if ep.name not in builtins}


def load_plugins(ctx: click.Context | None, kind: PluginKind) -> dict[str, Factory]:
    """The built-in plug-ins, then the plug-ins of other packages. A plug-in that cannot be loaded is left out."""
    plugins = dict(kind.builtins)
    # an OCR engine wins over a post-processor with the same name
    engines = installed_plugins(ctx, ENGINE_KIND) if kind is POST_PROCESSOR_KIND else {}
    for name, entry_point in plugin_entry_points(kind).items():
        if name in engines:
            logger.warning('The post-processor %s is ignored: an OCR engine has the same name', name)
            continue
        try:
            plugins[name] = entry_point.load()
        except Exception as e:
            # a broken plug-in must not stop the other plug-ins
            logger.warning('Cannot load the %s %s: <%s> %s', kind.label, name, type(e).__name__, e)

    return plugins


def installed_plugins(ctx: click.Context | None, kind: PluginKind) -> dict[str, Factory]:
    """The plug-ins of a kind, loaded one time for each run of a command."""
    if ctx is None:
        return load_plugins(ctx, kind)
    if kind.group not in ctx.meta:
        ctx.meta[kind.group] = load_plugins(ctx, kind)

    return typing.cast(dict[str, Factory], ctx.meta[kind.group])


def param_name(plugin: str, name: str) -> str:
    """The click parameter name of a plug-in option, e.g. tesseract_threshold."""
    return f'{plugin}_{name}'.replace('-', '_')


def option_flag(plugin: str, name: str) -> str:
    """The command line flag of a plug-in option, e.g. --tesseract-threshold."""
    return f'--{plugin}-{name}'.replace('_', '-')


def plugin_options(kind: PluginKind, plugins: dict[str, Factory]) -> list[click.Option]:
    """The --<plugin>-<name> options of each plug-in, and the --<engine>-workers option of each engine."""
    options: list[click.Option] = []
    for plugin, factory in plugins.items():
        for option in factory.options:
            flag = option_flag(plugin, option.name)
            options.append(
                click.Option(
                    [
                        *option.aliases,
                        f'{flag}/--no-{flag[2:]}' if option.flag else flag,
                        param_name(plugin, option.name),
                    ],
                    type=None if option.flag else option.type,
                    default=bool(option.default) if option.flag else option.default,
                    multiple=option.multiple,
                    help=option.help,
                    envvar=option.envvar,
                    show_envvar=bool(option.envvar),
                )
            )
        if kind.workers:
            options.append(
                click.Option(
                    [option_flag(plugin, 'workers'), param_name(plugin, 'workers')],
                    type=click.IntRange(1, 50),
                    help=f'Number of {plugin} jobs to run in parallel. Default: -w.',
                )
            )

    return options


class PluginCommand(click.Command):
    """A command with the options of every OCR engine and post-processor. The plug-ins are known only when the
    command runs."""

    def get_params(self, ctx: click.Context) -> list[click.Parameter]:
        params = super().get_params(ctx)
        for kind in KINDS:
            key = f'{kind.group}.options'
            if key not in ctx.meta:
                ctx.meta[key] = plugin_options(kind, installed_plugins(ctx, kind))
            # after the chain option, or before --help
            index = next(
                (i + 1 for i, p in enumerate(params) if p.name == kind.chain),
                next((i for i, p in enumerate(params) if p.name == 'help'), len(params)),
            )
            params = [*params[:index], *ctx.meta[key], *params[index:]]

        return params


def plugin_settings(plugin: str, factory: Factory, params: dict[str, typing.Any]) -> dict[str, typing.Any]:
    """The option values of one plug-in, by option name."""
    return {option.name: params[param_name(plugin, option.name)] for option in factory.options}


class PluginParamType(click.ParamType[str, str]):
    def __init__(self, kind: PluginKind):
        self.kind = kind
        self.name = kind.label

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> str:
        # not a click.Choice: the plug-ins are known only when the command runs
        names = [*([AUTO] if self.kind is ENGINE_KIND else []), *installed_plugins(ctx, self.kind)]
        if value not in names:
            self.fail(
                f'{click.style(value, bold=True)} is not {self.kind.article} {self.kind.label}. '
                f'Choose from: {", ".join(names)}'
            )

        return value


ENGINE = PluginParamType(ENGINE_KIND)
POST_PROCESSOR = PluginParamType(POST_PROCESSOR_KIND)


def plugin_checks(ctx: click.Context, kind: PluginKind, names: typing.Iterable[str]) -> list[Check]:
    """The checks of these plug-ins, with the option values of the command."""
    installed = installed_plugins(ctx, kind)
    checks: list[Check] = []
    for name in names:
        check = getattr(installed[name], 'check', None)
        if not check:
            continue
        try:
            checks += check(plugin_settings(name, installed[name], ctx.params))
        except Exception as e:
            # a broken check of a plug-in must not hide the other checks
            logger.debug('Cannot check the %s %s', kind.label, name, exc_info=True)
            checks.append(Check(name, f'check failed: <{type(e).__name__}> {e}', ok=False))

    return checks


def engine_names(params: dict[str, typing.Any]) -> tuple[str, ...]:
    """The OCR engines that the user selected, in order. auto gives the engines that it uses."""
    names = typing.cast(tuple[str, ...], params['engine'])
    if AUTO not in names:
        return names
    if len(names) > 1:
        raise click.UsageError(f'use --engine {AUTO} alone')

    return AUTO_ENGINES


def post_processor_names(params: dict[str, typing.Any]) -> tuple[str, ...]:
    """The chain of post-processors that the user selected, in order."""
    return () if params['no_post_process'] else typing.cast(tuple[str, ...], params['post_processor'])


def selected_plugins(
    ctx: click.Context, kind: PluginKind, names: tuple[str, ...]
) -> list[tuple[str, Factory, dict[str, typing.Any]]]:
    """The name, the class, and the settings of each selected plug-in, in order. Reject the options of the
    other plug-ins."""
    if len(set(names)) < len(names):
        raise click.UsageError(f'use each {kind.flag} only one time')

    installed = installed_plugins(ctx, kind)
    for plugin, factory in installed.items():
        # only the command line: a config file or an environment variable can hold the options of an unused plug-in
        option_names = [param_name(plugin, option.name) for option in factory.options]
        if kind.workers:
            option_names.append(param_name(plugin, 'workers'))
        if plugin not in names and any(
            ctx.get_parameter_source(n) == ParameterSource.COMMANDLINE for n in option_names
        ):
            raise click.UsageError(f'the --{plugin}-* options need {kind.flag} {plugin}')

    selected = []
    for name in names:
        factory = installed[name]
        settings = plugin_settings(name, factory, ctx.params)
        for option in factory.options:
            if option.required and settings[option.name] is None:
                raise click.UsageError(f'{kind.flag} {name} needs {option_flag(name, option.name)}')
        selected.append((name, factory, settings))

    return selected


def create_engines(ctx: click.Context) -> list[OcrEngine]:
    """Create the chain of OCR engines that the user selected, in order."""
    engines: list[OcrEngine] = []
    for name, factory, settings in selected_plugins(ctx, ENGINE_KIND, engine_names(ctx.params)):
        workers = ctx.params[param_name(name, 'workers')] or ctx.params['max_workers']
        try:
            engines.append(typing.cast(type[OcrEngineFactory], factory).from_settings(settings, workers))
        except OcrError as e:
            raise click.UsageError(str(e)) from e

    if ctx.params['engine'] == (AUTO,):
        tesseract, rapidocr = engines
        return [AutoEngine(typing.cast(TesseractEngine, tesseract), typing.cast(RapidOcrEngine, rapidocr))]

    return engines


def create_post_processors(ctx: click.Context) -> list[PostProcessor]:
    """Create the chain of post-processors that the user selected, in order."""
    if ctx.params['no_post_process'] and ctx.get_parameter_source('post_processor') == ParameterSource.COMMANDLINE:
        raise click.UsageError('use --post-processor or --no-post-process, not both')

    post_processors: list[PostProcessor] = []
    for _, factory, settings in selected_plugins(ctx, POST_PROCESSOR_KIND, post_processor_names(ctx.params)):
        try:
            post_processors.append(typing.cast(type[PostProcessorFactory], factory).from_settings(settings))
        except ValueError as e:
            raise click.UsageError(str(e)) from e

    return post_processors
