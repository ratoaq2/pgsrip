"""OCR with a vision model behind an OpenAI-compatible API, e.g. llama.cpp with GLM-OCR (see docs/ocr_batching.md).

The API is the OpenAI Chat Completions API: `POST /chat/completions` with an `image_url` part.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import typing
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import click
import cv2

from pgsrip.diagnostics import Check
from pgsrip.engines.base import OcrEngine, OcrEngineFactory, OcrError, Reading
from pgsrip.plugin import PluginOption
from pgsrip.utils import default_workers, split_lines

if typing.TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt
    from babelfish import Language

    from pgsrip.formats.pgs import Item

logger = logging.getLogger(__name__)

API_KEY_ENV = 'PGSRIP_OPENAI_API_KEY'
#: seconds for one request. A CPU server with several slots can take about 1 minute for one cue.
DEFAULT_TIMEOUT = 300
#: a subtitle is a few lines: a low limit stops a model that repeats itself.
DEFAULT_MAX_TOKENS = 512
#: OCR has one right answer: no sampling.
DEFAULT_TEMPERATURE = 0.0
#: white margin around the ink, so that the model does not see text that touches the image edge.
DEFAULT_BORDER = 20
#: length of an answer that goes into an error message.
MAX_REPORTED_ANSWER = 200
#: what one request reads: one text line of a subtitle image, or the whole image
REQUESTS_PER = ('line', 'cue')
#: a small OCR model joins the lines of a wrapped sentence: one request for each line keeps the line breaks
DEFAULT_REQUEST_PER = 'line'
#: the placeholder of the prompt that pgsrip replaces with the language name of the track
LANGUAGE = '{language}'
DEFAULT_PROMPT = (
    'Transcribe the text of this subtitle image. Reply with the text only. Keep the line breaks. '
    f'The language is {LANGUAGE}.'
)


class OpenAiError(OcrError):
    """Raised when the OpenAI-compatible API cannot read a subtitle image."""


class JsonObjectParamType(click.ParamType[dict[str, typing.Any], str | dict[str, typing.Any]]):
    """A JSON object on the command line, or a mapping in a configuration file."""

    name = 'json'

    def convert(
        self, value: str | dict[str, typing.Any], param: click.Parameter | None, ctx: click.Context | None
    ) -> dict[str, typing.Any]:
        if isinstance(value, dict):
            return value
        try:
            data = json.loads(value)
        except ValueError as e:
            self.fail(f'{click.style(value, bold=True)} is not valid JSON: {e}')
        if not isinstance(data, dict):
            self.fail(f'{click.style(value, bold=True)} is not a JSON object')

        return data


class OpenAiEngine(OcrEngine, OcrEngineFactory):
    """Sends each text line of each item in its own request, several items in parallel.

    One request for each line is not slow here: the server keeps the model loaded, and the time grows with
    the size of the image (the image prefill is most of the time), not with the number of requests.
    """

    options: typing.ClassVar[tuple[PluginOption, ...]] = (
        PluginOption('url', required=True, help='Base URL of an OpenAI-compatible API, e.g. http://127.0.0.1:8080/v1.'),
        PluginOption('model', help='Model name to send to the API, when the server needs one.'),
        PluginOption('api_key', envvar=API_KEY_ENV, help='API key of the OpenAI-compatible API.'),
        PluginOption(
            'timeout',
            click.FloatRange(min=0, min_open=True),
            default=DEFAULT_TIMEOUT,
            help='Seconds to wait for the answer to one request.',
        ),
        PluginOption(
            'workers',
            click.IntRange(1, 50),
            default=None,
            help='Number of requests that run in parallel. Set it to the parallel slots of the server. Default: -w.',
        ),
        PluginOption(
            'prompt',
            default=DEFAULT_PROMPT,
            help=f'Text that goes with each image. pgsrip replaces {LANGUAGE} with the language of the track.',
        ),
        PluginOption(
            'max_tokens',
            click.IntRange(min=1),
            default=DEFAULT_MAX_TOKENS,
            help='Maximum number of tokens of one answer.',
        ),
        PluginOption(
            'temperature',
            click.FloatRange(0, 2),
            default=DEFAULT_TEMPERATURE,
            help='Sampling temperature of the model.',
        ),
        PluginOption(
            'extra_body',
            JsonObjectParamType(),
            help='JSON object to add to each request, for the fields of one server. '
            'E.g. {"chat_template_kwargs": {"enable_thinking": false}} for llama.cpp or vLLM.',
        ),
        PluginOption(
            'border',
            click.IntRange(0, 200),
            default=DEFAULT_BORDER,
            help='White border around each image, in pixels.',
        ),
        PluginOption(
            'request_per',
            click.Choice(REQUESTS_PER),
            default=DEFAULT_REQUEST_PER,
            help='line: one request for each text line of a subtitle image, to keep the line breaks. '
            'cue: one request for each subtitle image.',
        ),
    )

    @classmethod
    def from_settings(cls, settings: dict[str, typing.Any]) -> OpenAiEngine:
        try:
            return cls(
                settings['url'],
                model=settings['model'],
                api_key=settings['api_key'],
                workers=settings['workers'],
                timeout=settings['timeout'],
                request_per=settings['request_per'],
                prompt=settings['prompt'],
                max_tokens=settings['max_tokens'],
                temperature=settings['temperature'],
                extra_body=settings['extra_body'],
                border=settings['border'],
            )
        except OpenAiError as e:
            raise ValueError(str(e)) from e

    @classmethod
    def check(cls, settings: dict[str, typing.Any]) -> list[Check]:
        """The URL and the model, for `pgsrip doctor`. No request: the API can be down when it is not used."""
        return [
            Check('openai url', settings.get('url') or 'not set'),
            Check('openai model', settings.get('model') or 'not set'),
        ]

    def __init__(
        self,
        url: str,
        model: str | None = None,
        api_key: str | None = None,
        workers: int | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        request_per: str = DEFAULT_REQUEST_PER,
        prompt: str = DEFAULT_PROMPT,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        extra_body: dict[str, typing.Any] | None = None,
        border: int = DEFAULT_BORDER,
    ):
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in ('http', 'https') or not parts.netloc:
            raise OpenAiError(f'{url} is not an http or https URL')

        self.url = url.rstrip('/')
        self.model = model
        self.api_key = api_key
        self.workers = workers or default_workers()
        self.timeout = timeout
        if request_per not in REQUESTS_PER:
            raise OpenAiError(f'request_per is {request_per}, not one of {", ".join(REQUESTS_PER)}')
        self.request_per = request_per
        self.prompt = prompt
        self.max_tokens = max_tokens
        self.temperature = temperature
        #: the fields that only some servers know, e.g. to turn off the thinking of a model
        self.extra_body = extra_body or {}
        self.border = border

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self) -> str:
        return (
            f'url:{self.url}, '
            f'model:{self.model}, '
            f'api_key:{"set" if self.api_key else None}, '
            f'workers:{self.workers}, '
            f'timeout:{self.timeout}, '
            f'request_per:{self.request_per}, '
            f'max_tokens:{self.max_tokens}, '
            f'temperature:{self.temperature}, '
            f'extra_body:{self.extra_body}, '
            f'border:{self.border}'
        )

    def prepare(
        self, languages: typing.Iterable[Language], reporter: typing.Callable[[str], None] | None = None
    ) -> None:
        """Make sure that the API answers, so that a wrong URL stops the rip before it starts."""
        self.request('/models')

    def supports(self, language: Language) -> bool:
        return True

    def recognize(self, items: list[Item], language: Language, debug_dir: str | None) -> list[Reading]:
        if debug_dir:
            for item in items:
                for index, line in enumerate(self.lines(item.bitmap)):
                    cv2.imwrite(os.path.join(debug_dir, f'openai-{item.index}-{index}.png'), self.image(line))

        with ThreadPoolExecutor(self.workers) as pool:
            futures = [pool.submit(self.read, item, language) for item in items]
            try:
                return [Reading(future.result() or None) for future in futures]
            except BaseException:
                # do not send the remaining requests to a server that failed
                pool.shutdown(cancel_futures=True)
                raise

    def image(self, bitmap: npt.NDArray[np.uint8]) -> typing.Any:
        border = self.border
        return cv2.copyMakeBorder(bitmap, border, border, border, border, cv2.BORDER_CONSTANT, value=255)

    def lines(self, bitmap: npt.NDArray[np.uint8]) -> list[npt.NDArray[np.uint8]]:
        return split_lines(bitmap) if self.request_per == 'line' else [bitmap]

    def read(self, item: Item, language: Language) -> str:
        texts = [self.read_line(line, language) for line in self.lines(item.bitmap)]
        return '\n'.join(text for text in texts if text)

    def read_line(self, bitmap: npt.NDArray[np.uint8], language: Language) -> str:
        _, png = cv2.imencode('.png', self.image(bitmap))
        prompt = self.prompt.replace(LANGUAGE, language.name if language else 'unknown')
        body: dict[str, typing.Any] = {
            'messages': [
                {
                    'role': 'user',
                    'content': [
                        {
                            'type': 'image_url',
                            'image_url': {'url': f'data:image/png;base64,{base64.b64encode(png.tobytes()).decode()}'},
                        },
                        {'type': 'text', 'text': prompt},
                    ],
                }
            ],
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
        }
        if self.model:
            body['model'] = self.model
        body.update(self.extra_body)

        answer = self.request('/chat/completions', body)
        try:
            text = answer['choices'][0]['message']['content']
        except (KeyError, IndexError, TypeError) as e:
            raise OpenAiError(f'Unexpected answer from {self.url}: {str(answer)[:MAX_REPORTED_ANSWER]}') from e

        if not isinstance(text, str):
            raise OpenAiError(f'Unexpected answer from {self.url}: {str(answer)[:MAX_REPORTED_ANSWER]}')

        return text.strip()

    def request(self, path: str, body: dict[str, typing.Any] | None = None) -> typing.Any:
        """GET the path, or POST the body to it, and return the JSON answer."""
        url = f'{self.url}{path}'
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = f'Bearer {self.api_key}'

        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            answer = e.read(MAX_REPORTED_ANSWER).decode(errors='replace')
            raise OpenAiError(f'{url} answered HTTP {e.code}: {answer}') from e
        except urllib.error.URLError as e:
            raise OpenAiError(f'Cannot reach {url}: {e.reason}') from e
        except ValueError as e:
            raise OpenAiError(f'{url} did not answer with JSON: {e}') from e
        except OSError as e:
            raise OpenAiError(f'Cannot reach {url}: <{type(e).__name__}> {e}') from e
