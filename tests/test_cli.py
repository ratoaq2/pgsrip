from click.testing import CliRunner

from pgsrip.cli import pgsrip


def test_rip_help_lists_the_flag_selection_options():
    result = CliRunner().invoke(pgsrip, ['rip', '--help'])

    assert result.exit_code == 0
    assert '--with' in result.output
    assert '--without' in result.output
    assert '--one-per-language' in result.output
