from __future__ import annotations

import logging
import os
import shlex
import shutil
import sys
import tempfile
import typing
import urllib.error
import urllib.request
from contextlib import contextmanager

import pytesseract as tess
from babelfish import Language

from pgsrip.engines.base import OcrError
from pgsrip.utils import cache_dir, is_writable

logger = logging.getLogger(__name__)

TRAINED_DATA_EXTENSION = '.traineddata'
DEFAULT_LANGUAGE_CODE = 'eng'

DEFAULT_REPOSITORY = 'best'
REPOSITORIES = {
    'best': 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main',
    'fast': 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main',
    'standard': 'https://raw.githubusercontent.com/tesseract-ocr/tessdata/main',
}
DOWNLOAD_TIMEOUT = 30
USER_AGENT = 'pgsrip'

#: tesseract does not name every model after its alpha3 code: some models are for one script
SCRIPT_CODES = {
    ('aze', 'Cyrl'): 'aze_cyrl',
    ('srp', 'Latn'): 'srp_latn',
    ('uzb', 'Cyrl'): 'uzb_cyrl',
    ('zho', 'Hans'): 'chi_sim',
    ('zho', 'Hant'): 'chi_tra',
}
TRADITIONAL_CHINESE_COUNTRIES = frozenset({'HK', 'MO', 'TW'})


class TessdataError(OcrError):
    """Raised when the tesseract data required to rip a subtitle cannot be made available."""


def tesseract_code(language: Language) -> str | None:
    """Return the tesseract model name for a language, or None when the language is unknown."""
    if not language:
        return None

    alpha3 = str(language.alpha3)
    script = str(language.script) if language.script else None
    country = str(language.country) if language.country else None
    if alpha3 == 'zho' and script is None:
        script = 'Hant' if country in TRADITIONAL_CHINESE_COUNTRIES else 'Hans'

    return SCRIPT_CODES.get((alpha3, script or ''), alpha3)


def required_codes(languages: typing.Iterable[Language]) -> set[str]:
    """Return every tesseract model needed to rip the given languages."""
    return {tesseract_code(language) or DEFAULT_LANGUAGE_CODE for language in languages}


def config_arg(directory: str | None) -> str:
    """Return the tesseract argument pointing to directory, or an empty string when it cannot be passed safely.

    pytesseract splits the config string with shlex before handing it to tesseract, so a directory that does not
    survive that round trip (e.g. a Windows path containing a space) has to be passed as TESSDATA_PREFIX instead.
    """
    if not directory:
        return ''

    if shlex.split(directory, posix=(sys.platform != 'win32')) != [directory]:
        logger.debug('Cannot pass %s as --tessdata-dir: TESSDATA_PREFIX is used', directory)
        return ''

    return f'--tessdata-dir {directory}'


