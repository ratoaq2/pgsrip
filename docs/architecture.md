# Project map

- `cli/__init__.py` — Click entry point. Args, configuration files (`--config`), progress bars, reporting. The
  path of each scrubbed file (`output_path`).
- `cli/plugins.py` — builds the OCR engine chain and the post-processor chain, with the plug-ins of the
  `pgsrip.engines` and `pgsrip.postprocessors` entry points. `PluginKind` holds what differs between the two
  kinds. `PluginCommand` adds the `--<plugin>-*` options that each plug-in declares.
- `api.py` — the library API, re-exported by `pgsrip/__init__.py` with `Options`, `Media`, `Subtitle`, `Workspace`,
  and `PgsripError`. `scan` finds the media files
  and returns a `ScanResult` (media, filtered out, ignored, each skipped path with its reason). `pending` keeps
  the subtitles with a file to write: the selection of `Media` does not look at the files. `prepare` gets the
  OCR engines ready for the languages of the subtitles, before the first `rip`. `rip` rips one
  subtitle: decoding, OCR chain, post-processor chain, writers. It raises the error that stops it.
  `pending_writers`: the writers whose file is missing, or must be written again with `--force`. The default
  engines, post-processors, and writers. With `--keep-temp-files`, writes the display sets and the cues. No OCR
  logic.
- `writers/base.py` — `Writer` protocol: `write(path, cues, track, encoding)` writes the cues of a track to a file.
  `name` is the value of `--format`.
- `writers/srt.py` — `SrtWriter`: the SRT file, with pysrt. It sorts the cues and leaves out a cue with no text.
- `writers/__init__.py` — `WRITERS`: the built-in writers.
- `postprocessors/__init__.py` — `POST_PROCESSORS`: the built-in post-processors, and
  `POST_PROCESSOR_ENTRY_POINTS`, the entry point group of the other packages.
- `postprocessors/base.py` — `PostProcessor` protocol (`process(cues, track)`) and `PostProcessorFactory` protocol.
  A post-processor and a writer get the `Track`, not the `Subtitle`.
- `postprocessors/cleanit.py` — `CleanitPostProcessor`, the default post-processor: the cleanit rules of the track language.
- `media.py` — `Media`, `Subtitle`, `Extraction`, and `Workspace`. `Media` is one media file: it picks the source
  and has the track selection (languages, flags, one per language, `.track<n>`) for all sources. `Subtitle` is one
  selected track to rip: its track, its source path, the base of its output paths, its extraction (`read`), and its
  temporary directory. `Extraction`: on the first read of a track, one call of the source extracts all the
  pending tracks of the file, each one into the temporary directory of its `Subtitle`. A subtitle that `pending`
  drops, or whose `with` block ends, is released: the next call does not extract it. When the call fails, each
  track raises the same error. `Workspace` is the temporary
  directory of a run. Its `with` block removes the directory at the end, except with `keep` (`--keep-temp-files`).
- `sources/base.py` — `Track`, the `Source` protocol, and `SourceError`. A source is a tool that reads the PGS
  tracks of some file extensions. `Media` raises `SourceError` when no source can read the file. `Track.create`
  merges the container facts with the guess from the track name.
- `sources/__init__.py` — `SOURCES`: the built-in sources, in order of preference. `Media` uses the first one that
  reads the file. `source_checks` gives the lines of `pgsrip doctor`.
- `sources/mkvtoolnix.py` — `MkvToolNixSource` for `.mkv`/`.mks`: `mkvmerge` finds the tracks, `mkvextract` writes
  them.
- `sources/raw.py` — `RawSource` for `.sup`: the file is the data of its only track. The file name gives the
  language and the flags.
- `media_path.py` — `MediaPath`: reads and writes the file name parts (language, flags, track number,
  extension). `replace` gives a copy with other parts.
