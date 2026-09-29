"""RapidOCR engine: the PaddleOCR text line models on ONNX Runtime. It needs no program on the system."""

from __future__ import annotations

import importlib.metadata
import logging
import os
import re
import tempfile
import typing
from pathlib import Path

import click
import cv2
import numpy as np
import numpy.typing as npt

from pgsrip.diagnostics import Check
from pgsrip.engines.base import OcrEngine, OcrEngineFactory, OcrError, Reading
from pgsrip.plugin import PluginOption
from pgsrip.utils import cache_dir, default_workers, is_writable, split_lines

if typing.TYPE_CHECKING:
    from babelfish import Language

    from pgsrip.formats.pgs import Item

logger = logging.getLogger(__name__)

#: the packages of the rapidocr extra
PACKAGES = ('rapidocr', 'onnxruntime')
INSTALL_URL = 'https://github.com/ratoaq2/pgsrip#install-pgsrip'
RAPIDOCR_HINT = f'Install pgsrip with RapidOCR: uv tool install "pgsrip[rapidocr]" (other ways: {INSTALL_URL})'
#: a cue with a character score below this value (0-100) is doubtful: the next engine of the chain reads it again.
DEFAULT_THRESHOLD = 90
MODELS = ('tiny', 'small', 'medium')
DEFAULT_MODEL = 'small'
#: white margin around each line. The model scales a line to 48 px high: a large margin makes the letters small.
DEFAULT_BORDER = 4
#: the lines of one model call
DEFAULT_BATCH = 6

#: the languages of the PP-OCRv6 model, as ISO 639-1 codes (rapidocr/utils/model_resolver.py)
V6_LANGUAGES = frozenset(
    'af az bs ca cs cy da de en es et eu fi fr ga gl hr hu id is it ku la lb lt lv mi ms mt nl no oc pl pt qu '
    'rm ro sk sl sq sv sw tl tr uz vi zh ja'.split()
)
#: ISO 639-1 code to the PP-OCRv5 model of its script, for the languages that PP-OCRv6 does not read
V5_LANGUAGES = {
    **dict.fromkeys('ru uk be bg mk sr kk ky mn tg tt'.split(), 'cyrillic'),
    **dict.fromkeys('ar fa ur ps ug sd'.split(), 'arabic'),
    **dict.fromkeys('hi mr ne sa'.split(), 'devanagari'),
    'el': 'el',
    'ko': 'korean',
    'th': 'th',
    'ta': 'ta',
    'te': 'te',
}


def model_of(language: Language, model: str) -> tuple[str, str, str] | None:
    """The (OCR version, language type, model type) of the model that reads this language, or None."""
    try:
        code = 'zh' if language.alpha3 == 'zho' else str(language.alpha2)
    except Exception:
        # a language with no ISO 639-1 code, e.g. und
        return None

    if code in V6_LANGUAGES:
        # the Japanese part is not in the tiny model
        return 'PP-OCRv6', code, 'small' if code == 'ja' and model == 'tiny' else model
    if code in V5_LANGUAGES:
        return 'PP-OCRv5', V5_LANGUAGES[code], 'mobile'

    return None


def ctc_decode(preds: npt.NDArray[np.float32], characters: list[str]) -> tuple[str, float]:
    """Greedy CTC decode of the model output for one line: the text, and the lowest character score.

    A line with no character gives the score 0. Spaces do not count for the score.
    """
    chars: list[tuple[str, float]] = []
    previous = -1
    for index, score in zip(preds.argmax(axis=1).tolist(), preds.max(axis=1).tolist(), strict=True):
        # index 0 is the CTC blank
        if index != previous and index != 0:
            chars.append((characters[index], score))
        previous = index

    text = re.sub(' +', ' ', ''.join(c for c, _ in chars)).strip()
    return text, min((score for c, score in chars if c != ' '), default=0.0)


def read_lines(recognizer: typing.Any, images: list[npt.NDArray[typing.Any]]) -> list[tuple[str, float]]:
    """The text and the lowest character score of each line image.

    The same batches as `TextRecognizer.__call__`: lines of similar width go together. The decode is our own,
    because RapidOCR gives only the mean score of a line, which hides one bad character.
    """
    from rapidocr.utils.model_resolver import normalize_lang
    from rapidocr.utils.utils import reorder_bidi_for_display

    characters = recognizer.postprocess_op.character
    _, height, width = recognizer.rec_image_shape[:3]
    ratios = [image.shape[1] / image.shape[0] for image in images]
    order = np.argsort(ratios)
    results: list[tuple[str, float]] = [('', 0.0)] * len(images)
    for start in range(0, len(images), recognizer.rec_batch_num):
        chunk = order[start : start + recognizer.rec_batch_num]
        max_ratio = max(width / height, *(ratios[i] for i in chunk))
        data = np.concatenate([recognizer.resize_norm_img(images[i], max_ratio)[np.newaxis, :] for i in chunk])
        preds = recognizer.session(data.astype(np.float32))
        for row, i in enumerate(chunk):
            results[i] = ctc_decode(preds[row], characters)

    if normalize_lang(recognizer.cfg.lang_type) in recognizer.RTL_LANGS:
        texts = reorder_bidi_for_display(tuple(text for text, _ in results))
        results = [(str(text), score) for text, (_, score) in zip(texts, results, strict=True)]

    return results


