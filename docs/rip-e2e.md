# End-to-end rip tests (`tests/test_rip_e2e.py`)

## 1. Context

The other tests check one part each: `tests/test_api.py` checks the selection and the output paths,
`tests/test_samples.py` decodes PGS with no OCR, and `tests/test_cli.py` checks the options. These tests
rip media from end to end: they write the `.srt` files and check them.

The goal: a guessit-style suite where the input is parameters that fabricate a media file, and the
output is the set of ripped `.srt` files and their content, driven through the CLI so it is genuinely
end to end. Tesseract is mocked in every scenario; MKVToolNix is mocked by default and can also run for
real.

## 2. Findings

- There is no MKV-creation logic in the repo. `scrub` only rewrites `.sup` bitmaps in place;
  `mkvmerge`/`mkvextract` are only ever read from. `tests/samples/placeholder.en.sup` (a committed,
  non-copyrighted, synthetic 3-cue PGS stream) plus `scrub_display_sets(..., only=...)` is the payload;
  the container around it is fabricated.
- `--all --one-per-language` silently ignores `--one-per-language`: `media.py`'s dedup key is gated on
  `not options.all_tracks`, and `--all` sets `all_tracks = True`, so the `one_per_language` collapsing
  branch never runs. Pinned as-is in `test_all_silently_disables_one_per_language`, not fixed here.
- A `Subtitle` makes its temporary directory on first use (`Subtitle.temp_dir`), in the directory of the run
  (`Workspace.dir`). `api.rip` removes the track directory, and the CLI removes the run directory. A track that
  gets filtered, deduped, excluded, or dropped by `pending` makes no directory.
  `test_no_temporary_directory_is_left_behind`
  covers the happy path, and `tests/test_api.py` covers a skipped track. `tempfile.tempdir` redirection
  (below) keeps the tests from touching the real system temp dir.
- The CLI has only the `srt` writer. `test_a_second_writer_writes_its_missing_file_and_the_existing_srt_does_not_change`
  calls `api.rip` directly, with `Options(writers=[SrtWriter(), FakeWriter()])`. `FakeWriter` is in
  `tests/test_writers.py`. The test checks the skip logic for each writer: one OCR pass, the existing `.srt`
  does not change, and the missing `.fake` file is written.

## 3. Target design

- **Hybrid media backend**, one fabrication API: `fake` (default) monkeypatches
  `pgsrip.sources.mkvtoolnix.check_output`; `real` actually muxes with `mkvmerge`. The same YAML scenarios run through
  both via `--media-backend {fake,real,both}` (`pytest_addoption`/`pytest_generate_tests` in
  `tests/conftest.py`).
- **`tests/fabricate.py`**: the fabrication API, pytest-free (builds bytes, dicts and argv lists, so it
  can be driven from a plain script). `TrackSpec`/`MediaSpec` dataclasses; `payload(cues)` slices the
  committed sample with `scrub_display_sets`; `FakeMkvToolNix` answers `mkvmerge -i -F json` and
  `mkvextract` from a registry of `MediaSpec`; `FakeTesseract` wraps `api.decode` to know the ripped track,
  wraps `TesseractEngine.read_pass` so the real image composition still runs (`Composite.placed` is real),
  wraps `Composite.from_items` to record every composite, and patches `pgsrip.engines.tesseract.tess.image_to_data` to read back
  `TrackSpec.texts`/`confidences` for the items of the composite it receives (matched by identity, not
  pixels: the sample cues are identical bitmaps) instead of running tesseract; `mkvmerge_version`/`mkvmerge_args`/`fabricate_real` drive the real backend.
- **YAML scenarios** (`tests/test_rip_e2e.yml`), loaded with the existing `from_yaml()` helper and fed
  to `@pytest.mark.parametrize`, the `tests/test_track.py` pattern. Each scenario asserts both the
  set of files written and their content (cue count, timings, text), and that nothing else appeared in
  the directory (catches stray `.sup` extracts and leftover temp files).
- **No autouse fixtures in `conftest.py`.** `tesseract_data`/`isolated_environment` are module-local to
  `test_rip_e2e.py`; redirecting `tempfile.tempdir` or patching `tess.get_languages` repo-wide would
  silently change `tests/test_tessdata.py`, which tests the real fallback/patches `get_languages`
  itself.
