# Changelog

## Unreleased

  - New: `--engine openai` reads the subtitle images with a vision model
    behind an OpenAI-compatible API, for example llama.cpp with GLM-OCR. The
    `--openai-*` options, or the `openai` section of the configuration file,
    set it up. This engine is experimental. Based on #148 by @socram8888
  - Breaking: `-w/--max-workers` is now `-w/--workers`, and the
    `max_workers` configuration key is now `workers`
  - Breaking: `-v` lists all the ignored paths, and `-vv` also lists the
    filtered-out paths. Before, it was `-vv` and `-vvv`
  - Breaking: `scrub` names its copies with a free name `.track2`, `.track3`.
    Before, it was `.track0`, `.track1`
  - Breaking: pgsrip rips an MKV track with no language as `und`, like a
    `.sup` file with no language. Before, it skipped the track
  - New: `--tesseract-confidence` (0 to 100, default 65) sets the word
    confidence of the first tesseract pass. `--tesseract-width` (10240 to
    31744, default 31744) sets the maximum width of the images that go to
    tesseract
  - New: `rip --help` shows the default of each engine and post-processor
    option, and the environment variables `PGSRIP_TESSDATA_DIR`,
    `PGSRIP_TESSDATA_REPO`, and `PGSRIP_RAPIDOCR_DIR`
  - Changed: `--keep-temp-files` writes `null` in `cues.json` for a missing
    time. Before, it wrote the text `None`
  - Changed: `doctor` also shows the versions of appdirs and pyyaml
  - Fixed: a second run does not rip the duplicate of a track that it ripped
    before, for example `movie.en.track2.srt` next to `movie.en.srt`
  - Fixed: 2 tracks of the same language that differ only in the default or
    original flag do not write the same file. Without `--all`, pgsrip rips
    only the first. With `--all`, the second is `.track2`. Before, with
    `--force`, the second track replaced the file of the first
  - Fixed: a corrupted display set is logged and dropped. Before, the whole
    track failed. This applies to an unknown segment type, a display set with
    no composition segment or with no palette, a value that does not exist,
    and a composition or window segment that is too short
  - Fixed: the palette of a subtitle image is the palette that its
    composition segment names. Before, pgsrip joined all the palettes of the
    display set
  - Fixed: tesseract: a cue where tesseract finds no word goes to the next
    pass and to the next engine, and the "not ripped" warning lists it.
    Before, the cue was dropped with no message
  - Fixed: tesseract: a subtitle image wider than the composite width does
    not stop the rip of the track
  - Fixed: `rip` and `scrub` exit with code 1 when the `--log-file` cannot be
    opened
  - Fixed: `scrub` exits with code 1 when a scrub fails, and when it finds no
    media. Before, it exited with 0
  - Fixed: `scrub` does not write a scrubbed file that pgsrip cannot read
    back. It shows the error
  - Fixed: `--age ''` is an error. Before, it was accepted and filtered
    nothing
  - Fixed: `--language` does not keep a media whose only track of the
    language is disabled
  - Fixed: `--debug` and `--log-file` log each line one time when a script
    runs 2 commands in one process. The log file closes when the command ends
  - Fixed: the help of `-a`, `-A`, `-f`, `--all`, and `--keep-temp-files` tells
    what the option does
  - Breaking: library: `pgsrip.core` merges into `pgsrip.api`. `pgsrip`
    exports `scan`, `ScanResult`, `Skipped`, `pending`, `prepare`, `rip`,
    `Options`, `Media`, `Subtitle`, `Workspace`, and `PgsripError`.
    `from pgsrip import pgsrip` goes away
  - Breaking: library: `scan_path` is now `scan`, and returns a
    `ScanResult(media, filtered_out, ignored)`. Each skipped path is a
    `Skipped(path, reason)`: `ScannedPath` and `get_reason` go away
  - Breaking: library: `rip_pgs` is now `rip(subtitle, options)`. It raises
    the error that stops the rip, in place of the `on_error` callback.
    `rip(media)` goes away. Call `prepare(subtitles, options, reporter)`
    before `rip`: it gets the OCR engines ready for the languages of the
    subtitles. Without it, `rip` does not use RapidOCR
  - Breaking: library: `Pgs` is now `Subtitle(track, source_path, output_base,
    extraction, workspace)`. `Subtitle.read()` gives the PGS data. It does not
    decode the data and has no `items`. `Pgs.pending_writers` is now
    `pgsrip.api.pending_writers`
  - Breaking: library: `Media.get_pgs_medias` is now
    `Media.subtitles(options, workspace)`. The selection does not look at the
    output files: `pgsrip.api.pending` does. `Media` and `Extraction` move
    from `pgsrip.sources.base` to `pgsrip.media`. `Media.media_path` is now
    `Media.path`
  - Breaking: library: `Options` is a frozen dataclass of plain values. Its
    fields have the names of the CLI options: `force` (was `overwrite`),
    `all_tracks` (was `one_per_lang`, inverted), `with_flags` and
    `without_flags` (were `include_flags` and `exclude_flags`). `languages` is
    a `frozenset`. None in `engines`, `post_processors`, or `writers` means the
    default. `Options` is not a context manager: `Workspace` (from
    `pgsrip.media`) holds the temporary directory of the run, and
    `Workspace(keep=True)` replaces `keep_temp_files`
  - Breaking: library: `Track` has one `flags` field (a `TrackFlags`) in place
    of one field for each flag, and no `external` field.
    `TrackFlags.version` is now the boolean `TrackFlags.alternate`.
    `TrackFlags.matches(with_flags, without_flags)`: the arguments were
    `include` and `exclude`
  - Breaking: library: `MediaPath.translate` is now `MediaPath.replace`, and
    it also takes `base_path`. `MediaPath.m_age` is now `MediaPath.age`, and
    `MediaPath.track_id` is now `MediaPath.track_number`
  - Breaking: library: all the errors of pgsrip are a `PgsripError` (from
    `pgsrip.errors`): `SourceError`, `CorruptDataError` (from
    `pgsrip.formats.pgs`, for a track with no subtitle image, before a
    `ValueError`), `OcrError`, `TessdataError`, and `ScrubError`. `Media`
    raises `SourceError` (from `pgsrip.sources.base`) when it cannot read the
    file: for an unsupported extension, when the tool is not installed, and
    when the tool fails. `Source.missing` is now `Source.install_hint`
  - Breaking: library: `pgsrip.formats.pgs` has new names. `PgsReader.decode`
    and `PgsReader.read_segments` are now the functions `read_display_sets`
    and `read_segments`. `BaseSegment` is now `Segment`, `Palette` is now
    `PaletteEntry`, and `PgsSubtitleItem` (from `pgsrip.media`) is now `Item`.
    `PgsSubtitleItem.create_items` is now `read_items`, and `Item.box` replaces
    `shape`. `PgsImage` is a `NamedTuple`, with module functions in place of
    its class methods. `pgsrip.utils.from_hex` is now
    `pgsrip.formats.pgs.to_int`
  - Breaking: library: `read_segments`, `read_display_sets`, `read_items`,
    `scrub_data`, and `verify` take a `name` (a `str`) for their log
    messages, not a `MediaPath`. `output_path` and `default_name` move from
    `pgsrip.formats.scrub` to `pgsrip.cli`
  - Breaking: library: names with no `get_` prefix: `tesseract_code`,
    `required_codes`, and `config_arg` (in `pgsrip.engines.tessdata`).
    `required_codes(languages)` has no `psm_value`, and `OSD_CODE` and
    `OSD_PAGE_SEGMENTATION_MODES` go away. `is_writable` moves from
    `pgsrip.engines.tessdata` to `pgsrip.utils`. `get_user_cache_dir` goes
    away: `pgsrip.utils.cache_dir(name)` gives a directory in the user cache
    directory of pgsrip, with appdirs
  - Breaking: library: `TesseractEngine` has no `oem` and `psm` arguments, and
    `TesseractEngineMode` and `TesseractPageSegmentationMode` go away: pgsrip
    always uses `--oem 1 --psm 6`. `FullImage` is now `Composite`, and
    `ImageArea` is now `Row`. `FullImage.data` is now `Composite.image`,
    `FullImage.items` is now `Composite.placed`, and `ImageArea.shape` is now
    `Row.box`. `TsvData` is now `TsvResult`, and `TsvDataItem` is now
    `TsvWord`. `TsvWord.matches` and `TsvResult.select` take a `Box`
  - Breaking: library: `TesseractEngine`, `Tessdata`, and `RapidOcrEngine` do
    not read the environment variables. Only the command line reads them.
    `Tessdata(directory=)` is now `Tessdata(data_dir=)`, and `Tessdata` has
    no `timeout`. `Tessdata.ensure(codes, on_download)`: the second argument
    was `reporter`. `RapidOcrEngine(directory=)` is now
    `RapidOcrEngine(model_dir=)`, and `RapidOcrEngine.model_dir` (the
    directory that it uses) is now `RapidOcrEngine.target_dir`
  - Breaking: library: `RapidOcrEngine` fields `recognizers_by_language`,
    `recognizers_by_model`, and `failed_models` (were `languages`,
    `recognizers`, and `failed`). `ctc` is now `ctc_decode`
  - Breaking: library: `ENGINES` and `ENGINE_ENTRY_POINTS` move from
    `pgsrip.cli.plugins` to `pgsrip.engines`, `POST_PROCESSORS` and
    `POST_PROCESSOR_ENTRY_POINTS` to `pgsrip.postprocessors`, `AUTO` and
    `AUTO_ENGINES` to `pgsrip.engines.auto`. `check_auto()` is now
    `AutoEngine.check(settings)`. `AutoEngine` needs its 2 engines, and
    `AutoEngine.from_engines(tesseract, rapidocr)` checks their type
  - Breaking: plug-in API: `OcrEngine.recognize(items, language, debug_dir)`
    returns one `Reading(text, confidence, doubtful)` (from
    `pgsrip.engines.base`) for each item. It does not change the items: `Item`
    has no `text`, `doubtful`, `confidence`, and `place`. `debug_dir` is None
    without `--keep-temp-files`. `PgsToSrtRipper` (`pgsrip.ripper`) is now the
    function `read_cues(items, language, engines, debug_dir)` in
    `pgsrip.engines.chain`. It returns the cues and the time of each engine
  - Breaking: plug-in API: `Item` has plain values: `start`, `end`, `image`,
    `x_offset`, and `y_offset` are never None. `read_items` makes the items:
    `Item(index, start, end, image, x_offset, y_offset, name)`. `Item` has no
    `media_path` and no `language`. `PgsSubtitleItem.auto_fix` and
    `pgsrip.utils.pairwise` go away
  - Breaking: plug-in API: `Cue` moves from `pgsrip.ripper` to `pgsrip.cue`.
    `Cue.start` and `Cue.end` are `int`
  - Breaking: plug-in API: `PostProcessor.process(cues, track)` and
    `Writer.write(path, cues, track, encoding)` get the `Track` (id, name,
    language, flags). Before, they were `process(pgs, cues)` and
    `write(path, pgs, cues, encoding)`
  - Breaking: plug-in API: `OcrEngineFactory.from_settings(settings)` has no
    `workers` argument, like `PostProcessorFactory.from_settings`. An engine
    that uses workers declares a `workers` option: with no value, it gets the
    `-w` value. pgsrip does not add `--<engine>-workers` to the other
    engines. The `check(settings)` classmethod is required for both kinds
  - Breaking: plug-in API: an OCR engine factory raises `ValueError` for a
    wrong setting, like a post-processor factory. Before, it was `OcrError`
  - Fixed: library: a `Subtitle` releases its extracted track at the end of
    its `with` block. A second `rip` of the same subtitle extracts the track
    again. Before, it read a removed file. The next read of another track
    does not extract a finished track again, and leaves no temporary
    directory
  - Fixed: library: after a rip, the environment of the process is the same as
    before. Before, tesseract left `OMP_THREAD_LIMIT=1` in `os.environ`
  - New: `--format` selects the output format. `srt` is the default and the
    only format. Use it more than one time to write more than one file. When
    the file of one format is missing, pgsrip writes only that file
  - Breaking: `-A/--srt-age` is now `-A/--output-age`, and the `srt_age`
    configuration key is now `output_age`
  - Breaking: library: `Options(writers=[...])` sets the output writers. The
    default is `[SrtWriter()]`, from `pgsrip.writers.srt`. `Options.srt_age` is
    now `Options.output_age`, and `Pgs.srt_path` is now
    `Subtitle.output_path(writer)`
  - New: a chain of OCR engines. Use `--engine` more than one time. Each next
    engine reads the cues that the engines before it could not read or are not
    sure of. `--tesseract-threshold` (default 80) sets which tesseract cues go
    to the next engine
  - New: other packages can add an OCR engine with a `pgsrip.engines` entry
    point. The engine declares its options: pgsrip adds them to `rip` as
    `--<engine>-*` options and reads them from the `<engine>` section of the
    configuration file. The engine tells the languages that it can read
    (`supports`). The chain skips an engine that cannot read the language of
    a track. When no engine can read it, the track fails
  - New: tesseract cannot read a language when the tesseract program is not
    found, or when its data is not installed and cannot be downloaded. A
    failed download does not stop the downloads of the other languages
  - New: the `rapidocr` OCR engine (`--engine rapidocr`). It reads the text
    with the PaddleOCR models on ONNX Runtime, and needs no program on the
    system. Install it with the `rapidocr` extra:
    `pip install "pgsrip[rapidocr]"`. The extra needs ONNX Runtime wheels:
    it does not install on musl Linux. It
    downloads the model of each language before the rip starts. Options:
    `--rapidocr-threshold`, `--rapidocr-model`, `--rapidocr-border`,
    `--rapidocr-batch`, `--rapidocr-dir`, `--no-rapidocr-download` and
    `--rapidocr-workers`
  - Changed: the default OCR engine is `auto`. For each language, it uses
    tesseract when tesseract can read the language, else RapidOCR. pgsrip
    can now rip with no tesseract program on the system. `doctor` shows the
    engine of auto. A missing tesseract is not a `doctor` failure when
    RapidOCR can rip
  - New: the Docker image has the RapidOCR PP-OCRv6 small model, in the
    `/usr/src/rapidocr` volume (`PGSRIP_RAPIDOCR_DIR`)
  - Fixed: `rip` exits with code 1 when a subtitle could not be ripped
  - Fixed: when tesseract is not found, `rip` shows the warning one time only
  - New: `doctor` shows the checks of every OCR engine. It accepts `--config`
    and the `--<engine>-*` options
  - New: `--tesseract-workers` sets the number of tesseract processes. It
    overrides `-w/--workers` for tesseract only
  - Breaking: the tessdata options of `rip` and `doctor` are now
    `--tesseract-dir`, `--tesseract-repository` and `--no-tesseract-download`
  - Breaking: library: `Options(engines=[...])` sets the OCR engines. The
    `confidence`, `tesseract_*` and `max_workers` arguments of `Options` move
    to `pgsrip.engines.tesseract.TesseractEngine`. The `tessdata_*` and
    `download_tessdata` arguments move to `TesseractEngine(tessdata=Tessdata(...))`
  - New: a configuration file with the default values of the `rip` options.
    pgsrip reads `config.{json,yml,yaml}` in the user configuration folder,
    `pgsrip.{json,yml,yaml}` in the current folder, and each `--config` file.
    A section groups the options with the same prefix, e.g.
    `tesseract: {threshold: 90}` for `--tesseract-threshold`
  - Breaking: the cleanit rules file option `-c/--config` is now
    `--cleanit-config`. `--config` is now the pgsrip configuration file
  - New: a chain of post-processors changes the text after the OCR engines.
    cleanit is the default post-processor. Use `--post-processor` more than
    one time for a chain, and `--no-post-processor` to keep the text of the OCR
    engines. Other packages can add a post-processor with a
    `pgsrip.postprocessors` entry point
  - New: `--cleanit-tag` is the long name of `-t/--tag`. The `cleanit` section
    of the configuration file sets `config` and `tag`
  - New: `--keep-temp-files` also keeps `ocr.json` and `cues.json`: the text,
    the confidence and the engine of each cue, before and after the
    post-processors
  - Breaking: library: `Options(config_path=..., tags=...)` is now
    `Options(post_processors=[CleanitPostProcessor(config_path, tags)])`, from
    `pgsrip.postprocessors.cleanit`. `Options.config` and `Options.tags` are
    removed. `read_cues` returns the cues, and the writers of
    `pgsrip.writers` write the files
  - Breaking: plug-ins: `pgsrip.ripper.EngineOption` is now
    `pgsrip.plugin.PluginOption`
  - Breaking: the modules move into sub-packages. Plug-ins import
    `OcrEngine`, `OcrEngineFactory` and `OcrError` from `pgsrip.engines.base`.
    `PostProcessor` and `PostProcessorFactory` from
    `pgsrip.postprocessors.base`. The OCR engines are in `pgsrip.engines`, and
    the post-processors are in `pgsrip.postprocessors`
  - Breaking: library: `Mkv` and `Sup` are removed. Use
    `Media('/path/mymedia.mkv')`: it finds the source that reads the file
  - Changed: `--with` and `--without` also apply to `.sup` files. The flags
    come from the file name, for example `mymedia.en.forced.sup`
  - Changed: pgsrip extracts all the selected tracks of a file with one
    `mkvextract` call. Before, each track read the full file again
  - Fixed: a track that pgsrip did not rip left its temporary directory
  - Changed: one temporary directory `pgsrip-XXXX` for each run, with one
    directory for each track in it. Library: use
    `with Workspace() as workspace:` to remove it at the end
  - Changed: `-l/--language` looks only at the languages of the PGS tracks of
    a media, not at the audio and video tracks. A media with no PGS track in
    the selected languages is now filtered out, with its reason
  - Fixed: a track with 20 or more cues that tesseract could not read made the
    rip run forever
  - Fixed: `pgsrip` requires click 8.5.0 or later, so `click.ParamType` stays
    subscriptable

