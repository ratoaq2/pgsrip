"""Fabricate MKV media and tesseract OCR output for the end-to-end rip test suite.

No pytest imports: this module only builds bytes, dicts and argv lists, so it can be
driven from a plain script while debugging.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import subprocess
import typing

from babelfish import Language
from trakit.api import trakit  # noqa: F401  registers the `cleanit` babelfish language converter

from pgsrip.media_path import MediaPath
from pgsrip.pgs import PgsReader
from pgsrip.scrub import Redaction, scrub_display_sets

if typing.TYPE_CHECKING:
    from pgsrip.media import PgsSubtitleItem

SAMPLE = os.path.join(os.path.dirname(__file__), 'samples', 'placeholder.en.sup')

BACKENDS = ('fake', 'real')

TSV_KEYS = (
    'level',
    'page_num',
    'block_num',
    'par_num',
    'line_num',
    'word_num',
    'left',
    'top',
    'width',
    'height',
    'conf',
    'text',
)

#: default conf reported for a cue whose confidences[] entry is unset.
DEFAULT_CONFIDENCE = 96


@dataclasses.dataclass(frozen=True)
class TrackSpec:
    language: str = 'en'  # IETF tag, exactly what `mkvmerge --language` takes
    name: str | None = None  # --track-name / the track_name property, fed to trakit
    forced: bool = False
    default: bool = False
    hearing_impaired: bool = False
    commentary: bool = False
    descriptive: bool = False
    original: bool = False
    enabled: bool = True
    cues: int = 3  # 0 gives an unreadable track
    texts: tuple[str, ...] = ()  # what the fake OCR reads back, one per cue, '\n' for two lines
    confidences: tuple[int, ...] = ()  # first-pass confidence per cue
    codec: str = 'HDMV PGS'  # fake only
    type: str = 'subtitles'  # fake only
    track_id: int | None = None  # fake only: a non-contiguous mkvmerge id
    language_ietf: str | None = None  # fake only: a raw, possibly unparseable tag
    language_alpha3: str | None = None  # fake only: a raw 639-2/B code


@dataclasses.dataclass(frozen=True)
class MediaSpec:
    name: str = 'movie.mkv'
    tracks: tuple[TrackSpec, ...] = ()


_PAYLOAD_CACHE: dict[int, bytes] = {}


def payload(cues: int = 3) -> bytes:
    """The PGS bytes of a track holding `cues` subtitles, sliced out of the committed sample."""
    if cues not in _PAYLOAD_CACHE:
        media_path = MediaPath(SAMPLE)
        display_sets = PgsReader.decode(media_path.get_data(), media_path)
        data, _ = scrub_display_sets(display_sets, Redaction.NONE, only=set(range(2 * cues)))
        _PAYLOAD_CACHE[cues] = data

    return _PAYLOAD_CACHE[cues]


def _track_id(spec: TrackSpec, index: int) -> int:
    return spec.track_id if spec.track_id is not None else index


def track_json(spec: TrackSpec, track_id: int) -> dict[str, typing.Any]:
    """A single track entry the way `mkvmerge -i -F json` would emit it."""
    lang = Language.fromcleanit(spec.language) if spec.language else None
    ietf = spec.language_ietf if spec.language_ietf is not None else (spec.language or '')
    alpha3 = spec.language_alpha3 if spec.language_alpha3 is not None else (str(lang.alpha3b) if lang else '')

    properties: dict[str, typing.Any] = {
        'default_track': spec.default,
        'forced_track': spec.forced,
        'enabled_track': spec.enabled,
        'language': alpha3,
        'language_ietf': ietf,
    }
    if spec.name is not None:
        properties['track_name'] = spec.name
    if spec.hearing_impaired:
        properties['flag_hearing_impaired'] = True
    if spec.commentary:
        properties['flag_commentary'] = True
    if spec.descriptive:
        properties['flag_text_descriptions'] = True
    if spec.original:
        properties['flag_original'] = True

    return {'id': track_id, 'type': spec.type, 'codec': spec.codec, 'properties': properties}


class FakeMkvToolNix:
    """Answers `mkvmerge`/`mkvextract` invocations for registered media, in place of `pgsrip.mkv.check_output`."""

    def __init__(self) -> None:
        self.media: dict[str, MediaSpec] = {}

    def register(self, path: str, spec: MediaSpec) -> None:
        self.media[os.path.normcase(os.path.abspath(path))] = spec

    def _spec(self, path: str) -> MediaSpec:
        return self.media[os.path.normcase(os.path.abspath(path))]

    def check_output(self, cmd: list[str], *args: typing.Any, **kwargs: typing.Any) -> bytes:
        if cmd[0] == 'mkvmerge':
            spec = self._spec(cmd[-1])
            tracks = [track_json(t, _track_id(t, i)) for i, t in enumerate(spec.tracks)]
            return json.dumps({'tracks': tracks}).encode()

        if cmd[0] == 'mkvextract':
            spec = self._spec(cmd[1])
            # `MkvPgs.read_data` builds `f'{id}:{sup_file}'`; on Windows `sup_file` starts with `C:\`, so
            # partition instead of split.
            id_str, _, out_file = cmd[-1].partition(':')
            track_id = int(id_str)
            track = next(t for i, t in enumerate(spec.tracks) if _track_id(t, i) == track_id)
            with open(out_file, mode='wb') as f:
                f.write(payload(track.cues))
            return b''

        raise ValueError(f'Unexpected command: {cmd}')


def fabricate_fake(
    media_dir: str, media_specs: list[MediaSpec], toolnix: FakeMkvToolNix, monkeypatch: typing.Any
) -> None:
    """Register every media under media_dir with toolnix, and point `pgsrip.mkv.check_output` at it."""
    monkeypatch.setattr('pgsrip.mkv.check_output', toolnix.check_output)
    for spec in media_specs:
        path = os.path.join(media_dir, spec.name)
        # `core.scan_path` calls `os.path.isfile`, so a real (empty) file has to exist on disk.
        with open(path, mode='wb'):
            pass
        toolnix.register(path, spec)


def _tsv_rows_for_item(item: PgsSubtitleItem, text: str, conf: int) -> list[dict[str, typing.Any]]:
    if not item.place or not text:
        return []

    top, left, bottom, right = item.place
    lines = text.split('\n')
    line_height = max(1, (bottom - top) // len(lines))
    rows: list[dict[str, typing.Any]] = []
    for line_num, line in enumerate(lines):
        words = line.split()
        if not words:
            continue

        word_width = max(1, (right - left) // len(words))
        line_top = top + line_num * line_height
        for word_num, word in enumerate(words):
            rows.append(
                {
                    'level': 5,
                    'page_num': 0,
                    'block_num': item.index,
                    'par_num': 0,
                    'line_num': line_num,
                    'word_num': word_num,
                    'left': left + word_num * word_width,
                    'top': line_top,
                    'width': word_width,
                    'height': line_height,
                    'conf': conf,
                    'text': word,
                }
            )

    return rows


class FakeTesseract:
    """Answers `PgsToSrtRipper.process`'s tesseract calls with text fabricated from `TrackSpec.texts`."""

    def __init__(self, toolnix: FakeMkvToolNix) -> None:
        self.toolnix = toolnix
        # (subtitle path, confidence) for every `process()` call, in order: the OCR retry ladder.
        self.passes: list[tuple[str, int]] = []
        self._context: tuple[typing.Any, list[PgsSubtitleItem], int] | None = None

    def _track_spec_for(self, pgs: typing.Any) -> TrackSpec:
        spec = self.toolnix._spec(str(pgs.source_path))
        track_id = pgs.track_id
        for i, t in enumerate(spec.tracks):
            if _track_id(t, i) == track_id:
                return t

        raise KeyError(f'No track {track_id} registered for {pgs.source_path}')

    def wrap_process(self, original_process: typing.Callable[..., typing.Any]) -> typing.Callable[..., typing.Any]:
        def process(
            ripper: typing.Any,
            subs: typing.Any,
            items: list[PgsSubtitleItem],
            post_process: typing.Any,
            confidence: int,
            max_width: int,
            oem: typing.Any,
            psm: typing.Any,
        ) -> typing.Any:
            self._context = (ripper.pgs, items, confidence)
            self.passes.append((str(ripper.pgs.media_path), confidence))
            return original_process(ripper, subs, items, post_process, confidence, max_width, oem, psm)

        return process

    def image_to_data(self, image: typing.Any, **config: typing.Any) -> dict[str, list[typing.Any]]:
        assert self._context is not None
        pgs, items, _confidence = self._context
        spec = self._track_spec_for(pgs)

        rows: list[dict[str, typing.Any]] = []
        for item in items:
            text = spec.texts[item.index] if item.index < len(spec.texts) else ''
            conf = spec.confidences[item.index] if item.index < len(spec.confidences) else DEFAULT_CONFIDENCE
            rows.extend(_tsv_rows_for_item(item, text, conf))

        if not rows:
            return {key: [] for key in TSV_KEYS}

        return {key: [row[key] for row in rows] for key in TSV_KEYS}


