import io
import os
import urllib.error

import pytest
from babelfish import Language

from pgsrip.engines.tessdata import (
    Tessdata,
    TessdataError,
    config_arg,
    required_codes,
    tesseract_code,
    tesseract_env,
)
from pgsrip.engines.tesseract import TesseractEngine


@pytest.fixture
def installed(monkeypatch):
    def install(*codes: str):
        monkeypatch.setattr('pgsrip.engines.tessdata.tess.get_languages', lambda: list(codes))

    return install


@pytest.fixture
def downloads(monkeypatch):
    requested = []

    def urlopen(request, timeout=None):
        requested.append(request.full_url)
        return io.BytesIO(b'traineddata')

    monkeypatch.setattr('pgsrip.engines.tessdata.urllib.request.urlopen', urlopen)

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
def test_tesseract_code(ietf, expected):
    assert tesseract_code(Language.fromietf(ietf)) == expected


def test_tesseract_code_undefined_language():
    assert tesseract_code(Language('und')) is None


def test_required_codes_defaults_to_english():
    assert required_codes([Language('und')]) == {'eng'}


def test_required_codes_has_one_code_for_each_language():
    languages = [Language.fromietf('en'), Language.fromietf('pt-BR')]

    assert required_codes(languages) == {'eng', 'por'}


def test_config_arg(tmp_path):
    directory = str(tmp_path / 'tessdata')

    assert config_arg(None) == ''
    assert config_arg(directory) == f'--tessdata-dir {directory}'


def test_config_arg_skips_directory_that_cannot_be_passed_as_argument(tmp_path):
    assert config_arg(str(tmp_path / 'tess data')) == ''


def test_tesseract_env_restores_previous_value(monkeypatch):
    monkeypatch.setenv('TESSDATA_PREFIX', '/previous')

    with tesseract_env('/other'):
        assert os.environ['TESSDATA_PREFIX'] == '/other'

    assert os.environ['TESSDATA_PREFIX'] == '/previous'


def test_tesseract_env_unsets_value_that_was_not_defined(monkeypatch):
    monkeypatch.delenv('TESSDATA_PREFIX', raising=False)

    with tesseract_env('/other'):
        assert os.environ['TESSDATA_PREFIX'] == '/other'

    assert 'TESSDATA_PREFIX' not in os.environ


def test_ensure_does_nothing_when_language_is_installed(installed, downloads, tmp_path):
    installed('eng', 'por')

    assert Tessdata(data_dir=str(tmp_path)).ensure({'por'}) is None
    assert downloads == []


def test_ensure_downloads_missing_language(installed, downloads, tmp_path):
    installed('eng')
    tessdata = Tessdata(data_dir=str(tmp_path))

    directory = tessdata.ensure({'por', 'eng'})

    assert directory == str(tmp_path)
    assert downloads == ['https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/main/por.traineddata']
    assert (tmp_path / 'por.traineddata').read_bytes() == b'traineddata'


def test_ensure_reports_each_downloaded_language(installed, downloads, tmp_path):
    installed()
    reported = []

    Tessdata(data_dir=str(tmp_path)).ensure({'por', 'eng'}, on_download=reported.append)

    assert reported == ['eng', 'por']


def test_ensure_reuses_previously_downloaded_language(installed, downloads, tmp_path):
    installed('eng')
    (tmp_path / 'por.traineddata').write_bytes(b'traineddata')

    directory = Tessdata(data_dir=str(tmp_path)).ensure({'por'})

    assert directory == str(tmp_path)
    assert downloads == []


def test_ensure_does_not_redirect_when_downloading_where_tesseract_already_looks(
    installed, downloads, tmp_path, monkeypatch
):
    installed('eng')
    monkeypatch.setenv('TESSDATA_PREFIX', str(tmp_path))

    assert Tessdata(data_dir=str(tmp_path)).ensure({'por'}) is None
    assert (tmp_path / 'por.traineddata').exists()


def test_ensure_skips_download_when_disabled(installed, downloads, tmp_path):
    installed('eng')

    assert Tessdata(data_dir=str(tmp_path), download=False).ensure({'por'}) is None
    assert downloads == []


def test_ensure_uses_previously_downloaded_language_even_when_download_is_disabled(installed, downloads, tmp_path):
    installed('eng')
    (tmp_path / 'por.traineddata').write_bytes(b'traineddata')

    assert Tessdata(data_dir=str(tmp_path), download=False).ensure({'por'}) == str(tmp_path)
    assert downloads == []


def test_ensure_skips_download_when_tesseract_cannot_be_queried(monkeypatch, downloads, tmp_path):
    def unavailable():
        raise OSError('tesseract is not installed')

    monkeypatch.setattr('pgsrip.engines.tessdata.tess.get_languages', unavailable)

    assert Tessdata(data_dir=str(tmp_path)).ensure({'por'}) is None
    assert downloads == []


