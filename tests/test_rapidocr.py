"""The RapidOCR engine: fakes for the decode and the cue results, and the real model on drawn text."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import shutil
import sys
import types
import typing

import cv2
import numpy as np
import pysrt
import pytest
from babelfish import Language
from click.testing import CliRunner

from pgsrip.cli import pgsrip
from pgsrip.diagnostics import Check
from pgsrip.engines.rapidocr import RAPIDOCR_HINT, RapidOcrEngine, ctc, model_of

from .fabricate import SAMPLE

needs_rapidocr = pytest.mark.skipif(
    importlib.util.find_spec('rapidocr') is None or importlib.util.find_spec('onnxruntime') is None,
    reason='rapidocr is not installed on this platform',
)


def item(bitmap: typing.Any = None) -> typing.Any:
    return types.SimpleNamespace(
        bitmap=np.full((10, 10), 255, np.uint8) if bitmap is None else bitmap,
        text=None,
        doubtful=False,
        confidence=None,
    )


@pytest.mark.parametrize(
    'language, model, expected',
    [
        pytest.param('en', 'small', ('PP-OCRv6', 'en', 'small'), id='v6'),
        pytest.param('ja', 'tiny', ('PP-OCRv6', 'ja', 'small'), id='japanese is not in the tiny model'),
        pytest.param('zh-TW', 'small', ('PP-OCRv6', 'zh', 'small'), id='chinese'),
        pytest.param('ru', 'small', ('PP-OCRv5', 'cyrillic', 'mobile'), id='v5 script model'),
        pytest.param('he', 'small', None, id='no model'),
        pytest.param('und', 'small', None, id='undefined language'),
    ],
)
def test_model_of_a_language(language: str, model: str, expected: tuple[str, str, str] | None) -> None:
    assert model_of(Language.fromietf(language), model) == expected


def test_ctc_gives_the_text_and_the_lowest_character_score() -> None:
    characters = ['blank', 'a', 'b', ' ']
    # a a (repeated: one character) blank a b space space b
    steps = [(1, 0.9), (1, 0.8), (0, 0.99), (1, 0.95), (2, 0.7), (3, 0.1), (3, 0.2), (2, 0.85)]
    preds = np.full((len(steps), len(characters)), 0.0, np.float32)
    for step, (index, score) in enumerate(steps):
        preds[step, index] = score

    text, score = ctc(preds, characters)

    assert text == 'aab b'
    # the space does not count
    assert score == pytest.approx(0.7)


def test_ctc_of_a_line_with_no_character_gives_the_score_0() -> None:
    assert ctc(np.array([[0.9, 0.1], [0.8, 0.2]], np.float32), ['blank', 'a']) == ('', 0.0)


def test_the_threshold_sets_doubtful_and_never_removes_text(monkeypatch: pytest.MonkeyPatch) -> None:
    lines = [('Sure', 0.95), ('Not sure', 0.5), ('', 0.0)]
    monkeypatch.setattr('pgsrip.engines.rapidocr.read_lines', lambda recognizer, images: lines[: len(images)])
    engine = RapidOcrEngine(threshold=90)
    engine.languages[Language('eng')] = object()
    items = [item(), item(), item()]

    engine.recognize(typing.cast(typing.Any, types.SimpleNamespace(language=Language('eng'))), items)

    assert [(i.text, i.confidence, i.doubtful) for i in items] == [
        ('Sure', 0.95, False),
        ('Not sure', 0.5, True),
        (None, None, False),
    ]


def test_supports_is_false_when_rapidocr_is_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, 'onnxruntime', None)
    engine = RapidOcrEngine()
    reported: list[str] = []

    engine.prepare([Language('eng')], reporter=reported.append)

    assert not engine.supports(Language('eng'))
    assert reported == ['RapidOCR is not installed: import of onnxruntime halted; None in sys.modules', RAPIDOCR_HINT]


@needs_rapidocr
def test_supports_is_false_when_the_download_is_off_and_there_is_no_model(tmp_path: typing.Any) -> None:
    engine = RapidOcrEngine(directory=str(tmp_path), download=False)
    reported: list[str] = []

    engine.prepare([Language('eng'), Language('heb')], reporter=reported.append)

    assert not engine.supports(Language('eng'))
    assert not engine.supports(Language('heb'))
    assert reported == [
        'Cannot load the RapidOCR model for en: <OcrError> PP-OCRv6_rec_small.onnx is not in '
        f'{tmp_path} and the download is disabled'
    ]


def test_the_check_is_not_a_failure_when_rapidocr_is_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    def version(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr('pgsrip.engines.rapidocr.importlib.metadata.version', version)

    assert RapidOcrEngine.check({}) == [Check('rapidocr', 'not installed: rapidocr is missing', hint=RAPIDOCR_HINT)]


@needs_rapidocr
def test_the_check_shows_the_models_in_the_directory(tmp_path: typing.Any) -> None:
    (tmp_path / 'PP-OCRv6_rec_small.onnx').write_bytes(b'model')
    settings = {'threshold': 90, 'model': 'small', 'border': 8, 'batch': 6, 'dir': str(tmp_path), 'download': False}

    checks = {check.name: check for check in RapidOcrEngine.check(settings)}

    assert checks['rapidocr download'].value == 'disabled'
    assert checks['rapidocr directory'].value == str(tmp_path)
    assert checks['rapidocr models'].value == 'PP-OCRv6_rec_small.onnx'
    assert all(check.ok for check in checks.values())


@pytest.fixture(scope='module')
def real_engine() -> RapidOcrEngine:
    """The engine with the real v6 small model. PGSRIP_RAPIDOCR_DIR sets the model directory, as for CI."""
    engine = RapidOcrEngine()
    engine.prepare([Language('eng')])
    assert engine.supports(Language('eng'))
    return engine


def draw(*lines: str) -> typing.Any:
    """A subtitle bitmap: black text on white, one text line under the other."""
    image = np.full((50 * len(lines) + 20, 600), 255, np.uint8)
    for n, line in enumerate(lines):
        cv2.putText(image, line, (10, 50 * n + 45), cv2.FONT_HERSHEY_SIMPLEX, 1.2, 0, 2, cv2.LINE_AA)
    return image


@needs_rapidocr
def test_the_real_model_reads_two_lines(real_engine: RapidOcrEngine) -> None:
    cue = item(draw('Hello world', 'See you soon'))

    real_engine.recognize(typing.cast(typing.Any, types.SimpleNamespace(language=Language('eng'))), [cue])

    assert cue.text == 'Hello world\nSee you soon'
    assert 0.9 < cue.confidence <= 1
    assert cue.doubtful is False


@needs_rapidocr
@pytest.mark.usefixtures('real_engine')
def test_the_last_engine_of_a_chain_writes_its_doubtful_cues(tmp_path: typing.Any) -> None:
    shutil.copy(SAMPLE, tmp_path)

    # with the threshold 100, every cue is doubtful
    result = CliRunner().invoke(pgsrip, ['rip', '--engine', 'rapidocr', '--rapidocr-threshold', '100', str(tmp_path)])

    assert result.exit_code == 0, result.output
    texts = [cue.text for cue in pysrt.open(str(tmp_path / 'placeholder.en.srt'), encoding='utf-8')]
    assert texts == ['Lorem ipsum dolor sit amet 0', 'Lorem ipsum dolor sit amet 2', 'Lorem ipsum dolor sit amet 4']
