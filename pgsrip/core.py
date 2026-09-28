from __future__ import annotations

import json
import logging
import os
import typing
from subprocess import CalledProcessError

from pgsrip.media import Pgs
from pgsrip.options import Options
from pgsrip.ripper import Cue, PgsRipper
from pgsrip.sources import EXTENSIONS
from pgsrip.sources.base import Media

logger = logging.getLogger(__name__)

# called with the subtitle that could not be ripped and the error that stopped it
ErrorHandler = typing.Callable[[Pgs, Exception], None]


class ScannedPath(str):
    """A path that was not collected, and the reason why.

    It is a ``str`` subclass on purpose: every consumer that prints or joins the scan results
    keeps working, and the reason is available to the ones that want to show it.
    """

    reason: str

    def __new__(cls, path: str, reason: str) -> ScannedPath:
        scanned_path = super().__new__(cls, path)
        scanned_path.reason = reason
        return scanned_path


def get_reason(path: str) -> str | None:
    """Return why a path was filtered out or ignored, when it is known."""
    return getattr(path, 'reason', None)


def create_media(path: str) -> Media | str:
    """Create the media for the given path, or return the reason why it cannot be created."""
    try:
        return Media(path)
    except FileNotFoundError as exc:
        return str(exc)
    except CalledProcessError as exc:
        return f'{exc.cmd[0]} could not read the file (exit code {exc.returncode})'
    except Exception as exc:
        return f'<{type(exc).__name__}> {exc}'


def scan_path(
    path: str, collected: list[Media], filtered_out: list[str], discarded: list[str], options: Options
) -> None:
    def discard(reason: str) -> None:
        logger.debug('Path %s discarded: %s', path, reason)
        discarded.append(ScannedPath(path, reason))

    if not os.path.exists(path):
        discard('path does not exist')

    elif os.path.isfile(path):
        if not path.lower().endswith(EXTENSIONS):
            discard(f'unsupported extension, expected one of {", ".join(sorted(EXTENSIONS))}')
            return

        media = create_media(path)
        if isinstance(media, str):
            discard(media)
            return

        reason = media.filter_reason(options)
        if reason is None:
            collected.append(media)
        else:
            logger.debug('Path %s filtered out: %s', path, reason)
            filtered_out.append(ScannedPath(path, reason))

    elif os.path.isdir(path):
        for dir_path, _dir_names, file_names in os.walk(path):
            for filename in file_names:
                file_path = os.path.join(dir_path, filename)
                if file_path.lower().endswith(EXTENSIONS):
                    scan_path(file_path, collected, filtered_out, discarded, options)

    else:
        discard('path is not a file nor a directory')


def rip(media: Media, options: Options, on_error: ErrorHandler | None = None) -> int:
    counter = 0
    for pgs in media.get_pgs_medias(options):
        counter += rip_pgs(pgs, options, on_error)

    return counter


def rip_pgs(pgs: Pgs, options: Options, on_error: ErrorHandler | None = None) -> bool:
    """Rip a single PGS subtitle, reporting the error to on_error when it cannot be ripped."""
    # noinspection PyBroadException
    try:
        with pgs as p:
            writers = p.pending_writers(options)
            if not writers:
                return False

            ripper = PgsRipper(p, options)
            cues = ripper.rip()
            if options.keep_temp_files:
                dump_cues(p, 'ocr.json', cues, ripper.seconds)
            for post_processor in options.post_processors:
                cues = post_processor.process(p, cues)
            if options.keep_temp_files:
                dump_cues(p, 'cues.json', cues, ripper.seconds)

            for writer in writers:
                writer.write(str(p.output_path(writer)), p, cues, options.encoding)
            return True
    except Exception as e:
        logger.warning(
            'Error while trying to rip %s: <%s> [%s]',
            pgs.media_path,
            type(e).__name__,
            e,
            exc_info=logger.isEnabledFor(logging.DEBUG),
        )
        if on_error:
            on_error(pgs, e)

    return False


def dump_cues(pgs: Pgs, name: str, cues: list[Cue], seconds: dict[str, float]) -> None:
    """Write the cues and the time of each OCR engine in the temporary folder, for debug and benchmarks."""
    with open(os.path.join(pgs.temp_folder, name), mode='w', encoding='utf8') as f:
        json.dump({'seconds': seconds, 'cues': [cue.to_json() for cue in cues]}, f, indent=2, ensure_ascii=False)
