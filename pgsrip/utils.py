import logging
import os
import sys
import tempfile

from appdirs import user_cache_dir

logger = logging.getLogger(__name__)

#: cap for the default number of parallel OCR jobs: a container with a CPU quota still reports every host core.
MAX_DEFAULT_WORKERS = 4


def default_workers() -> int:
    """The CPUs this process may run on, at most MAX_DEFAULT_WORKERS."""
    if sys.version_info >= (3, 13):
        count = os.process_cpu_count()
    elif sys.platform == 'linux':
        count = len(os.sched_getaffinity(0))
    else:
        count = os.cpu_count()

    return min(MAX_DEFAULT_WORKERS, count or 1)


def format_time(ms: int | None) -> str | None:
    """The time as `HH:MM:SS,mmm`, the SRT format. None for None: the debug JSON writes null."""
    if ms is None:
        return None

    seconds, millis = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}'


def cache_dir(name: str) -> str:
    """The directory `name` in the user cache directory of pgsrip, e.g. `~/.cache/pgsrip/<name>` on Linux."""
    # no author and no `Cache` part on Windows: `%LOCALAPPDATA%\pgsrip`
    return os.path.join(user_cache_dir('pgsrip', appauthor=False, opinion=False), name)


def is_writable(directory: str) -> bool:
    try:
        os.makedirs(directory, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, suffix='.pgsrip'):
            return True
    except OSError as e:
        logger.debug('Cannot write to %s: <%s> %s', directory, type(e).__name__, e)
        return False