def test_a_missing_tesseract_is_asked_and_reported_one_time(monkeypatch, caplog):
    calls = []

    def unavailable():
        calls.append(1)
        raise OSError('tesseract is not installed')

    monkeypatch.setattr('pgsrip.engines.tessdata.tess.get_languages', unavailable)
    tessdata = Tessdata()

    assert tessdata.installed_codes is None
    assert tessdata.installed_codes is None
    assert len(calls) == 1
    assert caplog.text.count('Cannot list installed tesseract languages') == 1


def test_ensure_uses_selected_repository(installed, downloads, tmp_path):
    installed()

    Tessdata(data_dir=str(tmp_path), repository='fast').ensure({'por'})

    assert downloads == ['https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/por.traineddata']


def test_ensure_uses_repository_defined_by_environment(installed, downloads, tmp_path, monkeypatch):
    installed()
    monkeypatch.setenv('PGSRIP_TESSDATA_URL', 'https://mirror.example.com/tessdata/')

    Tessdata(data_dir=str(tmp_path)).ensure({'por'})

    assert downloads == ['https://mirror.example.com/tessdata/por.traineddata']


def test_ensure_fails_on_unknown_repository(installed, tmp_path):
    installed()

    with pytest.raises(TessdataError, match='Unknown tessdata repository'):
        Tessdata(data_dir=str(tmp_path), repository='unknown').ensure({'por'})


def test_ensure_fails_when_language_is_not_available(installed, monkeypatch, tmp_path):
    installed()

    def urlopen(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 404, 'Not Found', {}, None)

    monkeypatch.setattr('pgsrip.engines.tessdata.urllib.request.urlopen', urlopen)

    with pytest.raises(TessdataError, match='not available in the best repository'):
        Tessdata(data_dir=str(tmp_path)).ensure({'xyz'})

    assert not list(tmp_path.iterdir())


def test_ensure_fails_when_download_is_empty(installed, monkeypatch, tmp_path):
    installed()
    monkeypatch.setattr('pgsrip.engines.tessdata.urllib.request.urlopen', lambda request, timeout=None: io.BytesIO(b''))

    with pytest.raises(TessdataError, match='is empty'):
        Tessdata(data_dir=str(tmp_path)).ensure({'por'})

    assert not list(tmp_path.iterdir())


def test_tesseract_supports_no_language_when_tesseract_cannot_be_queried(monkeypatch, tmp_path):
    def unavailable():
        raise OSError('tesseract is not installed')

    monkeypatch.setattr('pgsrip.engines.tessdata.tess.get_languages', unavailable)

    assert not TesseractEngine(tessdata=Tessdata(data_dir=str(tmp_path))).supports(Language('eng'))


@pytest.mark.parametrize(
    'download, downloaded, supported',
    [
        pytest.param(True, False, True, id='download on'),
        pytest.param(False, False, False, id='download off and no data'),
        pytest.param(False, True, True, id='download off and data downloaded before'),
    ],
)
def test_tesseract_supports_a_language_that_it_has_or_can_get(installed, tmp_path, download, downloaded, supported):
    installed('eng')
    if downloaded:
        (tmp_path / 'por.traineddata').write_bytes(b'traineddata')
    engine = TesseractEngine(tessdata=Tessdata(data_dir=str(tmp_path), download=download))

    assert engine.supports(Language('eng'))
    assert engine.supports(Language('por')) is supported


def test_tesseract_does_not_support_a_language_whose_download_failed(installed, monkeypatch, tmp_path):
    installed()

    def urlopen(request, timeout=None):
        if 'por' in request.full_url:
            raise urllib.error.URLError('offline')
        return io.BytesIO(b'traineddata')

    monkeypatch.setattr('pgsrip.engines.tessdata.urllib.request.urlopen', urlopen)
    engine = TesseractEngine(tessdata=Tessdata(data_dir=str(tmp_path)))
    reported = []

    engine.prepare([Language('por'), Language('eng')], reporter=reported.append)

    # the failed download does not stop the next one
    assert reported == [
        'Downloading tesseract data for eng...',
        'Downloading tesseract data for por...',
        'Cannot download tesseract data for por: offline',
    ]
    assert engine.supports(Language('eng'))
    assert not engine.supports(Language('por'))


def test_target_dir_falls_back_when_directory_is_not_writable(tmp_path, monkeypatch):
    monkeypatch.setenv('TESSDATA_PREFIX', str(tmp_path / 'prefix'))
    monkeypatch.setattr('pgsrip.engines.tessdata.is_writable', lambda directory: 'prefix' not in directory)

    assert 'prefix' not in Tessdata().target_dir