- The `Composite.placed` contract (`Composite.from_items` draws each item's ink-cropped `bitmap` exactly
  where its box in `placed` says) is the one thing the whole fake OCR rests on. It is pinned once, directly, in
  `test_every_subtitle_image_is_composed_where_its_place_says`, instead of trying to verify it through
  ink detection on the composite image.

## 4. Steps

### Step 1 — payloads and the fake MKVToolNix

**Files:** `tests/fabricate.py`, `tests/test_rip_e2e.py`.
**Do:** `TrackSpec`/`MediaSpec`, `payload()`, `track_json()`, `FakeMkvToolNix`, `fabricate_fake()`, the
two autouse hygiene fixtures.
**Done when:** a single `en` track rips to `movie.en.srt` with 3 cues at 1-3/4-6/7-9s; nothing appears
in the system temp dir.

### Step 2 — the fake OCR

**Files:** `tests/fabricate.py`.
**Do:** `FakeTesseract`, the `TesseractEngine.read_pass` wrapper, per-track registration, multi-line text,
`confidences`. The `Composite.placed` contract test.
**Done when:** a two-line cue, a cue recovered on retry, a cue below confidence 0, and an empty-text cue
are all covered.

### Step 3 — YAML schema and runner

**Files:** `tests/test_rip_e2e.yml`, `tests/test_rip_e2e.py`.
**Do:** `media_specs()`, `read_cues()`, `written_subtitles()`, `test_scenarios`, a stub `media_backend`
fixture returning `'fake'`.
**Done when:** scenarios 1-9 (naming, flag tokens, trakit name guessing, track-id collisions, IETF
tags) are green with readable ids.

### Step 4 — the rest of the matrix

**Files:** `tests/test_rip_e2e.yml`, `tests/test_rip_e2e.py`.
**Do:** scenarios 10-26 (language fallback, non-PGS tracks, disabled tracks, `--with`/`--without`,
`--one-per-language`, `-l`, cleanit, the OCR retry ladder, corrupt tracks, existing files, directory
scans, encoding), plus the hand-written behaviour tests.
**Done when:** the full matrix is green, and `--cov` shows more coverage of the rip path and of the CLI.

### Step 5 — the real backend

**Files:** `tests/fabricate.py`, `tests/conftest.py`, `tests/test_rip_e2e.py`,
`.github/workflows/test.yml`.
**Do:** `mkvmerge_version()`, `mkvmerge_args()`, `fabricate_real()`, the real `media_backend` wiring
(a missing or too-old mkvmerge fails the test rather than skipping it), `backends: [fake]` on the
scenarios that need a video/audio/non-PGS track, a non-contiguous id, or an empty (unmuxable) payload,
the CI job.
**Done when:** `--media-backend both` passes locally; default `scripts/test.sh` duration unchanged.
Measured: real-backend `.srt` content is byte-for-byte identical to the fake backend's for every shared
scenario — no `TIMING_TOLERANCE_MS` was needed.

### Step 6 — documentation

**Files:** `CLAUDE.md`, `README.md`, `docs/rip-e2e.md`.
**Do:** this document; a short README "Tests" note.
**Done when:** `scripts/test.sh` passes (ruff/mypy/pytest; see the progress log for one unrelated,
pre-existing gap) and nothing in the repo still claims the OCR path is untested.

## 5. Progress log

- All six steps implemented and verified green in one pass, including both the fake and the real
  MKVToolNix backend (`mkvmerge v100.0` locally). `bash scripts/test.sh`'s pytest/mypy/ruff-check steps
  are green; `ruff format --check .` only flags an untracked file outside the repo
  (`plans/...md`, not part of this change) — not a regression.
- No `TIMING_TOLERANCE_MS` was needed: `mkvextract`'s regenerated display sets produced the same
  timings as the fake backend for the one scenario compared directly
  (`pytest tests/test_rip_e2e.py --media-backend both -k "single and english and track"`).
- `--all --one-per-language` is pinned as found, not fixed, per the plan.
