import json
import typing
from subprocess import CalledProcessError, check_output

from pgsrip.diagnostics import Check, check_executable
from pgsrip.sources.base import Source, SourceError, Track

MKVTOOLNIX_EXECUTABLES = ('mkvmerge', 'mkvextract')
MKVTOOLNIX_HINT = 'Install MKVToolNix: https://mkvtoolnix.download/downloads.html'


def run(args: list[str], action: str) -> bytes:
    """Run a MKVToolNix program. A missing program raises FileNotFoundError."""
    try:
        return check_output(args)
    except CalledProcessError as e:
        raise SourceError(f'{args[0]} could not {action} (exit code {e.returncode})') from e


def track_from_json(track: dict[str, typing.Any]) -> Track:
    """Map a track of `mkvmerge -i -F json` to a Track."""
    properties = track.get('properties', {})
    # mkvmerge always reports language_ietf, but it may not parse (e.g. a malformed tag); fall back to
    # the alpha3 language (639-2/B: fre, ger, chi, dut, gre, rum, may, cze) before giving up to und.
    return Track.create(
        track['id'],
        name=properties.get('track_name'),
        language_tags=[properties.get('language_ietf'), properties.get('language')],
        container_flags={
            'disabled': not properties.get('enabled_track'),
            'default': properties.get('default_track'),
            'original': properties.get('flag_original'),
            'forced': properties.get('forced_track'),
            'hearing_impaired': properties.get('flag_hearing_impaired'),
            'commentary': properties.get('flag_commentary'),
            'descriptive': properties.get('flag_text_descriptions'),
        },
    )


class MkvToolNixSource(Source):
    install_hint: typing.ClassVar[str] = f'mkvmerge not found. {MKVTOOLNIX_HINT}'
    extensions: typing.ClassVar[tuple[str, ...]] = ('.mkv', '.mks')

    @classmethod
    def check(cls) -> list[Check]:
        return [check_executable(name, MKVTOOLNIX_HINT) for name in MKVTOOLNIX_EXECUTABLES]

    def probe(self, path: str) -> list[Track]:
        metadata = json.loads(run(['mkvmerge', '-i', '-F', 'json', path], 'read the file'))
        return [
            track_from_json(t)
            for t in metadata.get('tracks', [])
            if t['type'] == 'subtitles' and t['codec'] == 'HDMV PGS'
        ]

    def extract(self, path: str, targets: dict[int, str]) -> dict[int, str]:
        run(['mkvextract', path, 'tracks', *(f'{id}:{target}' for id, target in targets.items())], 'extract the tracks')
        return targets
