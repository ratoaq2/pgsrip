# Changelog

## Unreleased

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
    overrides `-w/--max-workers` for tesseract only
  - Breaking: the tessdata options of `rip` and `doctor` are now
    `--tesseract-dir`, `--tesseract-repository` and `--no-tesseract-download`
  - Breaking: library: `Options(engines=[...])` sets the OCR engines. The
    `confidence`, `tesseract_*` and `max_workers` arguments of `Options` move
    to `pgsrip.engines.tesseract.TesseractEngine`. The `tessdata_*` and
    `download_tessdata` arguments move to `TesseractEngine(tessdata=Tessdata(...))`.
    `TesseractEngineMode` and `TesseractPageSegmentationMode` move to
    `pgsrip.engines.tesseract`
  - New: a configuration file with the default values of the `rip` options.
    pgsrip reads `config.{json,yml,yaml}` in the user configuration folder,
    `pgsrip.{json,yml,yaml}` in the current folder, and each `--config` file.
    A section groups the options with the same prefix, e.g.
    `tesseract: {threshold: 90}` for `--tesseract-threshold`
  - Breaking: the cleanit rules file option `-c/--config` is now
    `--cleanit-config`. `--config` is now the pgsrip configuration file
  - New: a chain of post-processors changes the text after the OCR engines.
    cleanit is the default post-processor. Use `--post-processor` more than
    one time for a chain, and `--no-post-process` to keep the text of the OCR
    engines. Other packages can add a post-processor with a
    `pgsrip.postprocessors` entry point
  - New: `--cleanit-tag` is the long name of `-t/--tag`. The `cleanit` section
    of the configuration file sets `config` and `tag`
  - New: `--keep-temp-files` also keeps `ocr.json` and `cues.json`: the text,
    the confidence and the engine of each cue, before and after the
    post-processors
  - Breaking: library: `Options(config_path=..., tags=...)` is now
    `Options(post_processors=[CleanitPostProcessor(config_path, tags)])`, from
    `pgsrip.cleanit`. `Options.config` and `Options.tags` are removed.
    `PgsToSrtRipper.rip()` returns the cues, and `pgsrip.ripper.create_srt`
    makes the SRT from them
  - Breaking: plug-ins: `pgsrip.ripper.EngineOption` is now
    `pgsrip.plugin.PluginOption`
  - Breaking: the modules move into sub-packages. Plug-ins import
    `OcrEngine`, `OcrEngineFactory` and `OcrError` from `pgsrip.engines.base`.
    The OCR engines are in `pgsrip.engines`
  - Fix: a track with 20 or more cues that tesseract could not read made the
    rip run forever

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
