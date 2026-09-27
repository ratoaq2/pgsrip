# Project map

- `cli.py` — Click entry point. Args, configuration files (`--config`), progress bars, reporting. Builds the
  OCR engine chain and the post-processor chain, with the plug-ins of the `pgsrip.engines` and
  `pgsrip.postprocessors` entry points. `PluginKind` holds what differs between the two kinds.
  `PluginCommand` adds the `--<plugin>-*` options that each plug-in declares.
- `api.py` — public API over `core.py` (`scan_path`, `rip`, `rip_pgs`).
- `core.py` — path scanning/filtering, top-level rip loop: OCR chain, post-processor chain, SRT. With
  `--keep-temp-files`, writes the cues as JSON. No OCR logic.
- `postprocess.py` — `PostProcessor` protocol and `PostProcessorFactory` protocol.
- `cleanit.py` — `CleanitPostProcessor`, the default post-processor: the cleanit rules of the track language.
- `media.py` — `Media`/`Pgs`/`PgsSubtitleItem`: media abstraction, per-item bookkeeping (timing, offsets,
  image cropped to its ink), corrupted-data auto-fix (see `docs/corrupted_data.md`).
- `mkv.py` / `sup.py` — `Media` subclasses for `.mkv`/`.mks` (`mkvmerge`/`mkvextract`) and `.sup`.
- `media_path.py` — filename parsing/generation (language, track number, extension).
- `pgs.py` — binary PGS segment format: PDS/ODS/PCS/WDS/END parsing, RLE image decoding. Format-spec-heavy;
  malformed input is the norm (see `docs/corrupted_data.md`).
- `ripper.py` — `OcrEngine` protocol, `OcrEngineFactory` protocol and `PluginOption` (the options that an
  engine or a post-processor declares for the CLI), `Cue`, `create_srt`, and `PgsToSrtRipper`: asks a chain
  of OCR engines for the text of each item, and returns the cues. Each engine gets the items that the
  engines before it left unread or doubtful. It skips the engines that cannot read the language of the track.
  It does not know which engines run.
- `tesseract.py` — `TesseractEngine`: OCR batching (see `docs/ocr_batching.md`), tesseract
  TSV → item text and confidence (`accept`).
- `rapidocr.py` — `RapidOcrEngine`: the PaddleOCR text line models on ONNX Runtime, with no system program.
  It imports `rapidocr` only in its methods: `rapidocr` and `onnxruntime` come from the `rapidocr` extra. Line batching and the lowest character score (see
  `docs/ocr_batching.md`, "RapidOCR"). The models go to `PGSRIP_RAPIDOCR_DIR` or the user cache directory.
- `auto.py` — `AutoEngine`, the default engine (`--engine auto`): for each language, tesseract when it can read
  it, else RapidOCR. It overrides `engine_for`, so the cues get the name of the real engine. Not a chain.
  `check_auto` gives the `auto` line of `pgsrip doctor`. When it is OK, `doctor` shows the tesseract and
  RapidOCR checks, but they are not failures.
- `tsv.py` — typed wrapper over pytesseract TSV (`TsvData`/`TsvDataItem`).
- `options.py` — `Options` config object threaded through the pipeline. `Options.engines` holds the OCR
  engines, and `Options.post_processors` the post-processors, in chain order.
- `tessdata.py` — tesseract language codes and `.traineddata` lookup/download (`Tessdata`). `available` tells
  if tesseract has or can get a model (`TesseractEngine.supports`).
- `track_flags.py` — `TrackFlags`: track flags (forced, SDH, commentary, ...), their filename tokens and the
  `--with`/`--without` filter.
- `scrub.py` — makes a small, redacted copy of a PGS track so a reporter can share a bug sample.
- `diagnostics.py` — environment checks (MKVToolNix, package versions) for bug reports. Each OCR engine and
  post-processor adds its own checks with a `check` classmethod, e.g. `TesseractEngine.check`.
- `utils.py` — binary/time helpers (`from_hex`, `safe_get`, `to_time`, `pairwise`), `default_workers`, `split_lines`.
