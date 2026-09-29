"""The chain of post-processors, and the post-processors of other packages (`pgsrip.postprocessors` entry points)."""

from __future__ import annotations

import importlib.metadata
import json
import typing

import pysrt
import pytest
from click.testing import CliRunner

from pgsrip.api import post_processors
from pgsrip.cli import pgsrip
from pgsrip.diagnostics import Check
from pgsrip.engines import ENGINE_ENTRY_POINTS
from pgsrip.engines.base import Reading
from pgsrip.engines.tesseract import TesseractEngine
from pgsrip.options import Options
from pgsrip.plugin import PluginOption
from pgsrip.postprocessors import POST_PROCESSOR_ENTRY_POINTS
from pgsrip.postprocessors.cleanit import CleanitPostProcessor

from .test_engines import PluginEngine, fake_tesseract, read_texts, rip

if typing.TYPE_CHECKING:
    from babelfish import Language

    from pgsrip.cue import Cue
    from pgsrip.formats.pgs import Item
    from pgsrip.sources.base import Track

__all__ = ['fake_tesseract']


class SpeakerEngine(PluginEngine):
    """An engine of another package that reads a speaker label: the default cleanit rules remove it."""

    def recognize(self, items: list[Item], language: Language, debug_dir: str | None) -> list[Reading]:
        return [Reading(f'MAN:  Hello {item.index}') for item in items]


class UpperPostProcessor:
    """A post-processor of another package: upper case, and a suffix."""

    options: typing.ClassVar[tuple[PluginOption, ...]] = (PluginOption('suffix', default=''),)
    #: the settings of each created post-processor
    settings: typing.ClassVar[list[dict[str, typing.Any]]] = []

    def __init__(self, suffix: str = ''):
        self.suffix = suffix

    @classmethod
    def from_settings(cls, settings: dict[str, typing.Any]) -> UpperPostProcessor:
        UpperPostProcessor.settings.append(settings)
        return cls(settings['suffix'])

    @classmethod
    def check(cls, settings: dict[str, typing.Any]) -> list[Check]:
        return [Check('upper suffix', settings['suffix'] or 'not set')]

    def process(self, cues: list[Cue], track: Track) -> list[Cue]:
        for cue in cues:
            if cue.text:
                cue.text = cue.text.upper() + self.suffix
        return cues


class RecordPostProcessor:
    """A post-processor of another package that keeps a copy of the cues it gets."""

    options: typing.ClassVar[tuple[PluginOption, ...]] = ()
    #: (text, engine, confidence, doubtful) of each cue it got
    seen: typing.ClassVar[list[tuple[str | None, str | None, float | None, bool]]] = []

    @classmethod
    def from_settings(cls, settings: dict[str, typing.Any]) -> RecordPostProcessor:
        return cls()

    def process(self, cues: list[Cue], track: Track) -> list[Cue]:
        RecordPostProcessor.seen.extend((cue.text, cue.engine, cue.confidence, cue.doubtful) for cue in cues)
        return cues


class DropPostProcessor(RecordPostProcessor):
    """A post-processor of another package that empties the text of the second cue."""

    def process(self, cues: list[Cue], track: Track) -> list[Cue]:
        cues[1].text = ''
        return cues


class FailingPostProcessor(RecordPostProcessor):
    """A post-processor of another package that fails."""

    def process(self, cues: list[Cue], track: Track) -> list[Cue]:
        raise RuntimeError('no network')


@pytest.fixture(autouse=True)
def plugins(monkeypatch: pytest.MonkeyPatch) -> None:
    PluginEngine.calls = []
    PluginEngine.created = []
    UpperPostProcessor.settings = []
    RecordPostProcessor.seen = []
    engines = ENGINE_ENTRY_POINTS
    post_processors = POST_PROCESSOR_ENTRY_POINTS
    entry_points = [
        importlib.metadata.EntryPoint('plugin', 'tests.test_engines:PluginEngine', engines),
        importlib.metadata.EntryPoint('blind', 'tests.test_engines:BlindEngine', engines),
        importlib.metadata.EntryPoint('speaker', f'{__name__}:SpeakerEngine', engines),
        importlib.metadata.EntryPoint('upper', f'{__name__}:UpperPostProcessor', post_processors),
        importlib.metadata.EntryPoint('record', f'{__name__}:RecordPostProcessor', post_processors),
        importlib.metadata.EntryPoint('drop', f'{__name__}:DropPostProcessor', post_processors),
        importlib.metadata.EntryPoint('failing', f'{__name__}:FailingPostProcessor', post_processors),
        importlib.metadata.EntryPoint('plugin', f'{__name__}:UpperPostProcessor', post_processors),
        importlib.metadata.EntryPoint('cleanit', f'{__name__}:UpperPostProcessor', post_processors),
    ]
    monkeypatch.setattr(
        'pgsrip.cli.plugins.importlib.metadata.entry_points',
        lambda group: [ep for ep in entry_points if ep.group == group],
    )


