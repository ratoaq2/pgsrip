"""The OpenAI-compatible OCR engine against a stub server, driven through the CLI."""

from __future__ import annotations

import base64
import json
import threading
import time
import types
import typing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np
import pysrt
import pytest
from babelfish import Language
from click.testing import CliRunner

from pgsrip.cli import pgsrip
from pgsrip.engines.base import Reading
from pgsrip.engines.openai import API_KEY_ENV, OpenAiEngine, OpenAiError
from pgsrip.engines.tesseract import TesseractEngine

if typing.TYPE_CHECKING:
    from pgsrip.formats.pgs import Item


class StubServer:
    """Answers each chat completion with the next text, and records every request."""

    def __init__(self) -> None:
        self.texts = ['One', 'Two', 'Three']
        # (status, body) for every chat completion, instead of the texts
        self.answer: tuple[int, bytes] | None = None
        self.models_answer = (200, b'{"object": "list", "data": []}')
        self.delay = 0.0
        self.requests: list[tuple[str, dict[str, str], typing.Any]] = []
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), self.handler())
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}/v1'

    @property
    def completions(self) -> int:
        return [path for path, _, _ in self.requests].count('/v1/chat/completions')

    def handler(self) -> type[BaseHTTPRequestHandler]:
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                stub.requests.append((self.path, dict(self.headers), None))
                self.send(*stub.models_answer)

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                stub.requests.append((self.path, dict(self.headers), body))
                time.sleep(stub.delay)
                if stub.answer:
                    self.send(*stub.answer)
                    return

                text = stub.texts.pop(0)
                self.send(200, json.dumps({'choices': [{'message': {'role': 'assistant', 'content': text}}]}).encode())

            def send(self, status: int, body: bytes) -> None:
                try:
                    self.send_response(status)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except ConnectionError:
                    pass  # the client gave up first: the timeout test

            def log_message(self, format: str, *args: typing.Any) -> None:
                pass

        return Handler


