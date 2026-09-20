# Changelog

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
