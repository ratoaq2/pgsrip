from __future__ import annotations

import logging
import os
import shutil
import tempfile
import typing
from datetime import timedelta
from types import TracebackType

from babelfish import Language

from pgsrip.media_path import MediaPath
from pgsrip.options import Options
from pgsrip.sources import EXTENSIONS, SOURCES
from pgsrip.sources.base import Source, SourceError, Track

if typing.TYPE_CHECKING:
    from pgsrip.writers.base import Writer

logger = logging.getLogger(__name__)


class Workspace:
    """The temporary directory of a run: one directory for each subtitle. Use it in a `with` block.

    With `keep`, the files stay at the end of the block, for debug.
    """

    def __init__(self, keep: bool = False):
        self.keep = keep
        self._dir: str | None = None

    @property
    def dir(self) -> str:
        """The temporary directory of the run. It is made on first use."""
        if self._dir is None:
            self._dir = tempfile.mkdtemp(prefix='pgsrip-')
            logger.debug('Using temporary directory %s', self._dir)
        return self._dir

    def __enter__(self) -> Workspace:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        if self._dir is None:
            return

        if self.keep:
            logger.info('Keeping temporary files in %s', self._dir)
        else:
            logger.debug('Removing temporary files in %s', self._dir)
            shutil.rmtree(self._dir)
        self._dir = None


class Subtitle:
    """One selected track to rip: where its data comes from, and where its files go.

    Use it in a `with` block for one rip. At the end of the block, its temporary directory is removed.
    """

    def __init__(
        self,
        track: Track,
        source_path: MediaPath,
        output_base: MediaPath,
        extraction: Extraction,
        workspace: Workspace | None = None,
    ):
        self.track = track
        #: the media file, to point a bug report at
        self.source_path = source_path
        #: the base of the output paths: the media path with the language and the flags of the track
        self.output_base = output_base
        #: the extraction that this subtitle shares with the other selected subtitles of its media
        self.extraction = extraction
        self.workspace = workspace
        self._temp_dir: str | None = None

    @property
    def language(self) -> Language:
        return self.track.language

    @property
    def temp_dir(self) -> str:
        """The directory for the extracted track and the debug files, in the directory of the workspace.

        It is made on first use. The unique suffix prevents a clash between 2 files with the same name.
        """
        if self._temp_dir is None:
            name = os.path.splitext(os.path.basename(str(self.output_base)))[0]
            workspace_dir = self.workspace.dir if self.workspace is not None else None
            self._temp_dir = tempfile.mkdtemp(prefix=f'{name}-', dir=workspace_dir)
            logger.debug('%s is using temporary directory %s', self, self._temp_dir)
        return self._temp_dir

    @property
    def debug_dir(self) -> str | None:
        """The directory for the debug files, or None when the workspace does not keep the files."""
        return self.temp_dir if self.workspace is not None and self.workspace.keep else None

    def read(self) -> bytes:
        """The PGS data of the track."""
        return self.extraction.read(self)

    def output_path(self, writer: Writer) -> MediaPath:
        return self.output_base.replace(extension=writer.extension)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self}]>'

    def __str__(self) -> str:
        # a track of a container: the file name, the track id, and the language
        if str(self.source_path) != str(self.output_base):
            return f'{self.output_base.replace(language=Language("und"))} [{self.track.id}:{self.language}]'

        return str(self.output_base)

    def __enter__(self) -> Subtitle:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        # the next read of another subtitle does not extract this one
        self.extraction.release(self)
        if self._temp_dir is None or (self.workspace is not None and self.workspace.keep):
            return

        logger.debug('Removing temporary files in %s', self._temp_dir)
        shutil.rmtree(self._temp_dir)
        self._temp_dir = None


