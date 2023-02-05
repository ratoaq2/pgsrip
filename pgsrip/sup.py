import logging
from typing import Iterable

from pgsrip.media import Media, Pgs
from pgsrip.media_path import MediaPath
from pgsrip.options import Options

logger = logging.getLogger(__name__)


class Sup(Media):

    def __init__(self, path: str):
        media_path = MediaPath(path)
        super().__init__(media_path, languages={media_path.language})

    def get_pgs_medias(self, options: Options) -> Iterable[Pgs]:
        pgs = Pgs(self.media_path, data_reader=self.media_path.get_data)
        if pgs.matches(options):
            yield pgs
