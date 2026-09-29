"""The chain of OCR engines, and the OCR engines of other packages (`pgsrip.engines` entry points)."""

from __future__ import annotations

import dataclasses
import importlib.metadata
import shutil
import sys
import tempfile
import typing

import numpy as np
import pysrt
import pytest
from babelfish import Language
from click.testing import CliRunner

from pgsrip.api import engines
from pgsrip.cli import pgsrip
from pgsrip.diagnostics import Check
from pgsrip.engines import ENGINE_ENTRY_POINTS
from pgsrip.engines.auto import AutoEngine
from pgsrip.engines.base import OcrEngine, Reading
from pgsrip.engines.chain import read_cues
from pgsrip.engines.rapidocr import RAPIDOCR_HINT, RapidOcrEngine
from pgsrip.engines.tesseract import MAX_TESS_DIMENSION, TESSERACT_HINT, Composite, Gap, TesseractEngine
from pgsrip.engines.tsv import TsvResult
from pgsrip.formats.pgs import Box
from pgsrip.options import Options
from pgsrip.plugin import PluginOption

from .fabricate import SAMPLE

if typing.TYPE_CHECKING:
    from pgsrip.formats.pgs import Item


class PluginEngine(OcrEngine):
    """An engine of another package: it reads every cue as 'Plugin <index>'."""

    #: the item indexes of each recognize call
    calls: typing.ClassVar[list[list[int]]] = []
    #: the engines that the plug-in factory created
    created: typing.ClassVar[list[PluginEngine]] = []

    options: typing.ClassVar[tuple[PluginOption, ...]] = (PluginOption('workers', int, default=None),)

    def __init__(self, workers: int | None = None):
        self.workers = workers
        PluginEngine.created.append(self)

    @classmethod
    def from_settings(cls, settings: dict[str, typing.Any]) -> PluginEngine:
        return cls(workers=settings.get('workers'))

    @classmethod
    def check(cls, settings: dict[str, typing.Any]) -> list[Check]:
        return []

    def prepare(
        self, languages: typing.Iterable[Language], reporter: typing.Callable[[str], None] | None = None
    ) -> None:
        pass

    def supports(self, language: Language) -> bool:
        return True

    def recognize(self, items: list[Item], language: Language, debug_dir: str | None) -> list[Reading]:
        PluginEngine.calls.append([item.index for item in items])
        return [Reading(f'Plugin {item.index}') for item in items]


class BlindEngine(PluginEngine):
    """An engine of another package that reads nothing."""

    def recognize(self, items: list[Item], language: Language, debug_dir: str | None) -> list[Reading]:
        PluginEngine.calls.append([item.index for item in items])
        return [Reading(None) for _ in items]


class EnglishEngine(PluginEngine):
    """An engine of another package that reads only English, as 'English <index>'."""

    def supports(self, language: Language) -> bool:
        return bool(language == Language('eng'))

    def recognize(self, items: list[Item], language: Language, debug_dir: str | None) -> list[Reading]:
        return [Reading(f'English {item.index}') for item in items]


class RoutingEngine(BlindEngine):
    """An engine that gives the plug-in engine for each language, and reads nothing itself."""

    def engine_for(self, language: Language) -> PluginEngine:
        return PluginEngine()


class TunedEngine(PluginEngine):
    """An engine of another package with its own options."""

    options = (
        PluginOption('model', help='Model of the tuned engine.'),
        PluginOption('size', int, default=1, envvar='PGSRIP_TUNED_SIZE'),
        PluginOption('fast', flag=True, default=True),
        PluginOption('workers', int, default=None),
    )
    #: the settings of each created engine
    settings: typing.ClassVar[list[dict[str, typing.Any]]] = []

    @classmethod
    def from_settings(cls, settings: dict[str, typing.Any]) -> PluginEngine:
        TunedEngine.settings.append(settings)
        return cls(workers=settings['workers'])

    @classmethod
    def check(cls, settings: dict[str, typing.Any]) -> list[Check]:
        return [Check('tuned model', settings['model'] or 'not set')]


