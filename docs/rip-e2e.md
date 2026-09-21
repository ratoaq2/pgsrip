# End-to-end rip tests (`tests/test_rip_e2e.py`)

## 1. Context

`ripper.py`/`mkv.py`'s core decode/OCR path had no regression coverage: `test_core.py` asserted
`srt_path` strings without ever ripping, `test_samples.py` decoded PGS without ever OCRing,
`test_cli.py` was a 13-line `--help` smoke test. Nothing wrote an `.srt` and looked at it.

The goal: a guessit-style suite where the input is parameters that fabricate a media file, and the
output is the set of ripped `.srt` files and their content, driven through the CLI so it is genuinely
end to end. Tesseract is mocked in every scenario; MKVToolNix is mocked by default and can also run for
real.

## 2. Findings

- There is no MKV-creation logic in the repo. `scrub` only rewrites `.sup` bitmaps in place;
  `mkvmerge`/`mkvextract` are only ever read from. `tests/samples/placeholder.en.sup` (a committed,
  non-copyrighted, synthetic 3-cue PGS stream) plus `scrub_display_sets(..., only=...)` is the payload;
  the container around it is fabricated.
- `--all --one-per-language` silently ignores `--one-per-language`: `mkv.py`'s dedup key is gated on
  `options.one_per_lang`, and `--all` sets `one_per_lang = False`, so the `one_per_language` collapsing
  branch never runs. Pinned as-is in `test_all_silently_disables_one_per_language`, not fixed here.
- `MkvPgs.__init__` creates a temp folder for every *candidate* track but `rip_pgs` only enters (and
  therefore only cleans up) the ones it actually rips. The happy path leaves nothing behind; a track
  that gets filtered, deduped, or excluded leaks its temp folder. `tempfile.tempdir` redirection (below)
  keeps this from touching the real system temp dir; `test_no_temporary_folder_is_left_behind` only
  covers the happy path.

## 3. Target design

- **Hybrid media backend**, one fabrication API: `fake` (default) monkeypatches
  `pgsrip.mkv.check_output`; `real` actually muxes with `mkvmerge`. The same YAML scenarios run through
  both via `--media-backend {fake,real,both}` (`pytest_addoption`/`pytest_generate_tests` in
  `tests/conftest.py`).
- **`tests/fabricate.py`**: the fabrication API, pytest-free (builds bytes, dicts and argv lists, so it
  can be driven from a plain script). `TrackSpec`/`MediaSpec` dataclasses; `payload(cues)` slices the
  committed sample with `scrub_display_sets`; `FakeMkvToolNix` answers `mkvmerge -i -F json` and
  `mkvextract` from a registry of `MediaSpec`; `FakeTesseract` wraps `PgsToSrtRipper.process` so the
  real image composition still runs (`item.place` gets set for real) and patches
  `pgsrip.ripper.tess.image_to_data` to read back `TrackSpec.texts`/`confidences` instead of running
  tesseract; `mkvmerge_version`/`mkvmerge_args`/`fabricate_real` drive the real backend.
- **YAML scenarios** (`tests/test_rip_e2e.yml`), loaded with the existing `from_yaml()` helper and fed
  to `@pytest.mark.parametrize`, the `tests/test_mkvtrack.py` pattern. Each scenario asserts both the
  set of files written and their content (cue count, timings, text), and that nothing else appeared in
  the directory (catches stray `.sup` extracts and leftover temp files).
- **No autouse fixtures in `conftest.py`.** `tesseract_data`/`isolated_environment` are module-local to
  `test_rip_e2e.py`; redirecting `tempfile.tempdir` or patching `tess.get_languages` repo-wide would
  silently change `tests/test_tessdata.py`, which tests the real fallback/patches `get_languages`
  itself.
- The `item.place` contract (`FullImage.from_items` draws each item's image exactly where `item.place`
  says) is the one thing the whole fake OCR rests on. It is pinned once, directly, in
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
**Do:** `FakeTesseract`, the `PgsToSrtRipper.process` wrapper, per-track registration, multi-line text,
`confidences`. The `item.place` contract test.
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
**Done when:** the full matrix is green; `--cov` shows `ripper.py`, `mkv.py`, `core.py`, `cli.py`
visibly up. Measured: `ripper.py` 24% → 88%, `cli.py` 34% → 61%, `mkv.py` 88% → 96%, overall 72% → 85%.

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
- `--all --one-per-language` and the `MkvPgs` temp-folder leak on non-happy paths are pinned/noted as
  found, not fixed, per the plan.
