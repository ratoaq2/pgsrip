"""End-to-end rip tests: fabricated MKV in, ripped .srt out, driven through the CLI.

Tesseract is mocked (`fake_ocr`); MKVToolNix is mocked by default (`--media-backend fake`) and can be
run for real with `--media-backend real`/`both`. See docs/rip-e2e.md.
"""

from __future__ import annotations

import os
import tempfile
import typing

import numpy as np
import pysrt
import pytest
from click.testing import CliRunner

from pgsrip.cli import pgsrip
from pgsrip.media import PgsSubtitleItem
from pgsrip.media_path import MediaPath
from pgsrip.pgs import PgsReader
from pgsrip.ripper import MAX_TESS_DIMENSION, FullImage, PgsToSrtRipper

from . import from_yaml
from .fabricate import (
    BACKENDS,
    MIN_MKVMERGE_VERSION,
    SAMPLE,
    FakeMkvToolNix,
    FakeTesseract,
    MediaSpec,
    TrackSpec,
    fabricate_fake,
    fabricate_real,
    mkvmerge_version,
)

#: every language the matrix exercises, plus `osd`: with all "installed", `Tessdata.ensure` never
#: touches the network.
INSTALLED_CODES = {'eng', 'deu', 'fra', 'spa', 'por', 'chi_sim', 'chi_tra', 'jpn', 'osd'}


@pytest.fixture(autouse=True)
def tesseract_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never call tesseract and never download a traineddata file."""
    monkeypatch.setattr('pgsrip.tessdata.tess.get_languages', lambda: sorted(INSTALLED_CODES))


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: typing.Any) -> None:
    temp_dir = tmp_path / 'temp'
    temp_dir.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(temp_dir))
    monkeypatch.setenv('OMP_THREAD_LIMIT', '1')  # ripper.py:154 sets and never restores it


@pytest.fixture
def toolnix() -> FakeMkvToolNix:
    return FakeMkvToolNix()


@pytest.fixture
def fake_ocr(toolnix: FakeMkvToolNix, monkeypatch: pytest.MonkeyPatch) -> FakeTesseract:
    ocr = FakeTesseract(toolnix)
    monkeypatch.setattr(PgsToSrtRipper, 'process', ocr.wrap_process(PgsToSrtRipper.process))
    monkeypatch.setattr(FullImage, 'from_items', ocr.wrap_from_items(FullImage.from_items))
    monkeypatch.setattr('pgsrip.ripper.tess.image_to_data', ocr.image_to_data)
    return ocr


@pytest.fixture
def fabricate_media(
    tmp_path: typing.Any, toolnix: FakeMkvToolNix, monkeypatch: pytest.MonkeyPatch, media_backend: str
) -> typing.Callable[[dict[str, typing.Any]], typing.Any]:
    def build(scenario: dict[str, typing.Any]) -> typing.Any:
        media_dir = tmp_path / 'media'
        media_dir.mkdir()
        specs = media_specs(scenario)
        if media_backend == 'fake':
            fabricate_fake(str(media_dir), specs, toolnix, monkeypatch)
        else:
            # a missing or too-old mkvmerge has to fail loudly, not skip: a green real-backend job
            # that tested nothing is worse than a red one.
            version = mkvmerge_version()
            assert version >= MIN_MKVMERGE_VERSION, (
                f'mkvmerge v{version} is older than the required v{MIN_MKVMERGE_VERSION}'
            )
            fabricate_real(str(media_dir), str(tmp_path / 'payloads'), specs)
            # fake_ocr still needs to know which text belongs to which track, on both backends.
            for spec in specs:
                toolnix.register(os.path.join(str(media_dir), spec.name), spec)

        for name, content in scenario.get('existing', {}).items():
            (media_dir / name).write_text(content, encoding='utf-8')

        return media_dir

    return build


@pytest.fixture
def media_backend() -> str:
    """Overridden by conftest.py's pytest_generate_tests for every test that requests it."""
    return 'fake'


def track_spec(track: dict[str, typing.Any]) -> TrackSpec:
    kwargs = dict(track)
    if 'texts' in kwargs:
        kwargs['texts'] = tuple(kwargs['texts'])
    if 'confidences' in kwargs:
        kwargs['confidences'] = tuple(kwargs['confidences'])
    return TrackSpec(**kwargs)