def installed_versions() -> list[str]:
    """The versions of the packages of the rapidocr extra. Raise PackageNotFoundError when one is missing."""
    return [f'{name} {importlib.metadata.version(name)}' for name in PACKAGES]


class RapidOcrEngine(OcrEngine, OcrEngineFactory):
    """Reads each text line of each cue. All the lines of a track go to the model in batches."""

    options: typing.ClassVar[tuple[PluginOption, ...]] = (
        PluginOption(
            'threshold',
            click.IntRange(0, 100),
            default=DEFAULT_THRESHOLD,
            help='A cue with a character below this RapidOCR score goes to the next --engine.',
        ),
        PluginOption(
            'model',
            click.Choice(MODELS),
            default=DEFAULT_MODEL,
            help='PP-OCRv6 model: tiny, small or medium. The PP-OCRv5 languages use the mobile model.',
        ),
        PluginOption('border', click.IntRange(0, 50), default=DEFAULT_BORDER, help='White border around each line.'),
        PluginOption('batch', click.IntRange(1, 256), default=DEFAULT_BATCH, help='Text lines in one model call.'),
        PluginOption(
            'workers', click.IntRange(1, 50), default=None, help='Number of ONNX Runtime threads. Default: -w.'
        ),
        PluginOption(
            'dir',
            click.Path(),
            default=None,
            envvar='PGSRIP_RAPIDOCR_DIR',
            help='Directory where the RapidOCR models are stored. Default: a user cache directory.',
        ),
        PluginOption(
            'download',
            flag=True,
            default=True,
            help='Download missing RapidOCR models. With --no-rapidocr-download, use only the models in the directory.',
        ),
    )

    @classmethod
    def from_settings(cls, settings: dict[str, typing.Any]) -> RapidOcrEngine:
        return cls(
            threshold=settings['threshold'],
            model=settings['model'],
            border=settings['border'],
            batch=settings['batch'],
            model_dir=settings['dir'],
            download=settings['download'],
            workers=settings['workers'],
        )

    @classmethod
    def check(cls, settings: dict[str, typing.Any]) -> list[Check]:
        """The rapidocr and onnxruntime versions, and the models, for `pgsrip doctor`."""
        try:
            versions = installed_versions()
        except importlib.metadata.PackageNotFoundError as e:
            # not a failure: tesseract can still rip
            return [Check('rapidocr', f'not installed: {e.name} is missing', hint=RAPIDOCR_HINT)]

        engine = cls.from_settings(settings)
        checks = [
            Check('rapidocr', ', '.join(versions)),
            Check('rapidocr download', 'enabled' if engine.download else 'disabled'),
        ]
        try:
            directory = engine.target_dir
        except OcrError as e:
            return [*checks, Check('rapidocr directory', str(e), ok=False, hint='Set --rapidocr-dir')]

        models = sorted(name for name in os.listdir(directory) if name.endswith('.onnx'))
        return [
            *checks,
            Check('rapidocr directory', directory),
            Check('rapidocr models', ', '.join(models) or 'none, pgsrip downloads the ones it needs'),
        ]

    def __init__(
        self,
        threshold: int = DEFAULT_THRESHOLD,
        model: str = DEFAULT_MODEL,
        border: int = DEFAULT_BORDER,
        batch: int = DEFAULT_BATCH,
        model_dir: str | None = None,
        download: bool = True,
        workers: int | None = None,
    ):
        self.threshold = threshold
        self.model = model
        self.border = border
        self.batch = batch
        #: the directory of the option, None for the default: see `target_dir`
        self.model_dir = model_dir
        self.download = download
        self.workers = workers or default_workers()
        #: the loaded recognizers, by model file
        self.recognizers_by_model: dict[Path, typing.Any] = {}
        #: the model files that could not be loaded
        self.failed_models: set[Path] = set()
        #: the recognizer of each language that `prepare` got ready
        self.recognizers_by_language: dict[Language, typing.Any] = {}

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self) -> str:
        return (
            f'threshold:{self.threshold}, '
            f'model:{self.model}, '
            f'border:{self.border}, '
            f'batch:{self.batch}, '
            f'model_dir:{self.model_dir}, '
            f'download:{self.download}, '
            f'workers:{self.workers}'
        )

    @property
    def target_dir(self) -> str:
        """The directory option, else the first writable cache directory."""
        if self.model_dir:
            return self.model_dir

        candidates = [
            cache_dir('rapidocr'),
            os.path.join(tempfile.gettempdir(), 'pgsrip', 'rapidocr'),
        ]
        for candidate in candidates:
            if is_writable(candidate):
                return candidate

        raise OcrError('No writable directory found to store the RapidOCR models')

    def config(self, version: str, lang: str, size: str) -> typing.Any:
        """The recognizer settings of a model, from the RapidOCR defaults."""
        import rapidocr
        from rapidocr.utils.parse_parameters import ParseParams
        from rapidocr.utils.typings import ModelType, OCRVersion, TaskType

        cfg = ParseParams.load(Path(rapidocr.__file__).parent / 'config.yaml')
        params = {
            'Rec.ocr_version': OCRVersion(version),
            'Rec.lang_type': ParseParams.LangType(TaskType.REC, lang),
            'Rec.model_type': ModelType(size),
            'Rec.rec_batch_num': self.batch,
            'EngineConfig.onnxruntime.intra_op_num_threads': self.workers,
        }
        ParseParams.update_batch(cfg, params)
        cfg.Rec.engine_cfg = cfg.EngineConfig[cfg.Rec.engine_type.value]
        cfg.Rec.model_root_dir = self.target_dir
        cfg.Rec.font_path = None
        return cfg.Rec

    def load(self, cfg: typing.Any, reporter: typing.Callable[[str], None] | None) -> typing.Any:
        """The recognizer of a model. Download the model first when it is not in the directory."""
        from rapidocr.ch_ppocr_rec import TextRecognizer
        from rapidocr.inference_engine.base import FileInfo, InferSession

        info = FileInfo(cfg.engine_type, cfg.ocr_version, cfg.task_type, cfg.lang_type, cfg.model_type)
        path = Path(cfg.model_root_dir) / Path(InferSession.get_model_url(info)['model_dir']).name
        if path in self.failed_models:
            raise OcrError(f'{path.name} could not be loaded')
        if path not in self.recognizers_by_model:
            if not path.is_file():
                if not self.download:
                    raise OcrError(f'{path.name} is not in {cfg.model_root_dir} and the download is disabled')
                if reporter:
                    reporter(f'Downloading RapidOCR model {path.name}...')
            try:
                self.recognizers_by_model[path] = TextRecognizer(cfg)
            except Exception:
                self.failed_models.add(path)
                raise

        return self.recognizers_by_model[path]

    def prepare(
        self, languages: typing.Iterable[Language], reporter: typing.Callable[[str], None] | None = None
    ) -> None:
        """Download and load the model of each language, before any ripping starts.

        A model that cannot be loaded does not stop the rip: `supports` is False for its languages.
        """
        try:
            import onnxruntime  # noqa: F401
            from rapidocr.utils.log import logger as rapidocr_logger
        except ImportError as e:
            if reporter:
                reporter(f'RapidOCR is not installed: {e}')
                reporter(RAPIDOCR_HINT)
            return

        # the RapidOCR logger writes to the console itself. Its import sets its level: set it after.
        rapidocr_logger.setLevel(logging.ERROR)
        for language in languages:
            model = model_of(language, self.model)
            if model is None or language in self.recognizers_by_language:
                continue

            try:
                self.recognizers_by_language[language] = self.load(self.config(*model), reporter)
            except Exception as e:
                logger.debug('Cannot load the RapidOCR model for %s', language, exc_info=True)
                if reporter:
                    reporter(f'Cannot load the RapidOCR model for {language}: <{type(e).__name__}> {e}')

    def supports(self, language: Language) -> bool:
        return language in self.recognizers_by_language

    def recognize(self, items: list[Item], language: Language, debug_dir: str | None) -> list[Reading]:
        border = self.border
        line_images = [
            [
                cv2.cvtColor(
                    cv2.copyMakeBorder(line, border, border, border, border, cv2.BORDER_CONSTANT, value=255),
                    cv2.COLOR_GRAY2BGR,
                )
                for line in split_lines(item.bitmap)
            ]
            for item in items
        ]
        images = [image for lines in line_images for image in lines]
        try:
            results = iter(read_lines(self.recognizers_by_language[language], images))
        except Exception as e:
            raise OcrError(f'RapidOCR cannot read {language}: <{type(e).__name__}> {e}') from e

        readings = []
        for lines_of_item in line_images:
            lines = [next(results) for _ in lines_of_item]
            text = '\n'.join(line for line, _ in lines if line)
            if not text:
                readings.append(Reading(None))
                continue

            # the threshold never removes text: a doubtful cue keeps it when no next engine reads it
            confidence = min(score for _, score in lines)
            readings.append(Reading(text, confidence, confidence * 100 < self.threshold))

        return readings
