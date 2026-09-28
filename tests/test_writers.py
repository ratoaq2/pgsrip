from __future__ import annotations

import os
import time
import typing
from datetime import timedelta

import pytest

from pgsrip.media import Pgs
from pgsrip.media_path import MediaPath
from pgsrip.options import Options
from pgsrip.ripper import Cue
from pgsrip.writers.srt import SrtWriter


class FakeWriter:
    """A second output format: it writes the text of each cue on a line."""

    name: typing.ClassVar[str] = 'fake'
    extension: typing.ClassVar[str] = 'fake'

    def write(self, path: str, pgs: Pgs, cues: list[Cue], encoding: str | None) -> None:
        with open(path, mode='w', encoding=encoding or 'utf-8') as f:
            f.write('\n'.join(cue.text for cue in cues if cue.text))


def cue(index: int, start: int, end: int, text: str | None) -> Cue:
    return Cue(index, start, end, text, None, False, None, typing.cast(typing.Any, None))


def test_the_srt_writer_sorts_the_cues_and_leaves_out_a_cue_with_no_text(tmp_path: typing.Any) -> None:
    path = tmp_path / 'movie.en.srt'
    cues = [cue(1, 4000, 6000, 'Café'), cue(2, 6500, 7000, None), cue(0, 1000, 3000, 'Line one\nLine two')]

    SrtWriter().write(str(path), typing.cast(Pgs, None), cues, 'utf-8')

    expected = '1\n00:00:01,000 --> 00:00:03,000\nLine one\nLine two\n\n2\n00:00:04,000 --> 00:00:06,000\nCafé\n\n'
    assert path.read_bytes() == expected.replace('\n', os.linesep).encode('utf-8')


@pytest.fixture
def pgs(tmp_path: typing.Any) -> Pgs:
    return Pgs(MediaPath(str(tmp_path / 'movie.en.sup')), Options(), data_reader=lambda: b'')


def names(writers: list[typing.Any]) -> list[str]:
    return [w.name for w in writers]


def test_all_the_writers_are_pending_when_no_file_exists(pgs: Pgs) -> None:
    options = Options(writers=[SrtWriter(), FakeWriter()])

    assert names(pgs.pending_writers(options)) == ['srt', 'fake']
    assert pgs.matches(options)


def test_only_the_writer_of_the_missing_file_is_pending(tmp_path: typing.Any, pgs: Pgs) -> None:
    (tmp_path / 'movie.en.srt').write_text('')

    assert names(pgs.pending_writers(Options(writers=[SrtWriter(), FakeWriter()]))) == ['fake']


def test_no_writer_is_pending_when_all_the_files_exist(tmp_path: typing.Any, pgs: Pgs) -> None:
    (tmp_path / 'movie.en.srt').write_text('')
    (tmp_path / 'movie.en.fake').write_text('')
    options = Options(writers=[SrtWriter(), FakeWriter()])

    assert pgs.pending_writers(options) == []
    assert not pgs.matches(options)


def test_force_writes_again_only_the_files_that_are_older_than_the_output_age(tmp_path: typing.Any, pgs: Pgs) -> None:
    (tmp_path / 'movie.en.srt').write_text('')
    old = tmp_path / 'movie.en.fake'
    old.write_text('')
    two_days_ago = time.time() - timedelta(days=2).total_seconds()
    os.utime(old, (two_days_ago, two_days_ago))
    options = Options(overwrite=True, output_age=timedelta(days=1), writers=[SrtWriter(), FakeWriter()])

    assert names(pgs.pending_writers(options)) == ['fake']