def media_spec(media: dict[str, typing.Any]) -> MediaSpec:
    return MediaSpec(name=media.get('name', 'movie.mkv'), tracks=tuple(track_spec(t) for t in media.get('tracks', [])))


def media_specs(scenario: dict[str, typing.Any]) -> list[MediaSpec]:
    if 'medias' in scenario:
        return [media_spec(m) for m in scenario['medias']]
    return [media_spec(scenario['media'])]


def written_subtitles(media_dir: typing.Any) -> set[str]:
    return {p.name for p in media_dir.iterdir() if p.suffix == '.srt'}


def read_cues(path: typing.Any, encoding: str | None = None) -> list[tuple[str, str, str]]:
    # never read the raw file text: pysrt writes os.linesep, which is CRLF on Windows.
    subs = pysrt.open(str(path), encoding=encoding or 'utf-8')
    return [(str(item.start), str(item.end), item.text) for item in subs]


def parameters_from_yaml(test_filename: str) -> list[typing.Any]:
    return [pytest.param(scenario, id=scenario['name']) for scenario in from_yaml(test_filename)]


@pytest.mark.parametrize('scenario', parameters_from_yaml(__file__))
def test_scenarios(
    scenario: dict[str, typing.Any],
    media_backend: str,
    fabricate_media: typing.Callable[[dict[str, typing.Any]], typing.Any],
    fake_ocr: FakeTesseract,
) -> None:
    # given
    if media_backend not in scenario.get('backends', list(BACKENDS)):
        pytest.skip(f'scenario is {scenario.get("backends")} only')
    media_dir = fabricate_media(scenario)

    # when
    result = CliRunner().invoke(pgsrip, ['rip', *scenario.get('args', []), str(media_dir)])

    # then
    assert result.exit_code == 0, result.output
    for text in scenario.get('output', []) + scenario.get('failures', []):
        assert text in result.output

    expected = scenario.get('expected', {})
    assert written_subtitles(media_dir) == set(expected)
    for name, cues in expected.items():
        assert read_cues(media_dir / name, scenario.get('encoding')) == [tuple(c) for c in cues]

    if 'ocr_passes' in scenario:
        assert len(fake_ocr.passes) == scenario['ocr_passes']

    # nothing else appeared in the directory: no stray .sup extracts, no leftover temp files.
    expected_files = {s.name for s in media_specs(scenario)} | set(expected) | set(scenario.get('existing', {}))
    assert {p.name for p in media_dir.iterdir()} == expected_files


def test_all_silently_disables_one_per_language(
    fabricate_media: typing.Callable[[dict[str, typing.Any]], typing.Any], fake_ocr: FakeTesseract
) -> None:
    """Pinned as-is: `--all --one-per-language` writes both files (`one_per_lang` vs `one_per_language` in
    mkv.py:145 — `--all` sets `one_per_lang=False`, which is also the flag `one_per_language` collapsing is
    gated on)."""
    scenario = {
        'media': {
            'name': 'movie.mkv',
            'tracks': [
                {'language': 'en', 'cues': 1, 'texts': ['Plain']},
                {'language': 'en', 'cues': 1, 'texts': ['SDH'], 'hearing_impaired': True},
            ],
        }
    }
    media_dir = fabricate_media(scenario)

    result = CliRunner().invoke(pgsrip, ['rip', '--all', '--one-per-language', str(media_dir)])

    assert result.exit_code == 0, result.output
    assert written_subtitles(media_dir) == {'movie.en.srt', 'movie.en.sdh.srt'}


def test_pgsrip_rips_without_naming_the_rip_command(
    fabricate_media: typing.Callable[[dict[str, typing.Any]], typing.Any], fake_ocr: FakeTesseract
) -> None:
    scenario = {'media': {'name': 'movie.mkv', 'tracks': [{'language': 'en', 'cues': 1, 'texts': ['Hi there']}]}}
    media_dir = fabricate_media(scenario)

    result = CliRunner().invoke(pgsrip, [str(media_dir)])

    assert result.exit_code == 0, result.output
    assert written_subtitles(media_dir) == {'movie.en.srt'}