@pytest.fixture
def cleanit_config(tmp_path: typing.Any) -> str:
    """A cleanit rules file with a `shout` tag: Plugin becomes PLUGIN."""
    path = tmp_path / 'cleanit.yml'
    path.write_text(
        'rules:\n  shout[shout]:\n    tags: [shout]\n    patterns: [Plugin]\n    replacement: PLUGIN\n',
        encoding='utf-8',
    )
    return str(path)


def test_cleanit_is_the_default_post_processor(media_dir: typing.Any) -> None:
    result = rip('--engine', 'speaker', str(media_dir))

    assert result.exit_code == 0, result.output
    assert read_texts(media_dir) == ['Hello 0', 'Hello 1', 'Hello 2']


def test_no_post_process_keeps_the_text_of_the_engines(media_dir: typing.Any) -> None:
    result = rip('--engine', 'speaker', '--no-post-processor', str(media_dir))

    assert result.exit_code == 0, result.output
    assert read_texts(media_dir) == ['MAN:  Hello 0', 'MAN:  Hello 1', 'MAN:  Hello 2']


def test_the_post_processors_run_in_the_given_order(media_dir: typing.Any) -> None:
    result = rip('--engine', 'plugin', '--post-processor', 'record', '--post-processor', 'upper', str(media_dir))

    assert result.exit_code == 0, result.output
    assert [text for text, _, _, _ in RecordPostProcessor.seen] == ['Plugin 0', 'Plugin 1', 'Plugin 2']
    assert read_texts(media_dir) == ['PLUGIN 0', 'PLUGIN 1', 'PLUGIN 2']


def test_a_post_processor_gets_the_text_of_the_previous_post_processor(media_dir: typing.Any) -> None:
    result = rip('--engine', 'plugin', '--post-processor', 'upper', '--post-processor', 'record', str(media_dir))

    assert result.exit_code == 0, result.output
    assert [text for text, _, _, _ in RecordPostProcessor.seen] == ['PLUGIN 0', 'PLUGIN 1', 'PLUGIN 2']


def test_a_cue_gets_the_engine_that_read_it(media_dir: typing.Any, fake_tesseract: list[int]) -> None:
    fake_tesseract.append(1)

    result = rip('--engine', 'tesseract', '--engine', 'plugin', '--post-processor', 'record', str(media_dir))

    assert result.exit_code == 0, result.output
    assert RecordPostProcessor.seen == [
        ('Tesseract 0', 'TesseractEngine', None, False),
        ('Plugin 1', 'PluginEngine', None, False),
        ('Tesseract 2', 'TesseractEngine', None, False),
    ]


def test_the_post_processors_get_the_cues_that_no_engine_could_read(media_dir: typing.Any) -> None:
    result = rip('--engine', 'blind', '--post-processor', 'record', str(media_dir))

    assert result.exit_code == 0, result.output
    assert RecordPostProcessor.seen == [(None, None, None, False)] * 3


def test_a_cue_with_no_text_is_not_in_the_srt(media_dir: typing.Any) -> None:
    result = rip('--engine', 'plugin', '--post-processor', 'drop', str(media_dir))

    assert result.exit_code == 0, result.output
    subs = pysrt.open(str(media_dir / 'placeholder.en.srt'), encoding='utf-8')
    assert [(item.index, item.text) for item in subs] == [(1, 'Plugin 0'), (2, 'Plugin 2')]


def test_a_failing_post_processor_writes_no_srt(media_dir: typing.Any) -> None:
    result = rip('--engine', 'plugin', '--post-processor', 'failing', str(media_dir))

    assert result.exit_code == 1, result.output
    assert 'could not be ripped' in result.output
    assert '<RuntimeError> no network' in result.output
    assert not (media_dir / 'placeholder.en.srt').exists()


def test_the_options_of_a_post_processor_go_to_its_settings(media_dir: typing.Any) -> None:
    result = rip('--engine', 'plugin', '--post-processor', 'upper', '--upper-suffix', '!', str(media_dir))

    assert result.exit_code == 0, result.output
    assert UpperPostProcessor.settings == [{'suffix': '!'}]
    assert read_texts(media_dir) == ['PLUGIN 0!', 'PLUGIN 1!', 'PLUGIN 2!']


def test_a_config_file_sets_the_post_processor_chain_and_its_section(
    media_dir: typing.Any, tmp_path: typing.Any
) -> None:
    config = tmp_path / 'config.yml'
    config.write_text('engine: [plugin]\npost_processor: [upper]\nupper:\n  suffix: "?"\n', encoding='utf-8')

    result = rip('--config', str(config), str(media_dir))

    assert result.exit_code == 0, result.output
    assert read_texts(media_dir) == ['PLUGIN 0?', 'PLUGIN 1?', 'PLUGIN 2?']


