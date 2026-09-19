import typing

from pysrt import SubRipTime


def from_hex(b: bytes) -> int | None:
    return int(b.hex(), base=16) if len(b) > 0 else None


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
    return SubRipTime.from_ordinal(value) if value else None


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
