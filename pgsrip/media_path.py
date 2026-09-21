from __future__ import annotations

import logging
import os
import re
import tempfile
from copy import copy
from datetime import datetime, timedelta

from babelfish import Language

from pgsrip.track_flags import TrackFlags

logger = logging.getLogger(__name__)

#: trailing `.track<n>` token: a 1-based ordinal (2, 3, ...) among colliding tracks, breaking a naming
#: collision; the first (lowest-id) track of a group stays unlabeled.
TRACK_ID_PATTERN = re.compile(r'^track(\d+)$')


class MediaPath:
    def __init__(self, path: str):
        file_part, extension = os.path.splitext(path)
        self.extension = extension[1:] if extension else None

        tokens = file_part.split('.')
        track_id: int | None = None
        if len(tokens) > 1:
            match = TRACK_ID_PATTERN.match(tokens[-1])
            if match:
                track_id = int(match.group(1))
                tokens = tokens[:-1]

        flags, tokens = TrackFlags.parse(tokens) if len(tokens) > 1 else (TrackFlags(), tokens)

        language = Language.fromcleanit(tokens[-1]) if len(tokens) > 1 else None
        if language:
            self.language = language
            self.base_path = '.'.join(tokens[:-1])
            self.flags = flags
            self.track_id = track_id
        else:
            self.language = Language.fromcleanit('und')
            self.base_path = file_part
            self.flags = TrackFlags()
            self.track_id = None

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} [{str(self)}]>'

    def __str__(self) -> str:
        parts = [self.base_path]
        if self.language:
            parts.append(str(self.language))
        parts.extend(self.flags.tokens())
        if self.track_id is not None:
            parts.append(f'track{self.track_id}')
        result = '.'.join(parts)
        return f'{result}.{self.extension}' if self.extension else result

    @property
    def m_age(self) -> timedelta:
        return datetime.utcnow() - datetime.utcfromtimestamp(os.path.getmtime(str(self)))

    def create_temp_folder(self) -> str:
        base_name = os.path.basename(str(self))
        temp_folder = tempfile.mkdtemp(prefix=base_name, suffix='.pgsrip')
        logger.debug('%s is using temporary folder %s', self, temp_folder)
        return temp_folder

    def get_data(self) -> bytes:
        with open(str(self), 'rb') as f:
            return f.read()

    def exists(self) -> bool:
        return os.path.exists(str(self))

    def translate(
        self,
        language: Language | None = None,
        extension: str | None = None,
        flags: TrackFlags | None = None,
        track_id: int | None = None,
    ) -> MediaPath:
        media_path = copy(self)
        if flags is not None:
            media_path.flags = flags
        if track_id is not None:
            media_path.track_id = track_id
        if language is not None:
            media_path.language = language
        if extension is not None:
            media_path.extension = extension
        return media_path
