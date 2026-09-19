# pgsrip

CLI + library that extracts PGS/SUP subtitles (from `.mkv`, `.mks`, `.sup`) and OCRs them into `.srt` via
MKVToolNix + tesseract.

## Commands

Package management is `uv` (not poetry/pip). Python 3.11–3.14 only (see `pyproject.toml` `requires-python`).

```
uv sync                              # install/update the local environment from uv.lock
uv run pytest tests                  # run tests
uv run pytest --cov pgsrip tests     # run tests with coverage
uv run ruff check .                  # lint
uv run ruff format .                 # format
uv run mypy pgsrip                   # type-check (strict)
bash scripts/test.sh                 # everything CI runs, in one shot
uv run pre-commit run --all-files    # run all pre-commit hooks manually
uv build                             # build sdist + wheel
```

`pre-commit install --hook-type pre-commit --hook-type commit-msg` is already active in this checkout's
`.git/hooks` — ruff/mypy run before each commit, and commit messages are checked against Conventional
Commits before they're accepted.

## Code style

- **Typing is strict mypy** (`strict = true` in `pyproject.toml`). Every function needs full parameter and
  return annotations. When a value is genuinely optional (corrupted/partial PGS data), keep it `X | None`
  and narrow explicitly (`assert` or a filtered comprehension) at the point where a concrete value is
  required — don't silently assume non-`None`.
- **Ruff** does both linting and formatting (replaces the old flake8 + flake8-import-order + no-formatter
  setup). Single quotes, 120-char lines — both enforced by `ruff format`, don't hand-format against it.
- **Commit messages**: Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`, etc.), single-line subject,
  no attribution trailers.
- Flat package layout (`pgsrip/`, not `src/pgsrip/`) — keep it that way, there's no reason to change it at
  this size.

## Project map

- `cli.py` — Click entry point (`pgsrip` command). Argument parsing, progress bars, reporting.
- `api.py` — small public API wrapping `core.py` (`scan_path`, `rip`, `rip_pgs`) for library consumers.
- `core.py` — path scanning/filtering and the top-level rip loop; no OCR logic itself.
- `media.py` — `Media`/`Pgs`/`PgsSubtitleItem`: media abstraction, per-subtitle-item bookkeeping (timing,
  offsets, image), and the corrupted-data auto-fix logic.
- `mkv.py` / `sup.py` — `Media` subclasses for `.mkv`/`.mks` (via `mkvmerge`/`mkvextract`) and `.sup` files.
- `media_path.py` — filename parsing/generation (language code, track number, extension) shared by all
  media types.
- `pgs.py` — binary PGS segment format: reader/parser for PDS/ODS/PCS/WDS/END segments, RLE image decoding.
  This is the format-spec-heavy module; changes here need care since malformed real-world subtitle files
  are the norm, not the exception (see below).
- `ripper.py` — `PgsToSrtRipper`: the OCR batching engine (see below) and the tesseract TSV → SRT text
  mapping (`accept`).
- `tsv.py` — typed wrapper around pytesseract's TSV output (`TsvData`/`TsvDataItem`).
- `options.py` — `Options` dataclass-like config object threaded through the whole pipeline.
- `utils.py` — small binary/time helpers (`from_hex`, `safe_get`, `to_time`, `pairwise`).

## Domain knowledge

**Why the OCR batching exists**: PGS subtitles are bitmap images, one per subtitle event. Calling tesseract
once per subtitle item would mean one OCR process/roundtrip per line of dialogue — for a full episode/movie
that's hundreds of slow roundtrips. Instead, `ripper.py`'s `FullImage`/`ImageArea` pack as many subtitle
bitmaps as will fit into one (or a handful of) composite PNGs — bin-packed by vertical overlap and a max
width — and hand the whole composite to tesseract in a single `image_to_data` call. `TsvData` then maps each
recognized word back to the originating subtitle item by correlating pixel regions (`item.place`) against
tesseract's per-word bounding boxes. `PgsToSrtRipper.rip()` retries unrecognized items with progressively
smaller batches / lower confidence thresholds until everything is resolved or given up on. When touching
this code, the goal to preserve is: minimize tesseract invocations, not minimize code complexity.

**Corrupted input is expected, not exceptional**: real-world PGS streams are frequently malformed (bad
muxing, truncated segments). `media.py`'s `auto_fix` and the `Optional[int]`-heavy fields in `pgs.py`
(`from_hex` returning `None` on empty slices) exist to degrade gracefully — log and drop a bad subtitle
item rather than crash the whole rip. Don't tighten these into hard failures without checking whether
that's actually desired.

**Test coverage is intentionally thin**: this repo does not commit real-world subtitle fixtures because
they're typically copyrighted content extracted from commercial media. The only fixture (`tests/test_mkvtrack.yml`)
is synthetic MKV track metadata, not actual PGS image data — so `pgs.py`/`ripper.py`'s core decode/OCR path
has no regression coverage today. If you're ever handed real (non-infringing) `.sup`/`.mkv` samples, adding
them as fixtures would be high-value.

**Future direction (not yet implemented)**: better bug-report reproducibility — capturing enough of a
reporter's subtitle track (without requiring them to share copyrighted media) to reproduce an issue locally.
No design decided yet; flag it if relevant work comes up.
