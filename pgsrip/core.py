# -*- coding: utf-8 -*-
import logging
import os
from typing import List

from .media import Media, Pgs
from .mkv import Mkv
from .options import Options
from .ripper import PgsToSrtRipper
from .sup import Sup


logger = logging.getLogger(__name__)

MEDIAS = {
    '.sup': Sup,
    '.mkv': Mkv,
    '.mks': Mkv
}
EXTENSIONS = tuple(MEDIAS.keys())


def scan_path(path: str, collected: List[Media], filtered_out: List[str], discarded: List[str], options: Options):
    if not os.path.exists(path):
        logger.debug(f'Non existent path {path} discarded')
        discarded.append(path)

    elif os.path.isfile(path):
        if path.lower().endswith(EXTENSIONS):
            if path.lower().endswith(EXTENSIONS):
                # noinspection PyBroadException
                try:
                    ext = os.path.splitext(path.lower())[1]
                    media = MEDIAS[ext](path)
                    if media.matches(options):
                        collected.append(media)
                    else:
                        filtered_out.append(path)
                except Exception as exc:
                    logger.debug(f'Path {path} discarded: <{type(exc).__name__}> {exc}')
                    discarded.append(path)

    elif os.path.isdir(path):
        for dir_path, dir_names, file_names in os.walk(path):
            for filename in file_names:
                file_path = os.path.join(dir_path, filename)
                scan_path(file_path, collected, filtered_out, discarded, options)


def rip(media: Media, options: Options):
    counter = 0
    for pgs in media.get_pgs_medias(options):
        counter += rip_pgs(pgs, options)

    return counter


def rip_pgs(pgs: Pgs, options: Options):
    # noinspection PyBroadException
    try:
        if not pgs.matches(options):
            return False

        rules = options.config.select_rules(tags=options.tags, languages={pgs.language})
        srt = PgsToSrtRipper(pgs, options).rip(lambda t: rules.apply(t, '')[0])
        srt.save(encoding=options.encoding)
        return True
    except Exception as e:
        logger.warning(f'Error while trying to rip {pgs.media_path}: <{type(e).__name__}> [{e}]',
                       exc_info=logger.isEnabledFor(logging.DEBUG))
    finally:
        pgs.deallocate()

    return False
