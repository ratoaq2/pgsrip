"""The library API: find the media files, select their subtitles, and rip them."""

from __future__ import annotations

import functools
import json
import logging
import os
import typing
from collections.abc import Sequence

from pgsrip.cue import Cue
from pgsrip.engines.auto import AutoEngine
from pgsrip.engines.base import OcrEngine
from pgsrip.engines.chain import read_cues
from pgsrip.engines.rapidocr import RapidOcrEngine
from pgsrip.engines.tesseract import TesseractEngine
from pgsrip.formats.pgs import CorruptDataError, DisplaySet, Item, read_display_sets, read_items
from pgsrip.media import Media, Subtitle
from pgsrip.options import Options
from pgsrip.postprocessors.base import PostProcessor
from pgsrip.postprocessors.cleanit import CleanitPostProcessor
from pgsrip.sources import EXTENSIONS
from pgsrip.sources.base import SourceError
from pgsrip.writers.base import Writer
from pgsrip.writers.srt import SrtWriter

logger = logging.getLogger(__name__)


class Skipped(typing.NamedTuple):
    """A path that pgsrip does not rip, and the reason why."""

    path: str
    reason: str


class ScanResult(typing.NamedTuple):
    #: the media files that match the options
    media: list[Media]
    #: the media files that do not match the options
    filtered_out: list[Skipped]
    #: the paths that are not media files, or that no source can read
    ignored: list[Skipped]


def scan(path: str, options: Options | None = None) -> ScanResult:
    """The media files of a file or a directory. The directories are read recursively."""
    result = ScanResult([], [], [])
    _scan(path, options or Options(), result)
    return result


def _scan(path: str, options: Options, result: ScanResult) -> None:
    def ignore(reason: str) -> None:
        logger.debug('Path %s ignored: %s', path, reason)
        result.ignored.append(Skipped(path, reason))

    if not os.path.exists(path):
        ignore('path does not exist')

    elif os.path.isfile(path):
        try:
            media = Media(path)
        except SourceError as e:
            ignore(str(e))
            return
        except Exception as e:
            ignore(f'<{type(e).__name__}> {e}')
            return

        reason = media.filter_reason(options)
        if reason is None:
            result.media.append(media)
        else:
            logger.debug('Path %s filtered out: %s', path, reason)
            result.filtered_out.append(Skipped(path, reason))

    elif os.path.isdir(path):
        for dir_path, _dir_names, file_names in os.walk(path):
            for filename in file_names:
                file_path = os.path.join(dir_path, filename)
                if file_path.lower().endswith(EXTENSIONS):
                    _scan(file_path, options, result)

    else:
        ignore('path is not a file nor a directory')


@functools.cache
def default_engines() -> tuple[OcrEngine, ...]:
    return (AutoEngine(TesseractEngine(), RapidOcrEngine()),)


@functools.cache
def default_post_processors() -> tuple[PostProcessor, ...]:
    return (CleanitPostProcessor(),)


def engines(options: Options) -> Sequence[OcrEngine]:
    """The OCR engines of the options, else auto. The default engine is made one time, on first use."""
    return default_engines() if options.engines is None else options.engines


def post_processors(options: Options) -> Sequence[PostProcessor]:
    """The post-processors of the options, else cleanit."""
    return default_post_processors() if options.post_processors is None else options.post_processors


def writers(options: Options) -> Sequence[Writer]:
    """The writers of the options, else srt."""
    return (SrtWriter(),) if options.writers is None else options.writers


def pending_writers(subtitle: Subtitle, options: Options) -> list[Writer]:
    """The writers whose file must be written. An existing file is written again only with `force`."""
    kept = []
    for writer in writers(options):
        path = subtitle.output_path(writer)
        if not path.exists():
            kept.append(writer)
        elif not options.force:
            logger.debug('Skipping %s: %s exists', subtitle, path)
        elif options.output_age and path.age < options.output_age:
            logger.debug('Skipping %s: %s is too new', subtitle, path)
        else:
            kept.append(writer)

    return kept


def pending(subtitles: list[Subtitle], options: Options | None = None) -> list[Subtitle]:
    """The subtitles with a file to write. The others are not extracted."""
    options = options or Options()
    kept = []
    for subtitle in subtitles:
        if pending_writers(subtitle, options):
            kept.append(subtitle)
        else:
            subtitle.extraction.release(subtitle)

    return kept


def prepare(
    subtitles: list[Subtitle], options: Options | None = None, reporter: typing.Callable[[str], None] | None = None
) -> None:
    """Get the OCR engines ready for the languages of the subtitles. Call it before `rip`.

    Raise OcrError when an engine cannot rip at all. Tell the user through reporter, also when an engine cannot
    read a language.
    """
    languages = list(dict.fromkeys(subtitle.language for subtitle in subtitles))
    if not languages:
        return

    options = options or Options()
    for engine in engines(options):
        engine.prepare(languages, reporter)

    for engine in engines(options):
        unsupported = sorted(str(language) for language in languages if engine.engine_for(language) is None)
        if unsupported and reporter is not None:
            reporter(f'{type(engine).__name__} cannot read {", ".join(unsupported)}')


def rip(subtitle: Subtitle, options: Options | None = None) -> bool:
    """Rip one subtitle into the file of each pending writer. Return False when no file is pending.

    Raise the error that stops the rip. The temporary directory of the subtitle is removed at the end.
    """
    options = options or Options()
    with subtitle:
        to_write = pending_writers(subtitle, options)
        if not to_write:
            return False

        items = decode(subtitle)
        if not items:
            # a track with no image is corrupted: do not write an empty subtitle file as if it was ripped
            raise CorruptDataError(f'No subtitle image in {subtitle}')

        cues, seconds = read_cues(items, subtitle.language, engines(options), subtitle.debug_dir)
        if subtitle.debug_dir:
            dump_cues(subtitle.debug_dir, 'ocr.json', cues, seconds)
        for post_processor in post_processors(options):
            cues = post_processor.process(cues, subtitle.track)
        if subtitle.debug_dir:
            dump_cues(subtitle.debug_dir, 'cues.json', cues, seconds)

        for writer in to_write:
            writer.write(str(subtitle.output_path(writer)), cues, subtitle.track, options.encoding)
        return True


def decode(subtitle: Subtitle) -> list[Item]:
    """Read and decode the data of the subtitle. With a debug directory, write the display sets there."""
    logger.info('Decoding %s', subtitle)
    display_sets = list(read_display_sets(subtitle.read(), str(subtitle)))
    if subtitle.debug_dir:
        dump_display_sets(subtitle.debug_dir, display_sets)

    return read_items(display_sets, str(subtitle))


def dump_display_sets(debug_dir: str, display_sets: list[DisplaySet]) -> None:
    """Write the display sets as text and as JSON, for debug."""
    with open(os.path.join(debug_dir, 'display-sets.txt'), mode='w', encoding='utf8') as f:
        f.write('\n'.join(str(ds) for ds in display_sets))
    with open(os.path.join(debug_dir, 'display-sets.json'), mode='w', encoding='utf8') as f:
        json.dump([ds.to_json() for ds in display_sets], f, indent=2, ensure_ascii=False, default=str)


def dump_cues(debug_dir: str, name: str, cues: list[Cue], seconds: dict[str, float]) -> None:
    """Write the cues and the time of each OCR engine, for debug and benchmarks."""
    with open(os.path.join(debug_dir, name), mode='w', encoding='utf8') as f:
        json.dump({'seconds': seconds, 'cues': [cue.to_json() for cue in cues]}, f, indent=2, ensure_ascii=False)
