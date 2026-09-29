from pgsrip.engines.base import OcrEngineFactory
from pgsrip.engines.openai import OpenAiEngine
from pgsrip.engines.rapidocr import RapidOcrEngine
from pgsrip.engines.tesseract import TesseractEngine

#: the built-in OCR engines, by name. `auto` is not an engine of the list: see `pgsrip.engines.auto`.
ENGINES: dict[str, type[OcrEngineFactory]] = {
    'tesseract': TesseractEngine,
    'rapidocr': RapidOcrEngine,
    'openai': OpenAiEngine,
}
#: other packages add an OCR engine with an entry point in this group. See docs/usage.md.
ENGINE_ENTRY_POINTS = 'pgsrip.engines'