class Extraction:
    """One call of the source for all the selected tracks of a media, on the first read.

    The bytes stay on disk until each track reads them. When the call fails, each track gets the same error.
    """

    def __init__(self, source: Source, path: MediaPath):
        self.source = source
        self.path = path
        #: the subtitles that the next call extracts, if they are not on disk
        self.pending: list[Subtitle] = []
        #: the .sup path of each extracted track, by track id
        self._paths: dict[int, str] = {}
        self._error: Exception | None = None

    def extract(self, subtitle: Subtitle) -> None:
        """Extract this subtitle, and the pending subtitles that are not on disk."""
        targets: dict[int, str] = {}
        for target in dict.fromkeys([subtitle, *self.pending]):
            if target.track.id not in self._paths:
                targets[target.track.id] = os.path.join(target.temp_dir, f'{target.track.id}.{target.language}.sup')

        logger.debug('Extracting %d tracks from %s', len(targets), self.path)
        self._paths.update(self.source.extract(str(self.path), targets))

    def release(self, subtitle: Subtitle) -> None:
        """Nothing reads this subtitle now: do not extract it with the others, and forget its file."""
        if subtitle in self.pending:
            self.pending.remove(subtitle)
        self._paths.pop(subtitle.track.id, None)

    def read(self, subtitle: Subtitle) -> bytes:
        if self._error is None and subtitle.track.id not in self._paths:
            try:
                self.extract(subtitle)
            except Exception as e:
                self._error = e

        if self._error is not None:
            raise self._error

        with open(self._paths[subtitle.track.id], mode='rb') as f:
            return f.read()


class Media:
    def __init__(self, path: str, source: Source | None = None):
        self.path = MediaPath(path)
        if source is None:
            self.source, self.tracks = self.find_source(path)
        else:
            self.source, self.tracks = source, source.probe(path)
        self.languages = {t.language for t in self.tracks if not t.disabled}

    @staticmethod
    def find_source(path: str) -> tuple[Source, list[Track]]:
        """The first built-in source that reads the file, and the tracks that it finds."""
        extension = os.path.splitext(path.lower())[1]
        source_types = [s for s in SOURCES if extension in s.extensions]
        if not source_types:
            raise SourceError(f'unsupported extension, expected one of {", ".join(sorted(EXTENSIONS))}')

        for source_type in source_types:
            source = source_type()
            try:
                return source, source.probe(path)
            except FileNotFoundError as e:
                logger.debug('Cannot use %s for %s: %s', source_type.__name__, path, e)

        raise SourceError(source_types[0].install_hint)

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{self.path}]>'

    def __str__(self) -> str:
        return str(self.path)

    @property
    def age(self) -> timedelta:
        return self.path.age

    def filter_reason(self, options: Options) -> str | None:
        """Return why this media does not match the options, or None when it does."""
        if options.age and self.age > options.age:
            return f'file is older than {options.age}'

        if options.languages and not self.languages.intersection(options.languages):
            available = ', '.join(sorted(str(lang) for lang in self.languages if lang)) or 'none'
            return f'no track for the selected languages (available: {available})'

        return None

    def subtitles(self, options: Options, workspace: Workspace | None = None) -> list[Subtitle]:
        """The tracks that the options select. It does not look at the output files: see `pgsrip.api.pending`."""
        candidates: list[Track] = []
        for t in self.tracks:
            if t.disabled:
                continue
            if options.languages and t.language not in options.languages:
                logger.debug('Skipping track %s:%s in %s: language not selected', t.id, t.language, self)
                continue
            candidates.append(t)

        candidates.sort(key=lambda x: x.id)

        # 2 tracks with the same language and the same file name tokens write the same file.
        # The groups use all the candidates, not the selected tracks: the `.track<n>` suffix of a track is
        # the same with and without `all_tracks`, `with_flags` and `without_flags`.
        groups: dict[tuple[Language, tuple[str, ...]], list[Track]] = {}
        for t in candidates:
            groups.setdefault((t.language, t.flags.tokens()), []).append(t)
        # the first track of a group (lowest id) has no suffix. The next tracks get 2, 3, ...
        suffixes = {t.id: i + 1 for members in groups.values() for i, t in enumerate(members) if i > 0}

        selected: set[tuple[Language, tuple[str, ...] | None]] = set()
        subtitles: list[Subtitle] = []
        extraction = Extraction(self.source, self.path)
        for t in candidates:
            key = (t.language, None if options.one_per_language else t.flags.tokens())
            if not options.all_tracks and key in selected:
                logger.debug('Skipping track %s:%s in %s: duplicate of a selected track', t.id, t.language, self)
                continue
            if not t.flags.matches(options.with_flags, options.without_flags):
                logger.debug('Skipping track %s:%s in %s: flags not selected', t.id, t.language, self)
                continue

            logger.debug('Selecting track %s:%s in %s', t.id, t.language, self)
            subtitles.append(
                Subtitle(
                    t,
                    self.path,
                    self.path.replace(language=t.language, flags=t.flags, track_number=suffixes.get(t.id)),
                    extraction,
                    workspace,
                )
            )
            selected.add(key)

        extraction.pending.extend(subtitles)
        return subtitles
