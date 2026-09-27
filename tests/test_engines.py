"""The chain of OCR engines, and the OCR engines of other packages (`pgsrip.engines` entry points)."""

from __future__ import annotations

import importlib.metadata
import shutil
import tempfile
import types
import typing

import pysrt
import pytest
from click.testing import CliRunner

from pgsrip.cli import ENGINE_ENTRY_POINTS, pgsrip
from pgsrip.ripper import EngineOption
from pgsrip.tesseract import TesseractEngine
from pgsrip.tsv import TsvData

from .fabricate import SAMPLE

if typing.TYPE_CHECKING:
    from babelfish import Language

    from pgsrip.media import Pgs, PgsSubtitleItem


class PluginEngine:
    """An engine of another package: it reads every cue as 'Plugin <index>'."""

    #: the item indexes of each recognize call
    calls: typing.ClassVar[list[list[int]]] = []
    #: the engines that the plug-in factory created
    created: typing.ClassVar[list[PluginEngine]] = []

    options: typing.ClassVar[tuple[EngineOption, ...]] = ()

    def __init__(self, workers: int | None = None):
        self.workers = workers
        PluginEngine.created.append(self)

    @classmethod
    def from_settings(cls, settings: dict[str, typing.Any], workers: int | None) -> PluginEngine:
        return cls(workers=workers)

    def prepare(
        self, languages: typing.Iterable[Language], reporter: typing.Callable[[str], None] | None = None
    ) -> None:
        pass

    def recognize(self, pgs: Pgs, items: list[PgsSubtitleItem]) -> None:
        PluginEngine.calls.append([item.index for item in items])
        for item in items:
            item.text = f'Plugin {item.index}'


class BlindEngine(PluginEngine):
    """An engine of another package that reads nothing."""

    def recognize(self, pgs: Pgs, items: list[PgsSubtitleItem]) -> None:
        PluginEngine.calls.append([item.index for item in items])


class TunedEngine(PluginEngine):
    """An engine of another package with its own options."""

    options = (
        EngineOption('model', help='Model of the tuned engine.'),
        EngineOption('size', int, default=1, envvar='PGSRIP_TUNED_SIZE'),
        EngineOption('fast', flag=True, default=True),
    )
    #: the settings of each created engine
    settings: typing.ClassVar[list[dict[str, typing.Any]]] = []

    @classmethod
    def from_settings(cls, settings: dict[str, typing.Any], workers: int | None) -> PluginEngine:
        TunedEngine.settings.append(settings)
        return cls(workers=workers)


class RemoteEngine(PluginEngine):
    """An engine of another package that cannot work without its url."""

    options = (EngineOption('url', required=True),)


@pytest.fixture
def media_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: typing.Any) -> typing.Any:
    """A directory with the placeholder sample (3 cues), and a temporary folder of its own."""
    temp_dir = tmp_path / 'temp'
    temp_dir.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(temp_dir))
    media = tmp_path / 'media'
    media.mkdir()
    shutil.copy(SAMPLE, media)
    return media


@pytest.fixture(autouse=True)
def plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    PluginEngine.calls = []
    PluginEngine.created = []
    TunedEngine.settings = []
    monkeypatch.delenv('PGSRIP_TUNED_SIZE', raising=False)
    entry_points = [
        importlib.metadata.EntryPoint('plugin', f'{__name__}:PluginEngine', ENGINE_ENTRY_POINTS),
        importlib.metadata.EntryPoint('blind', f'{__name__}:BlindEngine', ENGINE_ENTRY_POINTS),
        importlib.metadata.EntryPoint('tuned', f'{__name__}:TunedEngine', ENGINE_ENTRY_POINTS),
        importlib.metadata.EntryPoint('remote', f'{__name__}:RemoteEngine', ENGINE_ENTRY_POINTS),
        importlib.metadata.EntryPoint('broken', f'{__name__}:MissingEngine', ENGINE_ENTRY_POINTS),
        importlib.metadata.EntryPoint('tesseract', f'{__name__}:PluginEngine', ENGINE_ENTRY_POINTS),
    ]
    monkeypatch.setattr(
        'pgsrip.cli.importlib.metadata.entry_points',
        lambda group: [ep for ep in entry_points if ep.group == group],
    )