# --- real MKVToolNix backend -------------------------------------------------------------------

MIN_MKVMERGE_VERSION = 57  # the `*-flag` option family landed in MKVToolNix 57.0.0


def mkvmerge_version() -> int:
    """The installed mkvmerge major version, or raise when it cannot be determined."""
    output = subprocess.check_output(['mkvmerge', '--version']).decode()
    match = re.search(r'mkvmerge v(\d+)', output)
    if not match:
        raise RuntimeError(f'Cannot parse mkvmerge version from: {output}')

    return int(match.group(1))


def mkvmerge_args(spec: TrackSpec) -> list[str]:
    """The mkvmerge options that set spec's flags on input TID 0."""
    yes_no = {True: 'yes', False: 'no'}
    args = ['--language', f'0:{spec.language}']
    if spec.name is not None:
        args += ['--track-name', f'0:{spec.name}']
    args += ['--default-track-flag', f'0:{yes_no[spec.default]}']
    args += ['--forced-display-flag', f'0:{yes_no[spec.forced]}']
    args += ['--track-enabled-flag', f'0:{yes_no[spec.enabled]}']
    if spec.hearing_impaired:
        args += ['--hearing-impaired-flag', '0:yes']
    if spec.commentary:
        args += ['--commentary-flag', '0:yes']
    if spec.descriptive:
        args += ['--text-descriptions-flag', '0:yes']
    if spec.original:
        args += ['--original-flag', '0:yes']

    return args


def fabricate_real(media_dir: str, payload_dir: str, media_specs: list[MediaSpec]) -> None:
    """Mux a real .mkv per media spec with mkvmerge, writing per-track .sup payloads into payload_dir.

    payload_dir must not be media_dir or a subdirectory of it: `core.scan_path` recurses into .sup
    files and would rip them as extra media.
    """
    os.makedirs(payload_dir, exist_ok=True)
    for spec in media_specs:
        cmd = ['mkvmerge', '-o', os.path.join(media_dir, spec.name)]
        for i, track in enumerate(spec.tracks):
            sup_path = os.path.join(payload_dir, f'{os.path.splitext(spec.name)[0]}-{i}.sup')
            with open(sup_path, mode='wb') as f:
                f.write(payload(track.cues))
            cmd += mkvmerge_args(track) + [sup_path]

        # mkvmerge exits 1 on warnings, so a plain check_output/check=True would treat those as failures.
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode > 1:
            output = result.stdout.decode(errors='replace')
            raise RuntimeError(f'mkvmerge failed ({result.returncode}) for {spec.name}: {output}')