class RemoteEngine(PluginEngine):
    """An engine of another package that cannot work without its url, and has a broken check."""

    options = (PluginOption('url', required=True),)

    @classmethod
    def check(cls, settings: dict[str, typing.Any]) -> list[Check]:
        raise RuntimeError('no network')


@pytest.fixture
def media_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: typing.Any) -> typing.Any:
    """A directory with the placeholder sample (3 cues), and a temporary directory of its own."""
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
        importlib.metadata.EntryPoint('english', f'{__name__}:EnglishEngine', ENGINE_ENTRY_POINTS),
        importlib.metadata.EntryPoint('tuned', f'{__name__}:TunedEngine', ENGINE_ENTRY_POINTS),
        importlib.metadata.EntryPoint('remote', f'{__name__}:RemoteEngine', ENGINE_ENTRY_POINTS),
        importlib.metadata.EntryPoint('broken', f'{__name__}:MissingEngine', ENGINE_ENTRY_POINTS),
        importlib.metadata.EntryPoint('tesseract', f'{__name__}:PluginEngine', ENGINE_ENTRY_POINTS),
    ]
    monkeypatch.setattr(
        'pgsrip.cli.plugins.importlib.metadata.entry_points',
        lambda group: [ep for ep in entry_points if ep.group == group],
    )


