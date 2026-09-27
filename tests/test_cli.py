from click.testing import CliRunner

from pgsrip.cli import pgsrip
from pgsrip.diagnostics import Check


def test_rip_help_lists_the_flag_selection_options():
    result = CliRunner().invoke(pgsrip, ['rip', '--help'])

    assert result.exit_code == 0
    assert '--with' in result.output
    assert '--without' in result.output
    assert '--one-per-language' in result.output


def test_doctor_shows_the_mkvtoolnix_checks(monkeypatch):
    monkeypatch.setattr('pgsrip.sources.mkvtoolnix.check_executable', lambda name, hint: Check(name, 'fake'))

    result = CliRunner().invoke(pgsrip, ['doctor'])

    lines = result.output.splitlines()
    assert any(line.startswith('mkvmerge ') and line.endswith('fake') for line in lines)
    assert any(line.startswith('mkvextract ') and line.endswith('fake') for line in lines)
