import os
import sys
import typing

import numpy as np
import numpy.typing as npt

#: cap for the default number of parallel OCR jobs: a container with a CPU quota still reports every host core.
MAX_DEFAULT_WORKERS = 4
#: a part of a cue lower than this share of its tallest part is not a text line, e.g. the dots of an umlaut.
MIN_LINE_SHARE = 0.4


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


def to_time(value: float | None) -> int | None:
    """The time in int milliseconds. It truncates, as `SubRipTime.from_ordinal` does."""
    return int(value) if value is not None else None


def format_time(ms: int | None) -> str:
    """The time as `HH:MM:SS,mmm`, the SRT format. `'None'` for None."""
    if ms is None:
        return 'None'

    seconds, millis = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}'


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


def split_lines(bitmap: npt.NDArray[np.uint8]) -> list[npt.NDArray[np.uint8]]:
    """Cut a subtitle bitmap at its empty rows: one image for each text line.

    A line recognition model reads one line of text. One image for each line also keeps the line breaks.
    A part that is too low to be a line (the dots of an umlaut) goes with the part below it.
    """
    parts: list[list[int]] = []
    for row in np.flatnonzero((bitmap < 128).any(axis=1)).tolist():
        if parts and parts[-1][1] == row:
            parts[-1][1] = row + 1
        else:
            parts.append([row, row + 1])

    tallest = max((end - start for start, end in parts), default=0)
    lines: list[list[int]] = []
    start: int | None = None
    for part_start, part_end in parts:
        start = part_start if start is None else start
        if part_end - part_start >= MIN_LINE_SHARE * tallest:
            lines.append([start, part_end])
            start = None
    if start is not None and lines:
        # a low part at the bottom, e.g. a line of dots: it goes with the line above it
        lines[-1][1] = parts[-1][1]

    return [bitmap[top:bottom] for top, bottom in lines] or [bitmap]
