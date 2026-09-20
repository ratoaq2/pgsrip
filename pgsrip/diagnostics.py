"""Environment checks, to know what a bug reporter has installed."""

from __future__ import annotations

import importlib.metadata
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import typing

import pytesseract as tess

from pgsrip import __version__
from pgsrip.options import Options
from pgsrip.tessdata import Tessdata, TessdataError, is_writable

logger = logging.getLogger(__name__)

MKVTOOLNIX_EXECUTABLES = ('mkvmerge', 'mkvextract')
REPORTED_PACKAGES = ('click', 'numpy', 'opencv-python', 'pytesseract', 'pysrt', 'babelfish', 'cleanit', 'trakit')
MKVTOOLNIX_HINT = 'Install MKVToolNix: https://mkvtoolnix.download/downloads.html'
TESSERACT_HINT = 'Install tesseract-ocr and make sure that it is in the PATH'
COMMAND_TIMEOUT = 10
MAX_REPORTED_LANGUAGES = 20


class Check(typing.NamedTuple):
    """One line of the environment report."""

    name: str
    value: str
    ok: bool = True
    hint: str | None = None


def run_command(*args: str) -> str | None:
    """Return the first line printed by a command, or None when it cannot be run."""
    try:
        output = subprocess.check_output(args, stderr=subprocess.DEVNULL, timeout=COMMAND_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        logger.debug('Cannot run %s: <%s> %s', args[0], type(e).__name__, e)
        return None

    return output.decode(errors='replace').strip().splitlines()[0]


def check_executable(name: str, hint: str) -> Check:
    path = shutil.which(name)
    if not path:
        return Check(name, 'not found', ok=False, hint=hint)

    version = run_command(name, '--version')

    return Check(name, f'{version or "unknown version"} ({path})')


def check_tesseract() -> Check:
    path = shutil.which('tesseract')
    try:
        version = tess.get_tesseract_version()
    except Exception as e:
        logger.debug('Cannot get the tesseract version: <%s> %s', type(e).__name__, e)
        return Check('tesseract', f'not found: <{type(e).__name__}> {e}', ok=False, hint=TESSERACT_HINT)

    return Check('tesseract', f'{version} ({path or "unknown path"})')


def check_languages() -> Check:
    try:
        codes = sorted(tess.get_languages())
    except Exception as e:
        logger.debug('Cannot list the tesseract languages: <%s> %s', type(e).__name__, e)
        return Check('tesseract languages', f'unknown: <{type(e).__name__}> {e}', ok=False, hint=TESSERACT_HINT)

    if not codes:
        return Check('tesseract languages', 'none installed, pgsrip downloads the ones it needs')

    listed = codes[:MAX_REPORTED_LANGUAGES]
    remaining = len(codes) - len(listed)

    return Check('tesseract languages', f'{", ".join(listed)}{f" and {remaining} more" if remaining else ""}')


def check_tessdata(options: Options) -> list[Check]:
    tessdata = Tessdata.from_options(options)
    checks = [
        Check('tessdata directory', str(tessdata.directory or 'not set')),
        Check('TESSDATA_PREFIX', os.getenv('TESSDATA_PREFIX') or 'not set'),
        Check('tessdata repository', tessdata.repository),
        Check('tessdata download', 'enabled' if tessdata.download else 'disabled'),
    ]
    try:
        checks.append(Check('tessdata download directory', tessdata.target_dir))
    except TessdataError as e:
        checks.append(
            Check('tessdata download directory', str(e), ok=False, hint='Set --tessdata-dir to a writable directory')
        )

    return checks


def check_packages() -> list[Check]:
    checks = []
    for name in REPORTED_PACKAGES:
        try:
            checks.append(Check(name, importlib.metadata.version(name)))
        except importlib.metadata.PackageNotFoundError:
            checks.append(Check(name, 'not installed', ok=False, hint=f'Install {name}'))

    return checks


def check_temp_directory() -> Check:
    directory = tempfile.gettempdir()
    if not is_writable(directory):
        return Check(
            'temporary directory', f'{directory} is not writable', ok=False, hint='Set TMPDIR to a writable directory'
        )

    return Check('temporary directory', directory)


def run_checks(options: Options | None = None) -> list[Check]:
    """Collect everything that is worth knowing about this installation."""
    checks = [
        Check('pgsrip', __version__),
        Check('python', f'{platform.python_version()} ({sys.executable})'),
        Check('platform', platform.platform()),
    ]
    checks += [check_executable(name, MKVTOOLNIX_HINT) for name in MKVTOOLNIX_EXECUTABLES]
    checks.append(check_tesseract())
    checks.append(check_languages())
    checks += check_tessdata(options or Options())
    checks.append(check_temp_directory())
    checks += check_packages()

    return checks


def format_checks(checks: typing.Iterable[Check]) -> str:
    """Render the checks as text that can be pasted into a bug report."""
    checks = list(checks)
    width = max(len(check.name) for check in checks)

    return '\n'.join(f'{check.name.ljust(width)}  {check.value}' for check in checks)
