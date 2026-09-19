import io
import os
import urllib.error

import pytest
from babelfish import Language

from pgsrip.options import Options
from pgsrip.tessdata import (
    Tessdata,
    TessdataError,
    get_config_arg,
    get_required_codes,
    get_tesseract_code,
    tessdata_env,
)


@pytest.fixture
def installed(monkeypatch):
    def install(*codes: str):
        monkeypatch.setattr('pgsrip.tessdata.tess.get_languages', lambda: list(codes))

    return install


@pytest.fixture
def downloads(monkeypatch):
    requested = []

    def urlopen(request, timeout=None):
        requested.append(request.full_url)
        return io.BytesIO(b'traineddata')

    monkeypatch.setattr('pgsrip.tessdata.urllib.request.urlopen', urlopen)

    return requested


@pytest.mark.parametrize(
    'ietf, expected',
    [
        ('en', 'eng'),
        ('pt-BR', 'por'),
        ('de', 'deu'),
        ('zh', 'chi_sim'),
        ('zh-CN', 'chi_sim'),
        ('zh-Hans', 'chi_sim'),
        ('zh-TW', 'chi_tra'),
        ('zh-HK', 'chi_tra'),
        ('zh-Hant', 'chi_tra'),
        ('sr', 'srp'),
        ('sr-Latn', 'srp_latn'),
        ('uz-Cyrl', 'uzb_cyrl'),
    ],
)
def test_get_tesseract_code(ietf, expected):
    assert get_tesseract_code(Language.fromietf(ietf)) == expected


def test_get_tesseract_code_undefined_language():
    assert get_tesseract_code(Language('und')) is None


def test_get_required_codes_defaults_to_english():
    assert get_required_codes([Language('und')]) == {'eng'}


def test_get_required_codes_adds_osd_when_page_segmentation_needs_it():
    languages = [Language.fromietf('en'), Language.fromietf('pt-BR')]

    assert get_required_codes(languages, psm_value=6) == {'eng', 'por'}
    assert get_required_codes(languages, psm_value=1) == {'eng', 'por', 'osd'}


def test_get_config_arg(tmp_path):
    directory = str(tmp_path / 'tessdata')

    assert get_config_arg(None) == ''
    assert get_config_arg(directory) == f'--tessdata-dir {directory}'


def test_get_config_arg_skips_directory_that_cannot_be_passed_as_argument(tmp_path):
    assert get_config_arg(str(tmp_path / 'tess data')) == ''


def test_tessdata_env_restores_previous_value(monkeypatch):
    monkeypatch.setenv('TESSDATA_PREFIX', '/previous')

    with tessdata_env('/other'):
        assert os.environ['TESSDATA_PREFIX'] == '/other'

    assert os.environ['TESSDATA_PREFIX'] == '/previous'


def test_tessdata_env_unsets_value_that_was_not_defined(monkeypatch):
    monkeypatch.delenv('TESSDATA_PREFIX', raising=False)

    with tessdata_env('/other'):
        assert os.environ['TESSDATA_PREFIX'] == '/other'

    assert 'TESSDATA_PREFIX' not in os.environ


def test_ensure_does_nothing_when_language_is_installed(installed, downloads, tmp_path):
    installed('eng', 'por')

    assert Tessdata(directory=str(tmp_path)).ensure({'por'}) is None
    assert downloads == []


def test_ensure_downloads_missing_language(installed, downloads, tmp_path):
    installed('eng')
    tessdata = Tessdata(directory=str(tmp_path))

    directory = tessdata.ensure({'por', 'eng'})

    assert directory == str(tmp_path)
    assert downloads == ['https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/por.traineddata']
    assert (tmp_path / 'por.traineddata').read_bytes() == b'traineddata'


def test_ensure_reports_each_downloaded_language(installed, downloads, tmp_path):
    installed()
    reported = []

    Tessdata(directory=str(tmp_path)).ensure({'por', 'eng'}, reporter=reported.append)

    assert reported == ['eng', 'por']