## 0.2.1

**release date:** 2026-09-23

  - Fix: a `.sup` or `.mks` file with a 3-letter language code in its name,
    e.g. `movie.fre.sup`, failed with `FileNotFoundError` and was not ripped
  - Fix: `pgsrip scrub` could write the scrubbed file over its source `.sup`
    file. It now adds `.track0` to the name
  - Fix: a long subtitle track with wide images failed with
    `Image too large` and was not ripped
  - Fix: a subtitle track with images split over 3 or more segments, or with
    palette updates, failed with `0 is not a valid ObjectSequenceType` or
    `IndexError` and was not ripped
  - Rip faster: run several tesseract processes in parallel, decode the
    subtitle images faster, and OCR only the part of each image that holds
    text
  - `-w/--max-workers` now sets the number of tesseract processes that run in
    parallel. The default is the number of CPUs, at most 4

## 0.2.0

**release date:** 2026-09-21

  - Name subtitle tracks after their flags instead of an unstable counter,
    e.g. `movie.en.sdh.srt`, `movie.pt-BR.forced.srt` instead of
    `movie-1.en.srt`
  - Add `--with`/`--without` to select tracks by flag (`forced`, `sdh`, `cc`,
    `commentary`, `descriptive`, `full`, ...)
  - Add `--one-per-language` to keep only one track per language, ignoring
    flags
  - `pgsrip scrub` names its output the same way as a ripped `.srt`
  - Fix: a second subtitle track for an already-ripped language could be
    skipped by mistake, because the overwrite check and the file actually
    written did not agree on its name