@pytest.mark.parametrize('flag', ['-t', '--tag', '--cleanit-tag'])
def test_the_tag_options_select_the_cleanit_rules(flag: str, media_dir: typing.Any, cleanit_config: str) -> None:
    result = rip('--engine', 'plugin', '--cleanit-config', cleanit_config, flag, 'shout', str(media_dir))

    assert result.exit_code == 0, result.output
    assert read_texts(media_dir) == ['PLUGIN 0', 'PLUGIN 1', 'PLUGIN 2']


def test_a_config_file_section_sets_the_cleanit_options(
    media_dir: typing.Any, tmp_path: typing.Any, cleanit_config: str
) -> None:
    config = tmp_path / 'config.yml'
    config.write_text(
        f'engine: [plugin]\ncleanit:\n  config: {json.dumps(cleanit_config)}\n  tag: [shout]\n', encoding='utf-8'
    )

    result = rip('--config', str(config), str(media_dir))

    assert result.exit_code == 0, result.output
    assert read_texts(media_dir) == ['PLUGIN 0', 'PLUGIN 1', 'PLUGIN 2']


def test_a_cleanit_config_that_is_not_a_file_is_rejected(media_dir: typing.Any, tmp_path: typing.Any) -> None:
    result = rip('--engine', 'plugin', '--cleanit-config', str(tmp_path / 'missing.yml'), str(media_dir))

    assert result.exit_code == 2
    assert 'Invalid cleanit configuration' in result.output


def test_a_cleanit_tag_with_no_rule_is_rejected(media_dir: typing.Any) -> None:
    result = rip('--engine', 'plugin', '-t', 'nope', str(media_dir))

    assert result.exit_code == 2
    assert 'No cleanit rules defined for nope' in result.output


def test_the_cleanit_options_need_the_cleanit_post_processor(media_dir: typing.Any) -> None:
    result = rip('--engine', 'plugin', '--no-post-processor', '--cleanit-tag', 'ocr', str(media_dir))

    assert result.exit_code == 2
    assert 'the --cleanit-* options need --post-processor cleanit' in result.output


def test_post_processor_and_no_post_process_are_rejected_together(media_dir: typing.Any) -> None:
    result = rip('--engine', 'plugin', '--post-processor', 'upper', '--no-post-processor', str(media_dir))

    assert result.exit_code == 2
    assert 'use --post-processor or --no-post-processor, not both' in result.output


def test_an_unknown_post_processor_is_rejected(media_dir: typing.Any) -> None:
    result = rip('--engine', 'plugin', '--post-processor', 'nope', str(media_dir))

    assert result.exit_code == 2
    assert 'nope is not a post-processor. Choose from: cleanit, upper, record, drop, failing' in result.output


def test_a_post_processor_with_the_name_of_an_engine_is_ignored(
    media_dir: typing.Any, caplog: pytest.LogCaptureFixture
) -> None:
    result = rip('--engine', 'plugin', '--post-processor', 'plugin', str(media_dir))

    assert result.exit_code == 2
    assert 'The post-processor plugin is ignored: an OCR engine has the same name' in caplog.text


def test_keep_temp_files_writes_the_cues_as_json(media_dir: typing.Any, tmp_path: typing.Any) -> None:
    result = rip('--engine', 'plugin', '--post-processor', 'upper', '--keep-temp-files', str(media_dir))

    assert result.exit_code == 0, result.output
    ocr = json.loads(next((tmp_path / 'temp').rglob('ocr.json')).read_text(encoding='utf-8'))
    cues = json.loads(next((tmp_path / 'temp').rglob('cues.json')).read_text(encoding='utf-8'))
    assert list(ocr['seconds']) == ['PluginEngine']
    assert [cue['text'] for cue in ocr['cues']] == ['Plugin 0', 'Plugin 1', 'Plugin 2']
    assert [cue['text'] for cue in cues['cues']] == ['PLUGIN 0', 'PLUGIN 1', 'PLUGIN 2']
    assert set(cues['cues'][0]) == {'index', 'start', 'end', 'text', 'confidence', 'doubtful', 'engine'}


def test_the_default_options_have_the_cleanit_post_processor() -> None:
    assert [type(p) for p in post_processors(Options())] == [CleanitPostProcessor]
    assert post_processors(Options(post_processors=[])) == []


def test_doctor_prints_the_checks_of_every_post_processor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(TesseractEngine, 'check', classmethod(lambda cls, settings: []))

    result = CliRunner().invoke(pgsrip, ['doctor', '--upper-suffix', '!'])

    lines = result.output.splitlines()
    assert any(line.startswith('cleanit config') and line.endswith('default') for line in lines)
    assert any(line.startswith('upper suffix') and line.endswith('!') for line in lines)