- `formats/pgs.py` — binary PGS segment format: PDS/ODS/PCS/WDS/END parsing (`read_segments`,
  `read_display_sets`), RLE image decoding (`PgsImage`, `decode_rle_image`), the binary helpers (`to_int`,
  `safe_get`, `to_time`). `Item`: one subtitle image with its times, cropped to its ink (`Item.box` is where the
  ink is on the screen). `read_items` groups the display sets, and `make_item` fixes or drops a corrupted
  group. An `Item` has plain values: its times, its image, and its window position are never None. Malformed input is frequent: see `docs/corrupted_data.md`.
- `plugin.py` — `PluginOption`: the options that an engine or a post-processor declares for the CLI.
- `cue.py` — `Cue`: the text result of one item. The post-processors and the writers get the cues.
- `engines/chain.py` — `read_cues`: asks a chain of OCR engines for the text of each item, and returns the
  cues and the time of each engine. Each engine gets the items that the engines before it left unread or
  doubtful. It skips the engines that cannot read the language of the track. It does not know which engines
  run.
- `engines/__init__.py` — `ENGINES`: the built-in OCR engines, and `ENGINE_ENTRY_POINTS`, the entry point group of
  the other packages. The library can list the engines with no CLI.
- `engines/base.py` — `OcrEngine` protocol, `OcrEngineFactory` protocol, `Reading` (the text, the confidence
  and the doubtful flag that an engine gives for one item), and `OcrError`.
- `engines/tesseract.py` — `TesseractEngine`: OCR batching (see `docs/ocr_batching.md`), tesseract
  TSV → item text and confidence (`read_item`).
- `engines/rapidocr.py` — `RapidOcrEngine`: the PaddleOCR text line models on ONNX Runtime, with no system program.
  It imports `rapidocr` only in its methods: `rapidocr` and `onnxruntime` come from the `rapidocr` extra. Line batching and the lowest character score (see
  `docs/ocr_batching.md`, "RapidOCR"). The models go to `--rapidocr-dir` (`PGSRIP_RAPIDOCR_DIR`) or the user cache directory.
- `engines/auto.py` — `AutoEngine`, the default engine (`--engine auto`, `AUTO`, with the `AUTO_ENGINES`).
  `AutoEngine.from_engines` makes it from the engines of the CLI. For each language, it uses tesseract when
  tesseract can read the language, else RapidOCR. It overrides `engine_for`, so the cues get the name of the real engine. Not a chain.
  `AutoEngine.check` gives the `auto` line of `pgsrip doctor`. When it is OK, `doctor` shows the tesseract and
  RapidOCR checks, but they are not failures.
- `engines/tsv.py` — typed wrapper over pytesseract TSV (`TsvResult`/`TsvWord`).
- `options.py` — `Options`: a frozen dataclass of plain values, with the names of the CLI options. It imports
  no engine. `Options.engines` and `Options.post_processors` are chains. None in `engines`, `post_processors`,
  or `writers` means the default that `api.py` gives: auto, cleanit, srt.
- `engines/tessdata.py` — tesseract language codes and `.traineddata` lookup/download (`Tessdata`). `available` tells
  if tesseract has or can get a model (`TesseractEngine.supports`).
- `track_flags.py` — `TrackFlags`: track flags (forced, SDH, commentary, ...), their filename tokens and the
  `--with`/`--without` filter.
- `formats/scrub.py` — makes a small, redacted copy of a PGS track so a reporter can share a bug sample.
- `formats/` does not know the media files and their names. Each function gets a `name` for its log messages.
- `diagnostics.py` — environment checks (package versions) for bug reports. Each source, OCR engine, and
  post-processor adds its own checks with a `check` classmethod, e.g. `TesseractEngine.check`.
- `errors.py` — `PgsripError`: the base of the errors of pgsrip: `SourceError`, `CorruptDataError`, `OcrError`
  (and `TessdataError`), `ScrubError`.
- `utils.py` — `format_time`, `default_workers`, `cache_dir` (with appdirs), `is_writable`.
