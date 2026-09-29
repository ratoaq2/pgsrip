from __future__ import annotations

import os
import time
import typing
from datetime import timedelta

import pytest

from pgsrip.api import pending_writers
from pgsrip.cue import Cue
from pgsrip.media import Media, Subtitle
from pgsrip.options import Options
from pgsrip.sources.base import Track
from pgsrip.writers.srt import SrtWriter


class FakeWriter:
    """A second output format: it writes the text of each cue on a line."""

    name: typing.ClassVar[str] = 'fake'
    extension: typing.ClassVar[str] = 'fake'

    def write(self, path: str, cues: list[Cue], track: Track, encoding: str | None) -> None:
        with open(path, mode='w', encoding=encoding or 'utf-8') as f:
            f.write('\n'.join(cue.text for cue in cues if cue.text))


def cue(index: int, start: int, end: int, text: str | None) -> Cue:
    return Cue(index, start, end, text, None, False, None, typing.cast(typing.Any, None))


def test_the_srt_writer_sorts_the_cues_and_leaves_out_a_cue_with_no_text(tmp_path: typing.Any) -> None:
    path = tmp_path / 'movie.en.srt'
    cues = [cue(1, 4000, 6000, 'Café'), cue(2, 6500, 7000, None), cue(0, 1000, 3000, 'Line one\nLine two')]

    SrtWriter().write(str(path), cues, typing.cast(Track, None), 'utf-8')

    expected = '1\n00:00:01,000 --> 00:00:03,000\nLine one\nLine two\n\n2\n00:00:04,000 --> 00:00:06,000\nCafé\n\n'
    assert path.read_bytes() == expected.replace('\n', os.linesep).encode('utf-8')


@pytest.fixture
def subtitle(tmp_path: typing.Any) -> Subtitle:
    (subtitle,) = Media(str(tmp_path / 'movie.en.sup')).subtitles(Options())
    return subtitle


def names(writers: list[typing.Any]) -> list[str]:
    return [w.name for w in writers]


def test_all_the_writers_are_pending_when_no_file_exists(subtitle: Subtitle) -> None:
    options = Options(writers=[SrtWriter(), FakeWriter()])

    assert names(pending_writers(subtitle, options)) == ['srt', 'fake']


def test_only_the_writer_of_the_missing_file_is_pending(tmp_path: typing.Any, subtitle: Subtitle) -> None:
    (tmp_path / 'movie.en.srt').write_text('')

    assert names(pending_writers(subtitle, Options(writers=[SrtWriter(), FakeWriter()]))) == ['fake']


def test_no_writer_is_pending_when_all_the_files_exist(tmp_path: typing.Any, subtitle: Subtitle) -> None:
    (tmp_path / 'movie.en.srt').write_text('')
    (tmp_path / 'movie.en.fake').write_text('')
    options = Options(writers=[SrtWriter(), FakeWriter()])

    assert pending_writers(subtitle, options) == []


def test_force_writes_again_only_the_files_that_are_older_than_the_output_age(
    tmp_path: typing.Any, subtitle: Subtitle
) -> None:
    (tmp_path / 'movie.en.srt').write_text('')
    old = tmp_path / 'movie.en.fake'
    old.write_text('')
    two_days_ago = time.time() - timedelta(days=2).total_seconds()
    os.utime(old, (two_days_ago, two_days_ago))
    options = Options(force=True, output_age=timedelta(days=1), writers=[SrtWriter(), FakeWriter()])

    assert names(pending_writers(subtitle, options)) == ['fake']
