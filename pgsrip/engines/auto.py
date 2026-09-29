"""The auto OCR engine: tesseract for each language that it can read, else RapidOCR. It is not a chain."""

from __future__ import annotations

import importlib.metadata
import logging
import typing

from pgsrip.diagnostics import Check
from pgsrip.engines.base import OcrEngine, OcrError, Reading
from pgsrip.engines.rapidocr import RAPIDOCR_HINT, RapidOcrEngine, installed_versions
from pgsrip.engines.tesseract import TESSERACT_HINT, TesseractEngine, check_languages

if typing.TYPE_CHECKING:
    from babelfish import Language

    from pgsrip.formats.pgs import Item

logger = logging.getLogger(__name__)


#: a reserved engine name, not a plug-in: tesseract for each language that it can read, else rapidocr
AUTO = 'auto'
#: the engines that auto uses, by name. The options of these engines are valid with auto.
AUTO_ENGINES = ('tesseract', 'rapidocr')


class AutoEngine(OcrEngine):
    """The default engine: one engine for each language, tesseract first."""

    def __init__(self, tesseract: TesseractEngine, rapidocr: RapidOcrEngine):
        self.tesseract = tesseract
        self.rapidocr = rapidocr

    @classmethod
    def from_engines(cls, tesseract: OcrEngine, rapidocr: OcrEngine) -> AutoEngine:
        """Auto with the engines that the CLI made from the options of AUTO_ENGINES."""
        if not isinstance(tesseract, TesseractEngine) or not isinstance(rapidocr, RapidOcrEngine):
            raise TypeError(f'auto needs a TesseractEngine and a RapidOcrEngine, not {tesseract!r} and {rapidocr!r}')

        return cls(tesseract, rapidocr)

    @classmethod
    def check(cls, settings: dict[str, typing.Any]) -> list[Check]:
        """The engine that auto uses when no language is known, for `pgsrip doctor`."""
        # the same test as Tessdata.installed_codes, without its warning
        if check_languages().ok:
            return [Check('auto', 'tesseract')]

        try:
            installed_versions()
        except importlib.metadata.PackageNotFoundError:
            return [
                Check(
                    'auto',
                    'no OCR engine: tesseract not found, rapidocr not installed',
                    ok=False,
                    hint=f'{TESSERACT_HINT}. Or: {RAPIDOCR_HINT}',
                )
            ]

        return [Check('auto', 'rapidocr (tesseract not found)')]

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
        if others and reporter and self.tesseract.tessdata.installed_codes is None:
            reporter(f'tesseract not found: rapidocr reads {read}' if read else 'tesseract not found')
            reporter(TESSERACT_HINT)
        elif read and reporter:
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

    def recognize(self, items: list[Item], language: Language, debug_dir: str | None) -> list[Reading]:
        engine = self.engine_for(language)
        if engine is None:
            raise OcrError(f'No OCR engine can read {language}')

        return engine.recognize(items, language, debug_dir)
