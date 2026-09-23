# Changelog

## Unreleased

  - Fix: a `.sup` or `.mks` file with a 3-letter language code in its name,
    e.g. `movie.fre.sup`, failed with `FileNotFoundError` and was not ripped
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
