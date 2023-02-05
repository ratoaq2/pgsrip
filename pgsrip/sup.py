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
        temp_folder = self.media_path.create_temp_folder()
        pgs = Pgs(self.media_path, options=options, data_reader=self.media_path.get_data, temp_folder=temp_folder)
        if pgs.matches(options):
            yield pgs