## 0.1.13

**release date:** 2026-09-20

  - Add a `doctor` command to check the environment (tesseract, mkvtoolnix,
    language data)
  - Add a `scrub` command to share a subtitle sample without its images
  - Add a `--log-file` option to write a full debug log
  - Auto-download missing tesseract language data
  - Report why a path is ignored or filtered out
  - Tell the user how to report a subtitle that failed to rip
  - Fix: upgrade cleanit to stop release tags being read as languages
  - Fix: do not repeat the language in the scrubbed file name
  - Migrate project tooling to uv, ruff, and strict mypy; support Python
    3.11 to 3.14

## 0.1.12

**release date:** 2025-07-26

  - Fix: `WindowDefinitionSegment` could have 0 windows
  - Update supported Python versions
  - Update dependencies

## 0.1.11

**release date:** 2024-06-23

  - Maintenance release: dependency updates only

## 0.1.10

**release date:** 2024-06-22

  - Publish arm64 Docker images
  - Add setuptools as an explicit dependency
  - Update dependencies

## 0.1.9

**release date:** 2023-03-03

  - Fix: display sets wrongly grouped together

## 0.1.8

**release date:** 2023-02-12

  - Improve OCR accuracy: add borders, increase gaps, and use PSM 6 for
    uniform text block detection

## 0.1.7

**release date:** 2023-02-12

  - Fix: handle multi-part ODS segments
  - Add an OCR engine mode option
  - Increase text gap and improve debug files

## 0.1.6

**release date:** 2023-02-05

  - Fix the Docker image build

## 0.1.5

**release date:** 2023-02-05

  - Use the latest tesseract version whenever possible
  - Add a `--version` option and report the tesseract version
  - Add an option to keep temporary files after ripping
  - Add Windows installation instructions

## 0.1.4

**release date:** 2023-01-09

  - Fix: wrong expected language passed to trakit

## 0.1.3

**release date:** 2023-01-09

  - Improve language detection using trakit

## 0.1.2

**release date:** 2022-12-31

  - Fix: confidence values are sometimes floats as strings

## 0.1.1

**release date:** 2021-04-08

  - Several fixes to make PGS parsing more resilient to errors and
    corruption

## 0.1

**release date:** 2021-03-21

  - Initial release