@pytest.fixture
def fake_tesseract(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Tesseract reads every cue as 'Tesseract <index>'. Add an index to the list to make that cue doubtful."""
    doubtful: list[int] = []

    def recognize(
        engine: TesseractEngine, items: list[Item], language: Language, debug_dir: str | None
    ) -> list[Reading]:
        return [Reading(f'Tesseract {item.index}', doubtful=item.index in doubtful) for item in items]

    monkeypatch.setattr(TesseractEngine, 'prepare', lambda *args, **kwargs: None)
    monkeypatch.setattr(TesseractEngine, 'supports', lambda *args: True)
    monkeypatch.setattr(TesseractEngine, 'recognize', recognize)
    return doubtful


@pytest.fixture
def blind_tesseract(monkeypatch: pytest.MonkeyPatch) -> list[TesseractEngine]:
    """Tesseract reads nothing. The list gets each tesseract engine that recognize was called on."""
    engines: list[TesseractEngine] = []
    monkeypatch.setattr(TesseractEngine, 'prepare', lambda *args, **kwargs: None)
    monkeypatch.setattr(TesseractEngine, 'supports', lambda *args: True)

    def recognize(engine: TesseractEngine, items: list[Item], *args: typing.Any) -> list[Reading]:
        engines.append(engine)
        return [Reading(None) for _ in items]

    monkeypatch.setattr(TesseractEngine, 'recognize', recognize)
    return engines


def rip(*args: str) -> typing.Any:
    return CliRunner().invoke(pgsrip, ['rip', *args])


def read_texts(media_dir: typing.Any, name: str = 'placeholder.en.srt') -> list[str]:
    return [item.text for item in pysrt.open(str(media_dir / name), encoding='utf-8')]


@pytest.fixture
def hebrew_track(media_dir: typing.Any) -> typing.Any:
    """A second track of the placeholder sample, in Hebrew."""
    shutil.copy(SAMPLE, media_dir / 'placeholder.he.sup')
    return media_dir / 'placeholder.he.srt'


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


def test_the_chain_skips_an_engine_that_cannot_read_the_language(
    media_dir: typing.Any, hebrew_track: typing.Any
) -> None:
    result = rip('--engine', 'english', '--engine', 'plugin', str(media_dir))

    # the plug-in engine has no supports method: it reads all languages
    assert result.exit_code == 0, result.output
    assert 'EnglishEngine cannot read he' in result.output
    assert read_texts(media_dir) == ['English 0', 'English 1', 'English 2']
    assert read_texts(media_dir, hebrew_track.name) == ['Plugin 0', 'Plugin 1', 'Plugin 2']


def test_a_track_that_no_engine_can_read_fails_and_the_other_tracks_rip(
    media_dir: typing.Any, hebrew_track: typing.Any
) -> None:
    result = rip('--engine', 'english', str(media_dir))

    # a failed track is a failed rip, also when the other tracks rip
    assert result.exit_code == 1
    assert 'No OCR engine of the chain can read he' in result.output
    assert read_texts(media_dir) == ['English 0', 'English 1', 'English 2']
    assert not hebrew_track.exists()


def test_the_last_engine_keeps_its_doubtful_cues_when_the_next_engine_cannot_read_the_language(
    media_dir: typing.Any, hebrew_track: typing.Any, fake_tesseract: list[int]
) -> None:
    fake_tesseract.extend([0, 1, 2])

    result = rip('--engine', 'tesseract', '--engine', 'english', str(media_dir))

    assert result.exit_code == 0, result.output
    assert read_texts(media_dir) == ['English 0', 'English 1', 'English 2']
    assert read_texts(media_dir, hebrew_track.name) == ['Tesseract 0', 'Tesseract 1', 'Tesseract 2']


@dataclasses.dataclass(eq=False)
class FakeItem:
    """A subtitle item with ink, for the ripper."""

    index: int = 0
    start: None = None
    end: None = None
    height: int = 1
    text: str | None = None
    doubtful: bool = False
    confidence: float | None = None


def test_the_chain_uses_the_engine_that_engine_for_gives() -> None:
    items: typing.Any = [FakeItem()]

    cues, _ = read_cues(items, Language('eng'), [RoutingEngine()])

    assert [(cue.text, cue.engine) for cue in cues] == [('Plugin 0', 'PluginEngine')]
    assert PluginEngine.calls == [[0]]


@pytest.fixture
def missing_tesseract(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tesseract program is not found."""

    def fail() -> list[str]:
        raise OSError('tesseract not found')

    monkeypatch.setattr('pgsrip.engines.tessdata.tess.get_languages', fail)


@pytest.fixture
def fake_rapidocr(monkeypatch: pytest.MonkeyPatch) -> list[Language]:
    """RapidOCR reads every cue as 'RapidOCR <index>', doubtful. The list gets the languages that it prepared."""
    prepared: list[Language] = []

    def recognize(
        engine: RapidOcrEngine, items: list[Item], language: Language, debug_dir: str | None
    ) -> list[Reading]:
        return [Reading(f'RapidOCR {item.index}', doubtful=True) for item in items]

    monkeypatch.setattr(RapidOcrEngine, 'prepare', lambda engine, languages, reporter=None: prepared.extend(languages))
    monkeypatch.setattr(RapidOcrEngine, 'supports', lambda engine, language: language in prepared)
    monkeypatch.setattr(RapidOcrEngine, 'recognize', recognize)
    return prepared


@pytest.mark.usefixtures('fake_tesseract')
def test_auto_uses_tesseract_else_rapidocr_for_each_language(
    media_dir: typing.Any, hebrew_track: typing.Any, fake_rapidocr: list[Language], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr('pgsrip.engines.tessdata.tess.get_languages', lambda: ['eng'])
    monkeypatch.setattr(TesseractEngine, 'supports', lambda engine, language: language == Language('eng'))

    result = rip(str(media_dir))

    # no chain: the doubtful rapidocr cues keep their text
    assert result.exit_code == 0, result.output
    assert 'no tesseract data for he: rapidocr reads he' in result.output
    assert fake_rapidocr == [Language('heb')]
    assert read_texts(media_dir) == ['Tesseract 0', 'Tesseract 1', 'Tesseract 2']
    assert read_texts(media_dir, hebrew_track.name) == ['RapidOCR 0', 'RapidOCR 1', 'RapidOCR 2']


@pytest.mark.usefixtures('missing_tesseract', 'fake_rapidocr')
def test_auto_uses_rapidocr_when_tesseract_is_not_found(media_dir: typing.Any) -> None:
    result = rip(str(media_dir))

    assert result.exit_code == 0, result.output
    assert f'tesseract not found: rapidocr reads en\n{TESSERACT_HINT}' in result.output
    assert read_texts(media_dir) == ['RapidOCR 0', 'RapidOCR 1', 'RapidOCR 2']


@pytest.mark.usefixtures('missing_tesseract')
def test_auto_tells_how_to_install_an_engine_when_there_is_none(
    media_dir: typing.Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # pgsrip without the rapidocr extra
    monkeypatch.setitem(sys.modules, 'onnxruntime', None)

    result = rip(str(media_dir))

    assert result.exit_code == 1
    assert f'tesseract not found\n{TESSERACT_HINT}' in result.output
    assert RAPIDOCR_HINT in result.output
    assert 'AutoEngine cannot read en' in result.output


@pytest.mark.usefixtures('fake_tesseract', 'fake_rapidocr')
def test_auto_fails_a_track_that_no_engine_can_read(
    media_dir: typing.Any, hebrew_track: typing.Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(TesseractEngine, 'supports', lambda engine, language: language == Language('eng'))
    monkeypatch.setattr(RapidOcrEngine, 'supports', lambda engine, language: False)

    result = rip(str(media_dir))

    assert 'AutoEngine cannot read he' in result.output
    assert 'No OCR engine of the chain can read he' in result.output
    assert read_texts(media_dir) == ['Tesseract 0', 'Tesseract 1', 'Tesseract 2']
    assert not hebrew_track.exists()


@pytest.mark.usefixtures('fake_tesseract', 'fake_rapidocr')
def test_the_cues_of_auto_have_the_name_of_the_engine_that_read_them(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(TesseractEngine, 'supports', lambda engine, language: False)
    engine = AutoEngine(TesseractEngine(), RapidOcrEngine())
    engine.prepare([Language('heb')])
    items: typing.Any = [FakeItem()]

    cues, _ = read_cues(items, Language('heb'), [engine])

    assert [(cue.text, cue.engine) for cue in cues] == [('RapidOCR 0', 'RapidOcrEngine')]


def test_the_default_engine_of_the_options_is_auto() -> None:
    assert [type(engine) for engine in engines(Options())] == [AutoEngine]


def test_auto_is_valid_only_alone(media_dir: typing.Any) -> None:
    result = rip('--engine', 'auto', '--engine', 'plugin', str(media_dir))

    assert result.exit_code == 2
    assert 'use --engine auto alone' in result.output


@pytest.mark.usefixtures('missing_tesseract')
def test_the_rapidocr_options_are_valid_with_auto(media_dir: typing.Any, monkeypatch: pytest.MonkeyPatch) -> None:
    engines: list[RapidOcrEngine] = []
    monkeypatch.setattr(RapidOcrEngine, 'prepare', lambda engine, languages, reporter=None: engines.append(engine))

    result = rip('--rapidocr-threshold', '50', '--rapidocr-workers', '2', str(media_dir))

    assert 'the --rapidocr-* options need' not in result.output
    assert [(engine.threshold, engine.workers) for engine in engines] == [(50, 2)]


def test_an_unknown_engine_is_rejected(media_dir: typing.Any) -> None:
    result = rip('--engine', 'nope', str(media_dir))

    assert result.exit_code == 2
    assert (
        'nope is not an OCR engine. Choose from: auto, tesseract, rapidocr, plugin, blind, english, tuned, remote'
        in result.output
    )


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


def test_the_tesseract_confidence_and_width_options_set_the_first_pass(
    media_dir: typing.Any, blind_tesseract: list[TesseractEngine]
) -> None:
    result = rip('--tesseract-confidence', '50', '--tesseract-width', '20000', str(media_dir))

    assert result.exit_code == 0, result.output
    assert [(engine.confidence, engine.width) for engine in blind_tesseract] == [(50, 20000)]


@pytest.mark.usefixtures('blind_tesseract')
def test_the_tesseract_width_has_a_range(media_dir: typing.Any) -> None:
    result = rip('--tesseract-width', '40000', str(media_dir))

    assert result.exit_code == 2
    assert '10240<=x<=31744' in result.output


def test_the_tesseract_environment_variables_set_the_options(
    media_dir: typing.Any, blind_tesseract: list[TesseractEngine], monkeypatch: pytest.MonkeyPatch, tmp_path: typing.Any
) -> None:
    monkeypatch.setenv('PGSRIP_TESSDATA_DIR', str(tmp_path / 'tessdata'))
    monkeypatch.setenv('PGSRIP_TESSDATA_REPO', 'fast')

    result = rip('--engine', 'tesseract', str(media_dir))

    assert result.exit_code == 0, result.output
    assert [(engine.tessdata.data_dir, engine.tessdata.repository) for engine in blind_tesseract] == [
        (str(tmp_path / 'tessdata'), 'fast')
    ]


def test_the_engines_do_not_read_the_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: typing.Any) -> None:
    monkeypatch.setenv('PGSRIP_TESSDATA_DIR', str(tmp_path))
    monkeypatch.setenv('PGSRIP_RAPIDOCR_DIR', str(tmp_path))

    assert TesseractEngine().tessdata.data_dir is None
    assert RapidOcrEngine().model_dir is None


def test_the_help_shows_the_defaults_and_the_environment_variables() -> None:
    result = CliRunner().invoke(pgsrip, ['rip', '--help'])

    assert result.exit_code == 0, result.output
    for name in ('PGSRIP_TESSDATA_DIR', 'PGSRIP_TESSDATA_REPO', 'PGSRIP_RAPIDOCR_DIR', 'default: 80'):
        assert name in result.output


def test_the_tesseract_defaults() -> None:
    engine = TesseractEngine()

    assert (engine.confidence, engine.width, engine.threshold) == (65, 31744, 80)


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
    data = TsvResult({key: [row[i] for row in rows] for i, key in enumerate(keys)}, confidence=65)
    reading = TesseractEngine(**({} if threshold is None else {'threshold': threshold})).read_item(
        data, Box(0, 0, 100, 100), 65
    )

    # the lowest word confidence, from 0 to 1
    assert reading == Reading('Hello there', 0.7, doubtful)


def test_a_config_file_sets_the_engine_chain_and_the_tesseract_section(
    media_dir: typing.Any, tmp_path: typing.Any, blind_tesseract: list[TesseractEngine]
) -> None:
    config = tmp_path / 'config.yml'
    config.write_text(
        'engine: [tesseract, plugin]\nworkers: 3\ntesseract:\n  threshold: 50\n  workers: 2\n  repository: fast\n',
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
    assert TunedEngine.settings == [{'model': 'small', 'size': 1, 'fast': False, 'workers': None}]


def test_a_config_file_section_sets_the_options_of_a_plugin_engine(media_dir: typing.Any, tmp_path: typing.Any) -> None:
    config = tmp_path / 'config.yml'
    config.write_text('engine: [tuned]\ntuned:\n  model: small\n  size: 3\n  workers: 2\n', encoding='utf-8')

    result = rip('--config', str(config), str(media_dir))

    assert result.exit_code == 0, result.output
    assert TunedEngine.settings == [{'model': 'small', 'size': 3, 'fast': True, 'workers': 2}]
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


@pytest.fixture
def doctor(monkeypatch: pytest.MonkeyPatch) -> typing.Callable[..., typing.Any]:
    """Run `pgsrip doctor`, without the checks of the real tesseract."""
    monkeypatch.setattr(TesseractEngine, 'check', classmethod(lambda cls, settings: [Check('tesseract', 'fake')]))
    return lambda *args: CliRunner().invoke(pgsrip, ['doctor', *args])


def test_doctor_has_the_options_of_every_engine(doctor: typing.Callable[..., typing.Any]) -> None:
    result = doctor('--help')

    assert result.exit_code == 0, result.output
    for option in ('--config', '--tesseract-dir', '--tuned-model', '--remote-url'):
        assert option in result.output


def test_doctor_prints_the_checks_of_every_engine(doctor: typing.Callable[..., typing.Any]) -> None:
    result = doctor('--tuned-model', 'small')

    lines = result.output.splitlines()
    assert any(line.startswith('tesseract ') and line.endswith('fake') for line in lines)
    assert any(line.startswith('tuned model') and line.endswith('small') for line in lines)
    # a broken check does not hide the other checks
    assert any(line.startswith('remote ') and 'check failed: <RuntimeError> no network' in line for line in lines)


@pytest.mark.parametrize(
    'tesseract, rapidocr, expected',
    [
        (True, True, 'tesseract'),
        (False, True, 'rapidocr (tesseract not found)'),
        (False, False, 'no OCR engine: tesseract not found, rapidocr not installed'),
    ],
)
def test_doctor_shows_the_engine_of_auto(
    tesseract: bool,
    rapidocr: bool,
    expected: str,
    doctor: typing.Callable[..., typing.Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def languages() -> list[str]:
        if not tesseract:
            raise OSError('tesseract not found')
        return ['eng']

    real_version = importlib.metadata.version

    def version(name: str) -> str:
        if name not in ('rapidocr', 'onnxruntime'):
            return real_version(name)
        if not rapidocr:
            raise importlib.metadata.PackageNotFoundError(name)
        return '1.0'

    monkeypatch.setattr('pgsrip.engines.tessdata.tess.get_languages', languages)
    monkeypatch.setattr('pgsrip.engines.auto.importlib.metadata.version', version)
    monkeypatch.setattr(
        TesseractEngine,
        'check',
        classmethod(lambda cls, settings: [Check('tesseract', 'fake' if tesseract else 'not found', ok=tesseract)]),
    )

    result = doctor()

    assert any(line.startswith('auto ') and line.endswith(expected) for line in result.output.splitlines())
    # the failures: when pgsrip can rip, a missing tesseract is not one
    assert (f'auto: {expected}' in result.output) is not rapidocr
    assert ('tesseract: not found' in result.output) is not rapidocr


def test_doctor_reads_the_engine_sections_of_a_config_file(
    doctor: typing.Callable[..., typing.Any], tmp_path: typing.Any
) -> None:
    config = tmp_path / 'config.yml'
    config.write_text('tuned:\n  model: large\n', encoding='utf-8')

    result = doctor('--config', str(config))

    assert any(line.startswith('tuned model') and line.endswith('large') for line in result.output.splitlines())


def test_the_debug_log_has_the_checks_of_the_selected_engines(media_dir: typing.Any, tmp_path: typing.Any) -> None:
    log_file = tmp_path / 'pgsrip.log'

    result = rip('--engine', 'tuned', '--tuned-model', 'small', '--log-file', str(log_file), str(media_dir))

    assert result.exit_code == 0, result.output
    log = log_file.read_text(encoding='utf-8')
    assert 'tuned model' in log
    assert 'check failed' not in log


def test_doctor_accepts_the_rip_options_of_a_config_file(
    doctor: typing.Callable[..., typing.Any], tmp_path: typing.Any
) -> None:
    config = tmp_path / 'config.yml'
    config.write_text('language: [en]\nworkers: 2\ntuned:\n  model: large\n', encoding='utf-8')

    result = doctor('--config', str(config))

    assert 'Unknown option' not in result.output
    assert any(line.startswith('tuned model') and line.endswith('large') for line in result.output.splitlines())


@dataclasses.dataclass(eq=False)
class WideItem:
    """An item with a box and a bitmap, for the composites of tesseract."""

    width: int
    height: int = 10

    @property
    def box(self) -> Box:
        return Box(0, 0, self.height, self.width)

    @property
    def bitmap(self) -> typing.Any:
        return np.zeros((self.height, self.width), dtype=np.uint8)


def test_an_item_wider_than_the_maximum_width_gets_a_composite_of_its_own() -> None:
    items: typing.Any = [WideItem(width=500)]

    composites = Composite.from_items(items, Gap(10, 10), max_width=100, max_height=MAX_TESS_DIMENSION)

    assert [[item for item, _ in composite.placed] for composite in composites] == [items]


def test_tesseract_reads_nothing_when_no_word_is_in_the_box() -> None:
    data = TsvResult({}, confidence=65)

    assert TesseractEngine().read_item(data, Box(0, 0, 100, 100), 65) is None


def test_the_next_engine_reads_the_cues_where_tesseract_finds_no_word(
    media_dir: typing.Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr('pgsrip.engines.tessdata.tess.get_languages', lambda: ['eng'])
    monkeypatch.setattr('pgsrip.engines.tesseract.tess.image_to_data', lambda image, **config: {})

    result = rip('--engine', 'tesseract', '--engine', 'plugin', str(media_dir))

    assert result.exit_code == 0, result.output
    assert read_texts(media_dir) == ['Plugin 0', 'Plugin 1', 'Plugin 2']