@contextmanager
def tesseract_env(directory: str | None) -> typing.Iterator[None]:
    """Set the environment of the tesseract processes for the block, and restore the previous values after.

    pytesseract gives `os.environ` to each tesseract process. `OMP_THREAD_LIMIT=1`: one process with OpenMP
    threads uses about one core, and pgsrip runs one process for each composite in parallel. `TESSDATA_PREFIX`
    points at directory, for the case when it cannot be passed as `--tessdata-dir`.
    """
    values = {'OMP_THREAD_LIMIT': '1', **({'TESSDATA_PREFIX': directory} if directory else {})}
    previous = {name: os.environ.get(name) for name in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class Tessdata:
    """The tesseract data files. It downloads the missing files when `download` is set."""

    def __init__(
        self,
        data_dir: str | None = None,
        repository: str = DEFAULT_REPOSITORY,
        download: bool = True,
    ):
        #: the directory of the option, None for the default: see `target_dir`
        self.data_dir = data_dir
        self.repository = repository
        self.download = download
        self._target_dir: str | None = None
        self._installed_codes: set[str] | None = None
        #: tesseract was asked for its languages: a failure is not asked again
        self._queried = False

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self) -> str:
        return f'data_dir:{self.data_dir}, repository:{self.repository}, download:{self.download}'

    @property
    def base_url(self) -> str:
        # a hidden hook for the tests: a mirror of the repository
        url = os.getenv('PGSRIP_TESSDATA_URL') or REPOSITORIES.get(self.repository)
        if not url:
            raise TessdataError(f'Unknown tessdata repository {self.repository}: expected {sorted(REPOSITORIES)}')

        return url.rstrip('/')

    @property
    def installed_codes(self) -> set[str] | None:
        """Models tesseract already finds on its own, or None when tesseract cannot be queried."""
        if not self._queried:
            self._queried = True
            try:
                self._installed_codes = set(tess.get_languages())
            except Exception as e:
                # tesseract itself is missing or broken: downloading data would not help
                logger.warning('Cannot list installed tesseract languages: <%s> %s', type(e).__name__, e)
            else:
                logger.debug('Tesseract has %d languages installed', len(self._installed_codes))

        return self._installed_codes

    @property
    def target_dir(self) -> str:
        """First writable directory where downloaded data can be stored."""
        if self._target_dir is None:
            candidates = [
                self.data_dir,
                os.getenv('TESSDATA_PREFIX'),
                cache_dir('tessdata'),
                os.path.join(tempfile.gettempdir(), 'pgsrip', 'tessdata'),
            ]
            for candidate in candidates:
                if candidate and is_writable(candidate):
                    self._target_dir = candidate
                    break
            else:
                raise TessdataError('No writable directory found to store tesseract data')

        return self._target_dir

    def path(self, code: str) -> str:
        """The file of a downloaded model."""
        return os.path.join(self.target_dir, f'{code}{TRAINED_DATA_EXTENSION}')

    def available(self, code: str) -> bool:
        """True when tesseract runs and has the model, or `ensure` can give it: downloaded before, or download on."""
        installed = self.installed_codes
        if installed is None:
            return False
        if code in installed or self.download:
            return True

        try:
            return os.path.isfile(self.path(code))
        except TessdataError:
            # no writable directory: nothing was downloaded before
            return False

    def ensure(
        self, codes: typing.Iterable[str], on_download: typing.Callable[[str], None] | None = None
    ) -> str | None:
        """Make the given models available to tesseract. Call `on_download` with the code before each download.

        Returns the directory tesseract has to be pointed at, or None when it already finds everything itself.
        """
        installed = self.installed_codes
        if installed is None:
            return None

        missing = sorted(code for code in codes if code not in installed)
        if not missing:
            return None

        directory = self.target_dir
        for code in missing:
            path = self.path(code)
            if os.path.isfile(path):
                logger.debug('Using previously downloaded tesseract data %s', path)
                continue

            if not self.download:
                # tesseract will report the missing data itself, there is nothing to redirect it to
                logger.warning('Tesseract data not installed for %s and downloading is disabled', code)
                return None

            if on_download:
                on_download(code)
            self.fetch(code, path)

        # data already visible to tesseract does not need it to be redirected
        return None if directory == os.getenv('TESSDATA_PREFIX') else directory

    def fetch(self, code: str, path: str) -> None:
        url = f'{self.base_url}/{code}{TRAINED_DATA_EXTENSION}'
        logger.info('Downloading tesseract data %s to %s', url, path)
        os.makedirs(os.path.dirname(path), exist_ok=True)

        request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        temp_path: str | None = None
        try:
            with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
                with tempfile.NamedTemporaryFile(dir=os.path.dirname(path), suffix='.part', delete=False) as f:
                    temp_path = f.name
                    shutil.copyfileobj(response, f)

            if not os.path.getsize(temp_path):
                raise TessdataError(f'Tesseract data downloaded from {url} is empty')

            # concurrent rips can be downloading the very same model: only the rename has to be atomic
            os.replace(temp_path, path)
            temp_path = None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise TessdataError(
                    f'Tesseract data for {code} is not available in the {self.repository} repository'
                ) from e
            raise TessdataError(f'Cannot download tesseract data for {code}: <HTTPError {e.code}> {e.reason}') from e
        except urllib.error.URLError as e:
            raise TessdataError(f'Cannot download tesseract data for {code}: {e.reason}') from e
        except OSError as e:
            raise TessdataError(f'Cannot save tesseract data for {code}: <{type(e).__name__}> {e}') from e
        finally:
            if temp_path and os.path.isfile(temp_path):
                os.remove(temp_path)