def test_ensure_reuses_previously_downloaded_language(installed, downloads, tmp_path):
    installed('eng')
    (tmp_path / 'por.traineddata').write_bytes(b'traineddata')

    directory = Tessdata(directory=str(tmp_path)).ensure({'por'})

    assert directory == str(tmp_path)
    assert downloads == []


def test_ensure_does_not_redirect_when_downloading_where_tesseract_already_looks(
    installed, downloads, tmp_path, monkeypatch
):
    installed('eng')
    monkeypatch.setenv('TESSDATA_PREFIX', str(tmp_path))

    assert Tessdata(directory=str(tmp_path)).ensure({'por'}) is None
    assert (tmp_path / 'por.traineddata').exists()


def test_ensure_skips_download_when_disabled(installed, downloads, tmp_path):
    installed('eng')

    assert Tessdata(directory=str(tmp_path), download=False).ensure({'por'}) is None
    assert downloads == []


def test_ensure_uses_previously_downloaded_language_even_when_download_is_disabled(installed, downloads, tmp_path):
    installed('eng')
    (tmp_path / 'por.traineddata').write_bytes(b'traineddata')

    assert Tessdata(directory=str(tmp_path), download=False).ensure({'por'}) == str(tmp_path)
    assert downloads == []


def test_ensure_skips_download_when_tesseract_cannot_be_queried(monkeypatch, downloads, tmp_path):
    def unavailable():
        raise OSError('tesseract is not installed')

    monkeypatch.setattr('pgsrip.tessdata.tess.get_languages', unavailable)

    assert Tessdata(directory=str(tmp_path)).ensure({'por'}) is None
    assert downloads == []


def test_ensure_uses_selected_repository(installed, downloads, tmp_path):
    installed()

    Tessdata(directory=str(tmp_path), repository='fast').ensure({'por'})

    assert downloads == ['https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/por.traineddata']


def test_ensure_uses_repository_defined_by_environment(installed, downloads, tmp_path, monkeypatch):
    installed()
    monkeypatch.setenv('PGSRIP_TESSDATA_URL', 'https://mirror.example.com/tessdata/')

    Tessdata(directory=str(tmp_path)).ensure({'por'})

    assert downloads == ['https://mirror.example.com/tessdata/por.traineddata']


def test_ensure_fails_on_unknown_repository(installed, tmp_path):
    installed()

    with pytest.raises(TessdataError, match='Unknown tessdata repository'):
        Tessdata(directory=str(tmp_path), repository='unknown').ensure({'por'})


def test_ensure_fails_when_language_is_not_available(installed, monkeypatch, tmp_path):
    installed()

    def urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 404, 'Not Found', {}, None)

    monkeypatch.setattr('pgsrip.tessdata.urllib.request.urlopen', urlopen)

    with pytest.raises(TessdataError, match='not available in the best repository'):
        Tessdata(directory=str(tmp_path)).ensure({'xyz'})

    assert not list(tmp_path.iterdir())


def test_ensure_fails_when_download_is_empty(installed, monkeypatch, tmp_path):
    installed()
    monkeypatch.setattr('pgsrip.tessdata.urllib.request.urlopen', lambda request, timeout=None: io.BytesIO(b''))

    with pytest.raises(TessdataError, match='is empty'):
        Tessdata(directory=str(tmp_path)).ensure({'por'})

    assert not list(tmp_path.iterdir())


def test_target_dir_falls_back_when_directory_is_not_writable(tmp_path, monkeypatch):
    monkeypatch.delenv('PGSRIP_TESSDATA_DIR', raising=False)
    monkeypatch.setenv('TESSDATA_PREFIX', str(tmp_path / 'prefix'))
    monkeypatch.setattr('pgsrip.tessdata.is_writable', lambda directory: 'prefix' not in directory)

    assert 'prefix' not in Tessdata().target_dir


def test_from_options():
    options = Options(tessdata_dir='/data', tessdata_repository='fast', download_tessdata=False)

    tessdata = Tessdata.from_options(options)

    assert tessdata.directory == '/data'
    assert tessdata.repository == 'fast'
    assert tessdata.download is False
