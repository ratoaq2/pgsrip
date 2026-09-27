"""Environment checks, to know what a bug reporter has installed."""

from __future__ import annotations

import importlib.metadata
import logging
import platform
import shutil
import subprocess
import sys
import tempfile
import typing

from pgsrip import __version__
from pgsrip.engines.tessdata import is_writable

logger = logging.getLogger(__name__)

MKVTOOLNIX_EXECUTABLES = ('mkvmerge', 'mkvextract')
REPORTED_PACKAGES = ('click', 'numpy', 'opencv-python', 'pytesseract', 'pysrt', 'babelfish', 'cleanit', 'trakit')
MKVTOOLNIX_HINT = 'Install MKVToolNix: https://mkvtoolnix.download/downloads.html'
COMMAND_TIMEOUT = 10


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


def run_checks(engine_checks: list[Check] | None = None) -> list[Check]:
    """Collect everything that is worth knowing about this installation, with the checks of the OCR engines."""
    checks = [
        Check('pgsrip', __version__),
        Check('python', f'{platform.python_version()} ({sys.executable})'),
        Check('platform', platform.platform()),
    ]
    checks += [check_executable(name, MKVTOOLNIX_HINT) for name in MKVTOOLNIX_EXECUTABLES]
    checks += engine_checks or []
    checks.append(check_temp_directory())
    checks += check_packages()

    return checks


def format_checks(checks: typing.Iterable[Check]) -> str:
    """Render the checks as text that can be pasted into a bug report."""
    checks = list(checks)
    width = max(len(check.name) for check in checks)

    return '\n'.join(f'{check.name.ljust(width)}  {check.value}' for check in checks)
