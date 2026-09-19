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

from pgsrip.options import Options

logger = logging.getLogger(__name__)

TRAINED_DATA_EXTENSION = '.traineddata'
DEFAULT_LANGUAGE_CODE = 'eng'
OSD_CODE = 'osd'
# page segmentation modes that need osd.traineddata on top of the language itself
OSD_PAGE_SEGMENTATION_MODES = frozenset({0, 1, 12})

DEFAULT_REPOSITORY = 'best'
REPOSITORIES = {
    'best': 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main',
    'fast': 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main',
    'standard': 'https://raw.githubusercontent.com/tesseract-ocr/tessdata/main',
}
DOWNLOAD_TIMEOUT = 30
USER_AGENT = 'pgsrip'

# tesseract does not name every model after its alpha3 code: some are script specific
SCRIPT_CODES = {
    ('aze', 'Cyrl'): 'aze_cyrl',
    ('srp', 'Latn'): 'srp_latn',
    ('uzb', 'Cyrl'): 'uzb_cyrl',
    ('zho', 'Hans'): 'chi_sim',
    ('zho', 'Hant'): 'chi_tra',
}
TRADITIONAL_CHINESE_COUNTRIES = frozenset({'HK', 'MO', 'TW'})


class TessdataError(Exception):
    """Raised when the tesseract data required to rip a subtitle cannot be made available."""


def get_tesseract_code(language: Language) -> str | None:
    """Return the tesseract model name for a language, or None when the language is unknown."""
    if not language:
        return None

    alpha3 = str(language.alpha3)
    script = str(language.script) if language.script else None
    country = str(language.country) if language.country else None
    if alpha3 == 'zho' and script is None:
        script = 'Hant' if country in TRADITIONAL_CHINESE_COUNTRIES else 'Hans'

    return SCRIPT_CODES.get((alpha3, script or ''), alpha3)


def get_required_codes(languages: typing.Iterable[Language], psm_value: int | None = None) -> set[str]:
    """Return every tesseract model needed to rip the given languages."""
    codes = {get_tesseract_code(language) or DEFAULT_LANGUAGE_CODE for language in languages}
    if psm_value in OSD_PAGE_SEGMENTATION_MODES:
        codes.add(OSD_CODE)

    return codes


def get_config_arg(directory: str | None) -> str:
    """Return the tesseract argument pointing to directory, or an empty string when it cannot be passed safely.

    pytesseract splits the config string with shlex before handing it to tesseract, so a directory that does not
    survive that round trip (e.g. a Windows path containing a space) has to be passed as TESSDATA_PREFIX instead.
    """
    if not directory:
        return ''

    if shlex.split(directory, posix=(sys.platform != 'win32')) != [directory]:
        logger.debug('Cannot pass %s as --tessdata-dir, falling back to TESSDATA_PREFIX', directory)
        return ''

    return f'--tessdata-dir {directory}'


@contextmanager
def tessdata_env(directory: str | None) -> typing.Iterator[None]:
    """Point TESSDATA_PREFIX at directory for the duration of the block, restoring the previous value after."""
    if not directory:
        yield
        return

    previous = os.environ.get('TESSDATA_PREFIX')
    os.environ['TESSDATA_PREFIX'] = directory
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('TESSDATA_PREFIX', None)
        else:
            os.environ['TESSDATA_PREFIX'] = previous


def get_user_cache_dir() -> str:
    if sys.platform == 'win32':
        return os.getenv('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
    if sys.platform == 'darwin':
        return os.path.join(os.path.expanduser('~'), 'Library', 'Caches')

    return os.getenv('XDG_CACHE_HOME') or os.path.join(os.path.expanduser('~'), '.cache')


def is_writable(directory: str) -> bool:
    try:
        os.makedirs(directory, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, suffix='.pgsrip'):
            return True
    except OSError as e:
        logger.debug('Cannot write tesseract data to %s: <%s> %s', directory, type(e).__name__, e)
        return False


class Tessdata:
    """Makes sure tesseract has the data files it needs, downloading the missing ones when allowed."""

    def __init__(
        self,
        directory: str | None = None,
        repository: str | None = None,
        download: bool = True,
        timeout: int = DOWNLOAD_TIMEOUT,
    ):
        self.directory = directory or os.getenv('PGSRIP_TESSDATA_DIR') or None
        self.repository = repository or os.getenv('PGSRIP_TESSDATA_REPO') or DEFAULT_REPOSITORY
        self.download = download
        self.timeout = timeout
        self._target_dir: str | None = None
        self._installed_codes: set[str] | None = None

    @classmethod
    def from_options(cls, options: Options) -> Tessdata:
        return cls(
            directory=options.tessdata_dir,
            repository=options.tessdata_repository,
            download=options.download_tessdata,
        )

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self) -> str:
        return f'directory:{self.directory}, repository:{self.repository}, download:{self.download}'

    @property
    def base_url(self) -> str:
        url = os.getenv('PGSRIP_TESSDATA_URL') or REPOSITORIES.get(self.repository)
        if not url:
            raise TessdataError(f'Unknown tessdata repository {self.repository}: expected {sorted(REPOSITORIES)}')

        return url.rstrip('/')

    @property
    def installed_codes(self) -> set[str] | None:
        """Models tesseract already finds on its own, or None when tesseract cannot be queried."""
        if self._installed_codes is None:
            try:
                codes: set[str] = set(tess.get_languages())
            except Exception as e:
                # tesseract itself is missing or broken: downloading data would not help
                logger.warning('Cannot list installed tesseract languages: <%s> %s', type(e).__name__, e)
                return None

            logger.debug('Tesseract has %d languages installed', len(codes))
            self._installed_codes = codes

        return self._installed_codes

    @property
    def target_dir(self) -> str:
        """First writable directory where downloaded data can be stored."""
        if self._target_dir is None:
            candidates = [
                self.directory,
                os.getenv('TESSDATA_PREFIX'),
                os.path.join(get_user_cache_dir(), 'pgsrip', 'tessdata'),
                os.path.join(tempfile.gettempdir(), 'pgsrip', 'tessdata'),
            ]
            for candidate in candidates:
                if candidate and is_writable(candidate):
                    self._target_dir = candidate
                    break
            else:
                raise TessdataError('No writable directory found to store tesseract data')

        return self._target_dir

    def ensure(self, codes: typing.Iterable[str], reporter: typing.Callable[[str], None] | None = None) -> str | None:
        """Make the given models available to tesseract, calling reporter before each actual download.

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
            path = os.path.join(directory, f'{code}{TRAINED_DATA_EXTENSION}')
            if os.path.isfile(path):
                logger.debug('Using previously downloaded tesseract data %s', path)
                continue

            if not self.download:
                # tesseract will report the missing data itself, there is nothing to redirect it to
                logger.warning('Tesseract data not installed for %s and downloading is disabled', code)
                return None

            if reporter:
                reporter(code)
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
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
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