@pytest.fixture
def fake_tesseract(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Tesseract reads every cue as 'Tesseract <index>'. Add an index to the list to make that cue doubtful."""
    doubtful: list[int] = []

    def recognize(engine: TesseractEngine, pgs: Pgs, items: list[PgsSubtitleItem]) -> None:
        for item in items:
            item.text = f'Tesseract {item.index}'
            item.doubtful = item.index in doubtful

    monkeypatch.setattr(TesseractEngine, 'prepare', lambda *args, **kwargs: None)
    monkeypatch.setattr(TesseractEngine, 'recognize', recognize)
    return doubtful


@pytest.fixture
def blind_tesseract(monkeypatch: pytest.MonkeyPatch) -> list[TesseractEngine]:
    """Tesseract reads nothing. The list gets each tesseract engine that recognize was called on."""
    engines: list[TesseractEngine] = []
    monkeypatch.setattr(TesseractEngine, 'prepare', lambda *args, **kwargs: None)
    monkeypatch.setattr(TesseractEngine, 'recognize', lambda engine, *args: engines.append(engine))
    return engines


def rip(*args: str) -> typing.Any:
    return CliRunner().invoke(pgsrip, ['rip', *args])


def read_texts(media_dir: typing.Any) -> list[str]:
    return [item.text for item in pysrt.open(str(media_dir / 'placeholder.en.srt'), encoding='utf-8')]


def test_a_plugin_engine_rips_the_cues(media_dir: typing.Any) -> None:
    result = rip('--engine', 'plugin', str(media_dir))

    assert result.exit_code == 0, result.output
    assert read_texts(media_dir) == ['Plugin 0', 'Plugin 1', 'Plugin 2']


def test_the_next_engine_reads_only_the_doubtful_cues(media_dir: typing.Any, fake_tesseract: list[int]) -> None:
    fake_tesseract.append(1)

    result = rip('--engine', 'tesseract', '--engine', 'plugin', str(media_dir))

    assert result.exit_code == 0, result.output
    assert PluginEngine.calls == [[1]]
    assert read_texts(media_dir) == ['Tesseract 0', 'Plugin 1', 'Tesseract 2']


def test_no_doubtful_cue_does_not_call_the_next_engine(media_dir: typing.Any, fake_tesseract: list[int]) -> None:
    result = rip('--engine', 'tesseract', '--engine', 'plugin', str(media_dir))

    assert result.exit_code == 0, result.output
    assert PluginEngine.calls == []
    assert read_texts(media_dir) == ['Tesseract 0', 'Tesseract 1', 'Tesseract 2']


def test_a_next_engine_that_reads_nothing_keeps_the_text_before_it(
    media_dir: typing.Any, fake_tesseract: list[int]
) -> None:
    fake_tesseract.append(1)

    result = rip('--engine', 'tesseract', '--engine', 'blind', '--engine', 'plugin', str(media_dir))

    # the doubtful cue keeps its text, and stays doubtful: the third engine reads it
    assert result.exit_code == 0, result.output
    assert PluginEngine.calls == [[1], [1]]
    assert read_texts(media_dir) == ['Tesseract 0', 'Plugin 1', 'Tesseract 2']


@pytest.mark.usefixtures('blind_tesseract')
def test_a_plugin_cannot_replace_a_built_in_engine(media_dir: typing.Any) -> None:
    result = rip('--engine', 'tesseract', '--engine', 'plugin', str(media_dir))

    # the built-in tesseract reads nothing here, so the plug-in reads every cue
    assert result.exit_code == 0, result.output
    assert read_texts(media_dir) == ['Plugin 0', 'Plugin 1', 'Plugin 2']


def test_an_unknown_engine_is_rejected(media_dir: typing.Any) -> None:
    result = rip('--engine', 'nope', str(media_dir))

    assert result.exit_code == 2
    assert 'nope is not an OCR engine. Choose from: tesseract, plugin, blind, tuned, remote' in result.output


def test_an_engine_is_rejected_the_second_time(media_dir: typing.Any) -> None:
    result = rip('--engine', 'plugin', '--engine', 'plugin', str(media_dir))

    assert result.exit_code == 2
    assert 'use each --engine only one time' in result.output


@pytest.mark.parametrize(
    'option',
    [
        ['--tesseract-threshold', '50'],
        ['--tesseract-workers', '2'],
        ['--tesseract-dir', 'tessdata'],
        ['--tesseract-repository', 'fast'],
        ['--no-tesseract-download'],
    ],
)
def test_the_tesseract_options_need_the_tesseract_engine(option: list[str], media_dir: typing.Any) -> None:
    result = rip('--engine', 'plugin', *option, str(media_dir))

    assert result.exit_code == 2
    assert 'the --tesseract-* options need --engine tesseract' in result.output


def test_the_tesseract_threshold_option_sets_the_engine_threshold(
    media_dir: typing.Any, blind_tesseract: list[TesseractEngine]
) -> None:
    result = rip('--tesseract-threshold', '50', str(media_dir))

    assert result.exit_code == 0, result.output
    assert [engine.threshold for engine in blind_tesseract] == [50]


@pytest.mark.parametrize(
    'options, tesseract_workers, plugin_workers',
    [
        (['-w', '3'], 3, 3),
        (['-w', '3', '--tesseract-workers', '1'], 1, 3),
        (['--tesseract-workers', '1'], 1, None),
    ],
)
def test_the_tesseract_workers_override_the_workers_of_the_chain(
    options: list[str],
    tesseract_workers: int,
    plugin_workers: int | None,
    media_dir: typing.Any,
    blind_tesseract: list[TesseractEngine],
) -> None:
    result = rip('--engine', 'tesseract', '--engine', 'plugin', *options, str(media_dir))

    assert result.exit_code == 0, result.output
    assert [engine.workers for engine in blind_tesseract] == [tesseract_workers]
    assert [engine.workers for engine in PluginEngine.created] == [plugin_workers]


@pytest.mark.parametrize(
    'threshold, doubtful',
    [
        (None, True),  # the default threshold is 80
        (71, True),
        (70, False),
        (0, False),
    ],
)
def test_a_cue_with_a_word_below_the_threshold_is_doubtful(threshold: int | None, doubtful: bool) -> None:
    columns = ('level', 'page_num', 'block_num', 'par_num', 'line_num', 'word_num')
    rows = [(5, 1, 1, 1, 1, 1, 10, 10, 20, 20, 96, 'Hello'), (5, 1, 1, 1, 1, 2, 40, 10, 20, 20, 70, 'there')]
    keys = (*columns, 'left', 'top', 'width', 'height', 'conf', 'text')
    data = TsvData({key: [row[i] for row in rows] for i, key in enumerate(keys)}, confidence=65)
    item: typing.Any = types.SimpleNamespace(place=(0, 0, 100, 100), text=None, doubtful=False)

    text = TesseractEngine(threshold=threshold).accept(data, item, 65)

    assert text == 'Hello there'
    assert item.doubtful is doubtful


def test_a_config_file_sets_the_engine_chain_and_the_tesseract_section(
    media_dir: typing.Any, tmp_path: typing.Any, blind_tesseract: list[TesseractEngine]
) -> None:
    config = tmp_path / 'config.yml'
    config.write_text(
        'engine: [tesseract, plugin]\nmax_workers: 3\ntesseract:\n  threshold: 50\n  workers: 2\n  repository: fast\n',
        encoding='utf-8',
    )

    result = rip('--config', str(config), str(media_dir))

    # tesseract reads nothing here, so the plug-in reads every cue
    assert result.exit_code == 0, result.output
    assert [(e.threshold, e.workers, e.tessdata.repository) for e in blind_tesseract] == [(50, 2, 'fast')]
    assert [engine.workers for engine in PluginEngine.created] == [3]
    assert read_texts(media_dir) == ['Plugin 0', 'Plugin 1', 'Plugin 2']


def test_the_options_of_a_plugin_engine_are_in_the_help() -> None:
    result = rip('--help')

    assert result.exit_code == 0, result.output
    for option in (
        '--tuned-model',
        '--tuned-size',
        '--tuned-fast / --no-tuned-fast',
        '--tuned-workers',
        '--remote-url',
    ):
        assert option in result.output
    assert 'PGSRIP_TUNED_SIZE' in result.output


def test_the_options_of_a_plugin_engine_go_to_its_settings(media_dir: typing.Any) -> None:
    result = rip('--engine', 'tuned', '--tuned-model', 'small', '--no-tuned-fast', str(media_dir))

    assert result.exit_code == 0, result.output
    assert TunedEngine.settings == [{'model': 'small', 'size': 1, 'fast': False}]


def test_a_config_file_section_sets_the_options_of_a_plugin_engine(media_dir: typing.Any, tmp_path: typing.Any) -> None:
    config = tmp_path / 'config.yml'
    config.write_text('engine: [tuned]\ntuned:\n  model: small\n  size: 3\n  workers: 2\n', encoding='utf-8')

    result = rip('--config', str(config), str(media_dir))

    assert result.exit_code == 0, result.output
    assert TunedEngine.settings == [{'model': 'small', 'size': 3, 'fast': True}]
    assert [engine.workers for engine in PluginEngine.created] == [2]


@pytest.mark.parametrize('options, size', [([], 5), (['--tuned-size', '7'], 7)])
def test_the_command_line_wins_over_the_environment_variable_of_an_option(
    options: list[str], size: int, media_dir: typing.Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv('PGSRIP_TUNED_SIZE', '5')

    result = rip('--engine', 'tuned', *options, str(media_dir))

    assert result.exit_code == 0, result.output
    assert [settings['size'] for settings in TunedEngine.settings] == [size]


@pytest.mark.parametrize('options, workers', [([], None), (['-w', '3'], 3), (['-w', '3', '--tuned-workers', '2'], 2)])
def test_the_workers_of_a_plugin_engine_default_to_the_workers_of_the_chain(
    options: list[str], workers: int | None, media_dir: typing.Any
) -> None:
    result = rip('--engine', 'tuned', *options, str(media_dir))

    assert result.exit_code == 0, result.output
    assert [engine.workers for engine in PluginEngine.created] == [workers]


def test_a_required_option_is_needed_when_the_engine_is_used(media_dir: typing.Any) -> None:
    result = rip('--engine', 'remote', str(media_dir))

    assert result.exit_code == 2
    assert '--engine remote needs --remote-url' in result.output


@pytest.mark.parametrize('option', [['--tuned-model', 'small'], ['--tuned-workers', '2'], ['--no-tuned-fast']])
def test_the_options_of_a_plugin_engine_need_the_engine(option: list[str], media_dir: typing.Any) -> None:
    result = rip('--engine', 'plugin', *option, str(media_dir))

    assert result.exit_code == 2
    assert 'the --tuned-* options need --engine tuned' in result.output


def test_a_config_file_section_of_an_unused_engine_is_accepted(media_dir: typing.Any, tmp_path: typing.Any) -> None:
    config = tmp_path / 'config.yml'
    config.write_text('tuned:\n  model: small\n', encoding='utf-8')

    result = rip('--config', str(config), '--engine', 'plugin', str(media_dir))

    assert result.exit_code == 0, result.output
    assert TunedEngine.settings == []


def test_a_config_file_section_of_an_engine_that_is_not_installed_is_rejected(
    media_dir: typing.Any, tmp_path: typing.Any
) -> None:
    config = tmp_path / 'config.yml'
    config.write_text('nope:\n  model: small\n', encoding='utf-8')

    result = rip('--config', str(config), str(media_dir))

    assert result.exit_code == 2
    assert 'Unknown option' in result.output
    assert 'nope_model' in result.output


def test_a_plugin_that_cannot_be_loaded_does_not_stop_the_other_engines(
    media_dir: typing.Any, caplog: pytest.LogCaptureFixture
) -> None:
    result = rip('--engine', 'plugin', str(media_dir))

    assert result.exit_code == 0, result.output
    assert 'Cannot load the OCR engine broken' in caplog.text