def test_a_corrupt_track_is_reported_with_the_scrub_command_to_run(
    media_backend: str, fabricate_media: typing.Callable[[dict[str, typing.Any]], typing.Any], fake_ocr: FakeTesseract
) -> None:
    if media_backend != 'fake':
        pytest.skip('an empty payload is not a muxable .sup, this is fake-backend only')

    scenario = {'media': {'name': 'movie.mkv', 'tracks': [{'language': 'en', 'cues': 0}]}}
    media_dir = fabricate_media(scenario)

    result = CliRunner().invoke(pgsrip, ['rip', str(media_dir)])

    # `rip` never exits non-zero: failures are content, not exit code.
    assert result.exit_code == 0, result.output
    # the message text (`max() arg is an empty sequence`) differs across 3.11-3.14: match the type only.
    assert '<ValueError>' in result.output
    assert 'pgsrip scrub' in result.output


def test_no_temporary_folder_is_left_behind(
    fabricate_media: typing.Callable[[dict[str, typing.Any]], typing.Any], fake_ocr: FakeTesseract, tmp_path: typing.Any
) -> None:
    scenario = {'media': {'name': 'movie.mkv', 'tracks': [{'language': 'en', 'cues': 1, 'texts': ['Hi there']}]}}
    media_dir = fabricate_media(scenario)

    result = CliRunner().invoke(pgsrip, ['rip', str(media_dir)])

    assert result.exit_code == 0, result.output
    temp_root = tmp_path / 'temp'
    assert list(temp_root.iterdir()) == []


@pytest.fixture
def sample_items() -> list[PgsSubtitleItem]:
    media_path = MediaPath(SAMPLE)
    display_sets = list(PgsReader.decode(media_path.get_data(), media_path))
    return PgsSubtitleItem.create_items(media_path, display_sets)


def test_every_subtitle_image_is_composed_where_its_place_says(sample_items: list[PgsSubtitleItem]) -> None:
    """The contract the whole fake OCR rests on: `item.place` is where `from_items` actually drew it."""
    composites = list(FullImage.from_items(sample_items, (42, 112), MAX_TESS_DIMENSION, MAX_TESS_DIMENSION))
    assert len(composites) == 1
    for item in sample_items:
        assert item.place is not None and item.image is not None
        top, left, bottom, right = item.place
        assert np.array_equal(composites[0].data[top:bottom, left:right], item.image.data)


def test_composites_are_bounded_in_height(sample_items: list[PgsSubtitleItem]) -> None:
    """Issue #136: a long track must be split into several composites, each small enough for tesseract."""
    # 600 px wide fits one 480 px item per area; 340 px tall fits two 48 px areas plus gap and border.
    max_width, max_height = 600, 340
    composites = list(FullImage.from_items(sample_items, (42, 112), max_width, max_height))

    assert [c.data.shape for c in composites] == [(338, 680), (248, 680)]
    assert sorted(item.index for c in composites for item in c.items) == [0, 1, 2]
    for composite in composites:
        height, width = composite.data.shape
        assert height <= max_height
        assert width <= max_width + 2 * FullImage.border
        for item in composite.items:
            assert item.place is not None and item.image is not None
            top, left, bottom, right = item.place
            assert np.array_equal(composite.data[top:bottom, left:right], item.image.data)


def test_an_area_taller_than_the_bound_gets_a_composite_of_its_own(sample_items: list[PgsSubtitleItem]) -> None:
    composites = list(FullImage.from_items(sample_items, (42, 112), 600, 1))

    assert [[item.index for item in c.items] for c in composites] == [[0], [1], [2]]


def test_a_pass_split_into_several_composites_rips_every_cue_once(
    fabricate_media: typing.Callable[[dict[str, typing.Any]], typing.Any],
    fake_ocr: FakeTesseract,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # the committed sample has 3 small cues: shrink the bounds instead of fabricating thousands of cues.
    from_items = FullImage.from_items
    monkeypatch.setattr(FullImage, 'from_items', lambda items, gap, _w, _h: from_items(items, gap, 600, 340))
    scenario = {'media': {'name': 'movie.mkv', 'tracks': [{'language': 'en', 'texts': ['One', 'Two', 'Three']}]}}
    media_dir = fabricate_media(scenario)

    result = CliRunner().invoke(pgsrip, ['rip', str(media_dir)])

    assert result.exit_code == 0, result.output
    assert len(fake_ocr.passes) == 1
    assert len(fake_ocr.composites) == 2
    assert read_cues(media_dir / 'movie.en.srt') == [
        ('00:00:01,000', '00:00:03,000', 'One'),
        ('00:00:04,000', '00:00:06,000', 'Two'),
        ('00:00:07,000', '00:00:09,000', 'Three'),
    ]
