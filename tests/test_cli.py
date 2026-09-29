import logging
import shutil

import pytest
from click.testing import CliRunner

from pgsrip.cli import pgsrip
from pgsrip.diagnostics import Check
from pgsrip.formats.scrub import ScrubError

from .fabricate import SAMPLE


def test_rip_help_lists_the_flag_selection_options():
    result = CliRunner().invoke(pgsrip, ['rip', '--help'])

    assert result.exit_code == 0
    assert '--with' in result.output
    assert '--without' in result.output
    assert '--one-per-language' in result.output
    assert 'Rip only the videos that are newer than AGE' in result.output


def test_doctor_shows_the_mkvtoolnix_checks(monkeypatch):
    monkeypatch.setattr('pgsrip.sources.mkvtoolnix.check_executable', lambda name, hint: Check(name, 'fake'))

    result = CliRunner().invoke(pgsrip, ['doctor'])

    lines = result.output.splitlines()
    assert any(line.startswith('mkvmerge ') and line.endswith('fake') for line in lines)
    assert any(line.startswith('mkvextract ') and line.endswith('fake') for line in lines)


@pytest.mark.parametrize('command', ['rip', 'scrub'])
def test_a_log_file_that_cannot_be_opened_is_an_error(command, tmp_path):
    log_file = tmp_path / 'missing' / 'pgsrip.log'

    result = CliRunner().invoke(pgsrip, [command, '--log-file', str(log_file), str(tmp_path)])

    assert result.exit_code != 0
    assert 'pgsrip.log' in result.output


@pytest.mark.parametrize(('args', 'listed'), [([], 10), (['-v'], 11)])
def test_v_lists_all_the_ignored_paths(args, listed, tmp_path):
    paths = [str(tmp_path / f'missing-{index}.mkv') for index in range(11)]

    result = CliRunner().invoke(pgsrip, ['rip', *args, *paths])

    assert sum(' ignored: ' in line for line in result.output.splitlines()) == listed
    assert ('... and 1 more, use -v to see them all' in result.output) == (not args)


def test_scrub_exits_with_1_when_a_scrub_fails(tmp_path, monkeypatch):
    shutil.copy(SAMPLE, tmp_path)

    def fail(*args, **kwargs):
        raise ScrubError('corrupted')

    monkeypatch.setattr('pgsrip.cli.scrub_data', fail)

    result = CliRunner().invoke(pgsrip, ['scrub', '-o', str(tmp_path / 'out'), str(tmp_path)])

    assert result.exit_code == 1
    assert 'Cannot scrub' in result.output


def test_scrub_exits_with_1_when_it_finds_no_media(tmp_path):
    result = CliRunner().invoke(pgsrip, ['scrub', str(tmp_path)])

    assert result.exit_code == 1
    assert 'No media to scrub' in result.output


@pytest.mark.parametrize('command', ['rip', 'scrub'])
def test_the_log_handlers_are_removed_at_the_end_of_each_run(command, tmp_path):
    logger = logging.getLogger('pgsrip')
    level = logger.level
    for _ in range(2):
        CliRunner().invoke(pgsrip, [command, '--debug', '--log-file', str(tmp_path / 'pgsrip.log'), str(tmp_path)])

        assert logger.handlers == []
        assert logger.level == level


def test_an_empty_age_is_an_error(tmp_path):
    result = CliRunner().invoke(pgsrip, ['rip', '--age', '', str(tmp_path)])

    assert result.exit_code == 2
    assert 'is not a valid age' in result.output
