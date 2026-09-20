import pytest

from pgsrip.diagnostics import (
    Check,
    check_executable,
    check_languages,
    check_tesseract,
    format_checks,
    run_checks,
)


@pytest.fixture
def missing_tesseract(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('tesseract not found')

    monkeypatch.setattr('pgsrip.diagnostics.tess.get_tesseract_version', fail)
    monkeypatch.setattr('pgsrip.diagnostics.tess.get_languages', fail)


def test_check_executable_reports_missing_executable(monkeypatch):
    monkeypatch.setattr('pgsrip.diagnostics.shutil.which', lambda name: None)

    check = check_executable('mkvmerge', 'Install MKVToolNix')

    assert check == Check('mkvmerge', 'not found', ok=False, hint='Install MKVToolNix')


def test_check_executable_reports_version(monkeypatch):
    monkeypatch.setattr('pgsrip.diagnostics.shutil.which', lambda name: f'/usr/bin/{name}')
    monkeypatch.setattr('pgsrip.diagnostics.run_command', lambda *args: 'mkvmerge v90.0')

    check = check_executable('mkvmerge', 'Install MKVToolNix')

    assert check.ok
    assert check.value == 'mkvmerge v90.0 (/usr/bin/mkvmerge)'


def test_check_tesseract_reports_missing_tesseract(missing_tesseract):
    check = check_tesseract()

    assert not check.ok
    assert check.hint


def test_check_languages_reports_missing_tesseract(missing_tesseract):
    check = check_languages()

    assert not check.ok
    assert check.hint


def test_check_languages_lists_installed_languages(monkeypatch):
    monkeypatch.setattr('pgsrip.diagnostics.tess.get_languages', lambda: ['por', 'eng'])

    assert check_languages() == Check('tesseract languages', 'eng, por')


def test_check_languages_cuts_a_long_list_short(monkeypatch):
    monkeypatch.setattr('pgsrip.diagnostics.tess.get_languages', lambda: [f'l{i:02d}' for i in range(25)])

    assert check_languages().value.endswith('and 5 more')


def test_run_checks_reports_the_versions(missing_tesseract):
    checks = {check.name: check for check in run_checks()}

    assert checks['pgsrip'].ok
    assert 'python' in checks
    assert not checks['tesseract'].ok


def test_format_checks_aligns_the_values():
    checks = [Check('pgsrip', '0.1.0'), Check('python', '3.13.0')]

    assert format_checks(checks) == 'pgsrip  0.1.0\npython  3.13.0'
