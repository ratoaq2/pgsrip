from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import timedelta
from types import TracebackType

from babelfish import Language

from pgsrip.engines.auto import AutoEngine
from pgsrip.engines.base import OcrEngine
from pgsrip.postprocessors.base import PostProcessor
from pgsrip.postprocessors.cleanit import CleanitPostProcessor
from pgsrip.writers.base import Writer
from pgsrip.writers.srt import SrtWriter

logger = logging.getLogger(__name__)


class Options:
    """The options of one run. Use it in a `with` block to remove the temporary folder of the run at the end."""

    def __init__(
        self,
        languages: set[Language] | None = None,
        encoding: str | None = None,
        overwrite: bool = False,
        one_per_lang: bool = True,
        one_per_language: bool = False,
        include_flags: frozenset[str] = frozenset(),
        exclude_flags: frozenset[str] = frozenset(),
        keep_temp_files: bool = False,
        engines: list[OcrEngine] | None = None,
        post_processors: list[PostProcessor] | None = None,
        age: timedelta | None = None,
        output_age: timedelta | None = None,
        writers: list[Writer] | None = None,
    ):
        self.languages = languages or set()
        self.encoding = encoding
        self.overwrite = overwrite
        self.one_per_lang = one_per_lang
        self.one_per_language = one_per_language
        self.include_flags = include_flags
        self.exclude_flags = exclude_flags
        self.keep_temp_files = keep_temp_files
        # a chain: each engine reads the items that the engines before it left unread
        self.engines = engines or [AutoEngine()]
        # a chain: each post-processor changes the cues of the one before it. An empty list changes nothing.
        self.post_processors: list[PostProcessor] = (
            [CleanitPostProcessor()] if post_processors is None else post_processors
        )
        self.age = age
        self.output_age = output_age
        # each writer writes one file for each track
        self.writers = writers or [SrtWriter()]
        self._temp_folder: str | None = None

    @property
    def temp_folder(self) -> str:
        """The temporary folder of the run: it holds one folder for each track. It is made on first use."""
        if self._temp_folder is None:
            self._temp_folder = tempfile.mkdtemp(prefix='pgsrip-')
            logger.debug('Using temporary folder %s', self._temp_folder)
        return self._temp_folder

    def __enter__(self) -> Options:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        if self._temp_folder is None:
            return

        if self.keep_temp_files:
            logger.info('Keeping temporary files in %s', self._temp_folder)
        else:
            logger.debug('Removing temporary files in %s', self._temp_folder)
            shutil.rmtree(self._temp_folder)
        self._temp_folder = None

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self) -> str:
        return (
            f'languages:{self.languages}, '
            f'encoding:{self.encoding}, '
            f'overwrite:{self.overwrite}, '
            f'one_per_lang:{self.one_per_lang}, '
            f'one_per_language:{self.one_per_language}, '
            f'include_flags:{self.include_flags}, '
            f'exclude_flags:{self.exclude_flags}, '
            f'keep_temp_files:{self.keep_temp_files}, '
            f'engines:{self.engines!r}, '
            f'post_processors:{self.post_processors!r}, '
            f'age:{self.age}, '
            f'output_age:{self.output_age}, '
            f'writers:{self.writers!r}'
        )
