# Project map

- `cli/__init__.py` — Click entry point. Args, configuration files (`--config`), progress bars, reporting.
- `cli/plugins.py` — builds the OCR engine chain and the post-processor chain, with the plug-ins of the
  `pgsrip.engines` and `pgsrip.postprocessors` entry points. `PluginKind` holds what differs between the two
  kinds. `PluginCommand` adds the `--<plugin>-*` options that each plug-in declares.
- `api.py` — public API over `core.py` (`scan_path`, `rip`, `rip_pgs`).
- `core.py` — path scanning/filtering, top-level rip loop: OCR chain, post-processor chain, SRT. With
  `--keep-temp-files`, writes the cues as JSON. No OCR logic.
- `postprocessors/base.py` — `PostProcessor` protocol and `PostProcessorFactory` protocol.
- `postprocessors/cleanit.py` — `CleanitPostProcessor`, the default post-processor: the cleanit rules of the track language.
- `media.py` — `Pgs`/`PgsSubtitleItem`: per-item bookkeeping (timing, offsets,
  image cropped to its ink), corrupted-data auto-fix (see `docs/corrupted_data.md`).
- `sources/base.py` — `Track`, the `Source` protocol, and `Media`. A source is a tool that reads the PGS tracks of
  some file extensions. `Track.create` merges the container facts with the guess from the track name. `Media`
  picks the source and has the track selection (languages, flags, one per language, `.track<n>`) for all sources.
  `Extraction`: on the first read of a track, one call of the source extracts all the selected tracks of the
  file, each one into the temp folder of its `Pgs`. When the call fails, each track raises the same error.
- `sources/__init__.py` — `SOURCES`: the built-in sources, in order of preference. `Media` uses the first one that
  reads the file. `source_checks` gives the lines of `pgsrip doctor`.
- `sources/mkvtoolnix.py` — `MkvToolNixSource` for `.mkv`/`.mks`: `mkvmerge` finds the tracks, `mkvextract` writes
  them.
- `sources/raw.py` — `RawSource` for `.sup`: the file is the data of its only track. The file name gives the
  language and the flags.
- `media_path.py` — filename parsing/generation (language, track number, extension).
- `formats/pgs.py` — binary PGS segment format: PDS/ODS/PCS/WDS/END parsing, RLE image decoding. Format-spec-heavy;
  malformed input is the norm (see `docs/corrupted_data.md`).
- `plugin.py` — `PluginOption`: the options that an engine or a post-processor declares for the CLI.
- `ripper.py` — `Cue`, `create_srt`, and `PgsToSrtRipper`: asks a chain
  of OCR engines for the text of each item, and returns the cues. Each engine gets the items that the
  engines before it left unread or doubtful. It skips the engines that cannot read the language of the track.
  It does not know which engines run.
- `engines/base.py` — `OcrEngine` protocol, `OcrEngineFactory` protocol, and `OcrError`.
- `engines/tesseract.py` — `TesseractEngine`: OCR batching (see `docs/ocr_batching.md`), tesseract
  TSV → item text and confidence (`accept`).
- `engines/rapidocr.py` — `RapidOcrEngine`: the PaddleOCR text line models on ONNX Runtime, with no system program.
  It imports `rapidocr` only in its methods: `rapidocr` and `onnxruntime` come from the `rapidocr` extra. Line batching and the lowest character score (see
  `docs/ocr_batching.md`, "RapidOCR"). The models go to `PGSRIP_RAPIDOCR_DIR` or the user cache directory.
- `engines/auto.py` — `AutoEngine`, the default engine (`--engine auto`): for each language, tesseract when it can read
  it, else RapidOCR. It overrides `engine_for`, so the cues get the name of the real engine. Not a chain.
  `check_auto` gives the `auto` line of `pgsrip doctor`. When it is OK, `doctor` shows the tesseract and
  RapidOCR checks, but they are not failures.
- `engines/tsv.py` — typed wrapper over pytesseract TSV (`TsvData`/`TsvDataItem`).
- `options.py` — `Options` config object threaded through the pipeline. `Options.engines` holds the OCR
  engines, and `Options.post_processors` the post-processors, in chain order. `Options.temp_folder` is the
  temporary folder of the run. Its `with` block removes the folder at the end.
- `engines/tessdata.py` — tesseract language codes and `.traineddata` lookup/download (`Tessdata`). `available` tells
  if tesseract has or can get a model (`TesseractEngine.supports`).
- `track_flags.py` — `TrackFlags`: track flags (forced, SDH, commentary, ...), their filename tokens and the
  `--with`/`--without` filter.
- `formats/scrub.py` — makes a small, redacted copy of a PGS track so a reporter can share a bug sample.
- `diagnostics.py` — environment checks (package versions) for bug reports. Each source, OCR engine, and
  post-processor adds its own checks with a `check` classmethod, e.g. `TesseractEngine.check`.
- `utils.py` — binary/time helpers (`from_hex`, `safe_get`, `to_time`, `pairwise`), `default_workers`, `split_lines`.
