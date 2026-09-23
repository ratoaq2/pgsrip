# Project map

- `cli.py` — Click entry point. Args, progress bars, reporting.
- `api.py` — public API over `core.py` (`scan_path`, `rip`, `rip_pgs`).
- `core.py` — path scanning/filtering, top-level rip loop. No OCR logic.
- `media.py` — `Media`/`Pgs`/`PgsSubtitleItem`: media abstraction, per-item bookkeeping (timing, offsets,
  image cropped to its ink), corrupted-data auto-fix (see `docs/corrupted_data.md`).
- `mkv.py` / `sup.py` — `Media` subclasses for `.mkv`/`.mks` (`mkvmerge`/`mkvextract`) and `.sup`.
- `media_path.py` — filename parsing/generation (language, track number, extension).
- `pgs.py` — binary PGS segment format: PDS/ODS/PCS/WDS/END parsing, RLE image decoding. Format-spec-heavy;
  malformed input is the norm (see `docs/corrupted_data.md`).
- `ripper.py` — `PgsToSrtRipper`: OCR batching (see `docs/ocr_batching.md`), tesseract TSV → SRT (`accept`).
- `tsv.py` — typed wrapper over pytesseract TSV (`TsvData`/`TsvDataItem`).
- `options.py` — `Options` config object threaded through the pipeline.
- `tessdata.py` — tesseract language codes and `.traineddata` lookup/download (`Tessdata`).
- `track_flags.py` — `TrackFlags`: track flags (forced, SDH, commentary, ...), their filename tokens and the
  `--with`/`--without` filter.
- `scrub.py` — makes a small, redacted copy of a PGS track so a reporter can share a bug sample.
- `diagnostics.py` — environment checks (MKVToolNix, package versions) for bug reports.
- `utils.py` — binary/time helpers (`from_hex`, `safe_get`, `to_time`, `pairwise`).