@pytest.fixture
def server() -> typing.Iterator[StubServer]:
    stub = StubServer()
    thread = threading.Thread(target=stub.server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    thread.start()
    yield stub
    stub.server.shutdown()
    stub.server.server_close()


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never send the API key of the user who runs the tests."""
    monkeypatch.delenv(API_KEY_ENV, raising=False)


def rip(*args: str) -> typing.Any:
    return CliRunner().invoke(pgsrip, ['rip', *args])


def read_texts(media_dir: typing.Any) -> list[str]:
    return [item.text for item in pysrt.open(str(media_dir / 'placeholder.en.srt'), encoding='utf-8')]


def test_the_openai_engine_rips_each_cue_with_one_request(
    server: StubServer, media_dir: typing.Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(API_KEY_ENV, 'secret')

    result = rip(
        '--engine', 'openai', '--openai-url', server.url, '--openai-model', 'glm-ocr', '-w', '1', str(media_dir)
    )

    assert result.exit_code == 0, result.output
    assert read_texts(media_dir) == ['One', 'Two', 'Three']
    assert [path for path, _, _ in server.requests] == ['/v1/models'] + ['/v1/chat/completions'] * 3
    _, headers, body = server.requests[1]
    assert headers['Authorization'] == 'Bearer secret'
    assert body['model'] == 'glm-ocr'
    assert body['temperature'] == 0
    assert body['max_tokens'] == 512
    image, prompt = body['messages'][0]['content']
    assert image['image_url']['url'].startswith('data:image/png;base64,')
    assert 'English' in prompt['text']


def test_the_prompt_max_tokens_and_temperature_options_go_to_the_request(
    server: StubServer, media_dir: typing.Any
) -> None:
    result = rip(
        '--engine',
        'openai',
        '--openai-url',
        server.url,
        '--openai-prompt',
        'Read this {language} subtitle.',
        '--openai-max-tokens',
        '64',
        '--openai-temperature',
        '0.5',
        str(media_dir),
    )

    assert result.exit_code == 0, result.output
    body = server.requests[1][2]
    assert body['messages'][0]['content'][1]['text'] == 'Read this English subtitle.'
    assert body['max_tokens'] == 64
    assert body['temperature'] == 0.5


def test_the_extra_body_option_goes_to_each_request(server: StubServer, media_dir: typing.Any) -> None:
    extra_body = '{"chat_template_kwargs": {"enable_thinking": false}}'

    result = rip('--engine', 'openai', '--openai-url', server.url, '--openai-extra-body', extra_body, str(media_dir))

    assert result.exit_code == 0, result.output
    body = server.requests[1][2]
    assert body['chat_template_kwargs'] == {'enable_thinking': False}
    assert body['max_tokens'] == 512


def test_a_config_file_sets_the_extra_body_as_a_mapping(
    server: StubServer, media_dir: typing.Any, tmp_path: typing.Any
) -> None:
    config = tmp_path / 'config.yml'
    config.write_text('openai:\n  extra_body:\n    chat_template_kwargs: {enable_thinking: false}\n', encoding='utf-8')

    result = rip('--config', str(config), '--engine', 'openai', '--openai-url', server.url, str(media_dir))

    assert result.exit_code == 0, result.output
    body = server.requests[1][2]
    assert body['chat_template_kwargs'] == {'enable_thinking': False}
    assert body['max_tokens'] == 512


@pytest.mark.parametrize(
    ('value', 'message'),
    [
        pytest.param('{nope', 'is not valid JSON', id='not json'),
        pytest.param('[1, 2]', 'is not a JSON object', id='not an object'),
    ],
)
def test_an_extra_body_that_is_not_a_json_object_is_rejected(media_dir: typing.Any, value: str, message: str) -> None:
    url = 'http://localhost/v1'

    result = rip('--engine', 'openai', '--openai-url', url, '--openai-extra-body', value, str(media_dir))

    assert result.exit_code == 2
    assert message in result.output


@pytest.mark.parametrize(('border', 'size'), [pytest.param(20, 44, id='default'), pytest.param(2, 8, id='2 px')])
def test_the_border_sets_the_margin_of_each_image(server: StubServer, border: int, size: int) -> None:
    server.texts = ['Text']
    item = typing.cast('Item', types.SimpleNamespace(bitmap=np.zeros((4, 4), dtype=np.uint8)))

    OpenAiEngine(server.url, border=border).read(item, Language('eng'))

    url = server.requests[0][2]['messages'][0]['content'][0]['image_url']['url']
    png = np.frombuffer(base64.b64decode(url.removeprefix('data:image/png;base64,')), dtype=np.uint8)
    assert cv2.imdecode(png, cv2.IMREAD_GRAYSCALE).shape == (size, size)


def test_the_prompt_of_an_undetermined_language_has_no_language_name(server: StubServer) -> None:
    server.texts = ['Text']
    item = typing.cast('Item', types.SimpleNamespace(bitmap=np.zeros((4, 4), dtype=np.uint8)))

    OpenAiEngine(server.url).read(item, Language('und'))

    assert server.requests[0][2]['messages'][0]['content'][1]['text'].endswith('The language is unknown.')


def test_a_config_file_sets_the_openai_section(server: StubServer, media_dir: typing.Any, tmp_path: typing.Any) -> None:
    config = tmp_path / 'config.yml'
    config.write_text(
        f'engine: [openai]\nopenai:\n  url: {server.url}\n  api_key: secret\n  workers: 1\n', encoding='utf-8'
    )

    result = rip('--config', str(config), str(media_dir))

    assert result.exit_code == 0, result.output
    assert read_texts(media_dir) == ['One', 'Two', 'Three']
    assert server.requests[1][1]['Authorization'] == 'Bearer secret'


def test_the_openai_engine_sends_no_model_and_no_key_when_none_is_set(
    server: StubServer, media_dir: typing.Any
) -> None:
    result = rip('--engine', 'openai', '--openai-url', server.url, '-w', '1', str(media_dir))

    assert result.exit_code == 0, result.output
    _, headers, body = server.requests[1]
    assert 'Authorization' not in headers
    assert 'model' not in body


@pytest.mark.parametrize(
    ('request_per', 'requests', 'text'),
    [
        pytest.param('line', 2, 'First line\nSecond line', id='one request for each line'),
        pytest.param('cue', 1, 'First line', id='one request for each cue'),
    ],
)
def test_request_per_sets_the_requests_of_a_cue(server: StubServer, request_per: str, requests: int, text: str) -> None:
    server.texts = ['First line', 'Second line']
    bitmap = np.full((12, 4), 255, dtype=np.uint8)
    bitmap[[0, 1, 2, 3, 4, 7, 8, 9, 10, 11], 1] = 0
    item = typing.cast('Item', types.SimpleNamespace(bitmap=bitmap))

    assert OpenAiEngine(server.url, request_per=request_per).read(item, Language('und')) == text
    assert server.completions == requests


@pytest.mark.parametrize(
    ('args', 'request_per'),
    [pytest.param([], 'line', id='default'), pytest.param(['--openai-request-per', 'cue'], 'cue', id='option')],
)
def test_the_request_per_option_sets_the_engine(
    server: StubServer, media_dir: typing.Any, monkeypatch: pytest.MonkeyPatch, args: list[str], request_per: str
) -> None:
    engines: list[OpenAiEngine] = []
    monkeypatch.setattr(OpenAiEngine, 'recognize', lambda engine, items, *rest: engines.append(engine) or [])

    rip('--engine', 'openai', '--openai-url', server.url, *args, str(media_dir))

    assert [engine.request_per for engine in engines] == [request_per]


@pytest.mark.parametrize(
    ('status', 'body', 'message'),
    [
        pytest.param(500, b'model crashed', 'answered HTTP 500: model crashed', id='http error'),
        pytest.param(200, b'{"choices": []}', 'Unexpected answer', id='no choice'),
        pytest.param(200, b'{"choices": [{"message": {"content": null}}]}', 'Unexpected answer', id='no text'),
        pytest.param(200, b'not json', 'did not answer with JSON', id='not json'),
    ],
)
def test_a_failed_request_fails_the_track_and_writes_no_srt(
    server: StubServer, media_dir: typing.Any, status: int, body: bytes, message: str
) -> None:
    server.answer = (status, body)
    # slow answers: the one worker is still busy with the second cue when the first failure cancels the third
    server.delay = 0.2

    result = rip('--engine', 'openai', '--openai-url', server.url, '-w', '1', str(media_dir))

    assert result.exit_code == 1, result.output
    assert '1 PGS subtitle could not be ripped' in result.output
    assert message in result.output
    # a scrubbed sample cannot reproduce a server failure
    assert 'pgsrip scrub' not in result.output
    assert not (media_dir / 'placeholder.en.srt').exists()
    # the first failure cancels the requests that were not started
    assert server.completions < 3


@pytest.fixture
def tesseract_reads(monkeypatch: pytest.MonkeyPatch) -> dict[int, Reading]:
    """A fake tesseract: the reading of each item index. By default, cue 0 is sure, cue 1 is doubtful, and
    tesseract cannot read cue 2."""
    reads = {0: Reading('Sure'), 1: Reading('Doubtful', doubtful=True), 2: Reading(None)}

    def recognize(engine: TesseractEngine, items: list[Item], *args: typing.Any) -> list[Reading]:
        return [reads[item.index] for item in items]

    monkeypatch.setattr(TesseractEngine, 'prepare', lambda *args, **kwargs: None)
    monkeypatch.setattr(TesseractEngine, 'supports', lambda *args: True)
    monkeypatch.setattr(TesseractEngine, 'recognize', recognize)
    return reads


@pytest.mark.usefixtures('tesseract_reads')
def test_the_openai_engine_reads_the_doubtful_and_unread_cues_in_a_chain(
    server: StubServer, media_dir: typing.Any
) -> None:
    result = rip('--engine', 'tesseract', '--engine', 'openai', '--openai-url', server.url, '-w', '1', str(media_dir))

    assert result.exit_code == 0, result.output
    assert read_texts(media_dir) == ['Sure', 'One', 'Two']
    assert server.completions == 2


@pytest.mark.usefixtures('tesseract_reads')
def test_an_empty_answer_keeps_the_tesseract_text(server: StubServer, media_dir: typing.Any) -> None:
    server.texts = ['', 'Three']

    result = rip('--engine', 'tesseract', '--engine', 'openai', '--openai-url', server.url, '-w', '1', str(media_dir))

    assert result.exit_code == 0, result.output
    assert read_texts(media_dir) == ['Sure', 'Doubtful', 'Three']


def test_the_next_engine_gets_no_request_when_tesseract_is_sure_of_every_cue(
    server: StubServer, media_dir: typing.Any, tesseract_reads: dict[int, Reading]
) -> None:
    tesseract_reads.update({1: Reading('B'), 2: Reading('C')})

    result = rip('--engine', 'tesseract', '--engine', 'openai', '--openai-url', server.url, str(media_dir))

    assert result.exit_code == 0, result.output
    assert [path for path, _, _ in server.requests] == ['/v1/models']


@pytest.mark.parametrize(
    ('options', 'workers'),
    [
        pytest.param(['-w', '3'], 3, id='-w'),
        pytest.param(['-w', '3', '--openai-workers', '1'], 1, id='openai override'),
    ],
)
def test_the_openai_workers_override_the_workers_of_the_chain(
    server: StubServer, media_dir: typing.Any, monkeypatch: pytest.MonkeyPatch, options: list[str], workers: int
) -> None:
    engines: list[OpenAiEngine] = []
    monkeypatch.setattr(OpenAiEngine, 'recognize', lambda engine, items, *args: engines.append(engine) or [])

    rip('--engine', 'openai', '--openai-url', server.url, *options, str(media_dir))

    assert [engine.workers for engine in engines] == [workers]


def test_an_api_that_does_not_answer_stops_the_rip_before_it_starts(server: StubServer, media_dir: typing.Any) -> None:
    server.models_answer = (404, b'no such API')

    result = rip('--engine', 'openai', '--openai-url', server.url, str(media_dir))

    assert result.exit_code == 1
    assert f'{server.url}/models answered HTTP 404: no such API' in result.output
    assert server.requests[-1][0] == '/v1/models'
    assert 'Ripping subtitles' not in result.output
    assert not (media_dir / 'placeholder.en.srt').exists()


def test_a_slow_answer_is_a_timeout_error(server: StubServer) -> None:
    server.delay = 1

    with pytest.raises(OpenAiError, match='Cannot reach'):
        OpenAiEngine(server.url, timeout=0.2).request('/chat/completions', {})


def test_the_openai_timeout_option_sets_the_request_timeout(server: StubServer, media_dir: typing.Any) -> None:
    server.delay = 1

    result = rip('--engine', 'openai', '--openai-url', server.url, '--openai-timeout', '0.2', '-w', '1', str(media_dir))

    assert 'timed out' in result.output
    assert not (media_dir / 'placeholder.en.srt').exists()


def test_the_debug_directory_gets_the_image_of_each_request(server: StubServer, media_dir: typing.Any) -> None:
    result = rip('--engine', 'openai', '--openai-url', server.url, '-w', '1', '--keep-temp-files', str(media_dir))

    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in media_dir.parent.rglob('openai-*.png')) == [
        'openai-0-0.png',
        'openai-1-0.png',
        'openai-2-0.png',
    ]


@pytest.mark.usefixtures('tesseract_reads')
def test_an_api_key_in_the_environment_does_not_need_the_openai_engine(
    media_dir: typing.Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(API_KEY_ENV, 'secret')

    result = rip('--engine', 'tesseract', str(media_dir))

    assert result.exit_code == 0, result.output


@pytest.mark.parametrize(
    ('args', 'message'),
    [
        pytest.param(['--engine', 'openai'], '--engine openai needs --openai-url', id='openai without url'),
        pytest.param(['--openai-url', 'http://localhost/v1'], 'the --openai-* options need --engine openai', id='url'),
        pytest.param(['--openai-model', 'glm-ocr'], 'the --openai-* options need --engine openai', id='model'),
        pytest.param(['--openai-api-key', 'secret'], 'the --openai-* options need --engine openai', id='key'),
        pytest.param(
            ['--engine', 'openai', '--openai-url', 'http://localhost/v1', '--no-tesseract-download'],
            'the --tesseract-* options need --engine tesseract',
            id='openai with a tesseract option',
        ),
        pytest.param(
            ['--engine', 'openai', '--openai-url', 'localhost:8080'], 'is not an http or https URL', id='no scheme'
        ),
        pytest.param(
            ['--engine', 'openai', '--openai-url', 'http://localhost/v1', '--openai-request-per', 'word'],
            "'word' is not one of 'line', 'cue'",
            id='request per word',
        ),
    ],
)
def test_the_options_of_the_other_engine_are_rejected(media_dir: typing.Any, args: list[str], message: str) -> None:
    result = rip(*args, str(media_dir))

    assert result.exit_code == 2
    assert message in result.output


def test_doctor_shows_the_openai_url_and_model() -> None:
    result = CliRunner().invoke(pgsrip, ['doctor', '--openai-url', 'http://127.0.0.1:8080/v1'])

    lines = result.output.splitlines()
    assert any(line.startswith('openai url') and line.endswith('http://127.0.0.1:8080/v1') for line in lines)
    assert any(line.startswith('openai model') and line.endswith('not set') for line in lines)


def test_a_wrong_request_per_is_an_error() -> None:
    with pytest.raises(OpenAiError, match='request_per is word, not one of line, cue'):
        OpenAiEngine('http://localhost/v1', request_per='word')
