"""The auto OCR engine: tesseract for each language that it can read, else RapidOCR. It is not a chain."""

from __future__ import annotations

import importlib.metadata
import logging
import typing

from pgsrip.diagnostics import Check
from pgsrip.rapidocr import RapidOcrEngine
from pgsrip.ripper import OcrEngine, OcrError
from pgsrip.tesseract import TESSERACT_HINT, TesseractEngine, check_languages

if typing.TYPE_CHECKING:
    from babelfish import Language

    from pgsrip.media import Pgs, PgsSubtitleItem

logger = logging.getLogger(__name__)


def check_auto() -> Check:
    """The engine that auto uses when no language is known, for `pgsrip doctor`."""
    # the same test as Tessdata.installed_codes, without its warning
    if check_languages().ok:
        return Check('auto', 'tesseract')

    try:
        for name in ('rapidocr', 'onnxruntime'):
            importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return Check(
            'auto', 'no OCR engine: tesseract not found, rapidocr not installed', ok=False, hint=TESSERACT_HINT
        )

    return Check('auto', 'rapidocr (tesseract not found)')


class AutoEngine(OcrEngine):
    """The default engine: one engine for each language, tesseract first."""

    def __init__(self, tesseract: TesseractEngine | None = None, rapidocr: RapidOcrEngine | None = None):
        self.tesseract = tesseract or TesseractEngine()
        self.rapidocr = rapidocr or RapidOcrEngine()

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self.tesseract!r}, {self.rapidocr!r}]>'

    def prepare(
        self, languages: typing.Iterable[Language], reporter: typing.Callable[[str], None] | None = None
    ) -> None:
        """Get tesseract ready, then RapidOCR only for the languages that tesseract cannot read."""
        languages = list(languages)
        self.tesseract.prepare(languages, reporter)
        others = [language for language in languages if not self.tesseract.supports(language)]
        if others:
            self.rapidocr.prepare(others, reporter)

        read = ', '.join(str(language) for language in others if self.rapidocr.supports(language))
        if read and reporter:
            if self.tesseract.tessdata.installed_codes is None:
                reporter(f'tesseract not found: rapidocr reads {read}')
                reporter(TESSERACT_HINT)
            else:
                reporter(f'no tesseract data for {read}: rapidocr reads {read}')

        for language in languages:
            engine = self.engine_for(language)
            logger.debug('%s: %s', language, type(engine).__name__ if engine else 'no engine')

    def supports(self, language: Language) -> bool:
        return self.engine_for(language) is not None

    def engine_for(self, language: Language) -> OcrEngine | None:
        if self.tesseract.supports(language):
            return self.tesseract
        if self.rapidocr.supports(language):
            return self.rapidocr

        return None

    def recognize(self, pgs: Pgs, items: list[PgsSubtitleItem]) -> None:
        engine = self.engine_for(pgs.language)
        if engine is None:
            raise OcrError(f'No OCR engine can read {pgs.language}')

        engine.recognize(pgs, items)
