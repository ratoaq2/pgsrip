import os
import sys
import typing

from pysrt import SubRipTime

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


def from_hex(b: bytes) -> int | None:
    return int.from_bytes(b, 'big') if b else None


@typing.overload
def safe_get(b: bytes, i: int) -> int: ...
@typing.overload
def safe_get(b: bytes, i: int, default_value: int) -> int: ...
@typing.overload
def safe_get(b: bytes, i: int, default_value: None) -> int | None: ...
def safe_get(b: bytes, i: int, default_value: int | None = 0) -> int | None:
    try:
        return b[i]
    except IndexError:
        return default_value


def to_time(value: float | None) -> SubRipTime | None:
    return SubRipTime.from_ordinal(value) if value is not None else None


T = typing.TypeVar('T')


def pairwise(iterable: typing.Iterable[T]) -> typing.Iterable[tuple[T, T | None]]:
    """s -> (s0, s1), (s1, s2), (s2, s3), (s2, None)"""
    it = iter(iterable)
    a = next(it, None)
    if a is not None:
        for b in it:
            yield a, b
            a = b

        yield a, None
