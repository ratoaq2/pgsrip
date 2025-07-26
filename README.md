# PGSRip

Rip your PGS subtitles.

[![Latest
Version](https://img.shields.io/pypi/v/pgsrip.svg)](https://pypi.python.org/pypi/pgsrip)

[![License](https://img.shields.io/github/license/ratoaq2/pgsrip.svg)](https://github.com/ratoaq2/pgsrip/blob/master/LICENSE)

  - Project page
    <https://github.com/ratoaq2/pgsrip>

**PGSRip** is a command line tool that allows you to extract and convert
PGS subtitles into SRT format. This tool requires MKVToolNix and
tesseract-ocr and tessdata (<https://github.com/tesseract-ocr/tessdata>
or <https://github.com/tesseract-ocr/tessdata_best>)

## Installation

pgsrip:

    $ pip install pgsrip

MKVToolNix:

    [Linux/WSL - Ubuntu/Debian]
    $ sudo apt-get install mkvtoolnix

    [Windows/Chocolatey]
    $ choco install mkvtoolnix

tesseract:

PPA is used to install latest tesseract 5.x. Skip PPA repository if you decide to stick with latest official Debian/Ubuntu package

    [Linux/WSL - Ubuntu/Debian]
    $ sudo add-apt-repository ppa:alex-p/tesseract-ocr5
    $ sudo apt update
    $ sudo apt-get install tesseract-ocr

    [Windows/Chocolatey]
    $ choco install tesseract-ocr


tessdata:

    $ git clone https://github.com/tesseract-ocr/tessdata_best.git
    export TESSDATA_PREFIX=~/tessdata_best

If you prefer to build the docker image Build Docker:

    $ git clone https://github.com/ratoaq2/pgsrip.git
    cd pgsrip
    docker build . -t pgsrip

## Usage

### CLI

Rip from a .mkv:

    $ pgsrip mymedia.mkv
    3 PGS subtitles collected from 1 file
    Ripping subtitles  [####################################]  100%  mymedia.mkv [5:de]
    3 PGS subtitles ripped from 1 file

Rip from a .mks:

    $ pgsrip mymedia.mks
    3 PGS subtitles collected from 1 file
    Ripping subtitles  [####################################]  100%  mymedia.mks [3:pt-BR]
    3 PGS subtitles ripped from 1 file

Rip from a .sup:

    $ pgsrip mymedia.en.sup
    1 PGS subtitle collected from 1 file
    Ripping subtitles  [####################################]  100%  mymedia.en.sup
    1 PGS subtitle ripped from 1 file

Rip from a folder path:

    $ pgsrip -l en -l pt-BR ~/medias/
    11 PGS subtitles collected from 9 files / 2 files filtered out
    Ripping subtitles  [####################################]  100%  ~/medias/mymedia.mkv [4:en]
    11 PGS subtitles ripped from 9 files

#### Subtitle Type Filtering

PGSRip supports filtering subtitles by type based on MKVToolNix metadata:

**Filter by specific types:**

    # Extract only FULL subtitles (regular, non-forced, non-SDH)
    $ pgsrip --full-only mymedia.mkv

    # Extract only FORCED subtitles (for foreign language text/signs)
    $ pgsrip --forced-only mymedia.mkv

    # Extract only SDH subtitles (for Deaf and Hard of hearing)
    $ pgsrip --sdh-only mymedia.mkv

**Filter by combined types:**

    # Extract FULL and FORCED subtitles together
    $ pgsrip --forced-included mymedia.mkv

    # Extract FULL and SDH subtitles together
    $ pgsrip --sdh-included mymedia.mkv

    # Extract FULL, FORCED and SDH subtitles together
    $ pgsrip --all-included mymedia.mkv

**Advanced examples:**

    # Extract forced subtitles in multiple languages
    $ pgsrip --forced-only -l en -l fr -l de ~/Movies/

    # Extract full French and forced English subtitles
    $ pgsrip --forced-included -l fr -l en mymedia.mkv

    # Extract all subtitle types (full, forced, SDH) in multiple languages
    $ pgsrip --all-included -l fr -l en mymedia.mkv

**Output file naming:**

- Files are named with format: `<movie>.<language>.<type>.srt`
- Examples: `movie.en.forced.srt`, `movie.fr.full.srt`, `movie.en.sdh.srt`

**Subtitle type detection:**

- **FORCED**: Detected via MKV `forced_track` metadata
- **SDH**: Auto-detected from track names containing "SDH", "CC", "Hearing Impaired", or "Deaf"
- **FULL**: Regular subtitles that are neither forced nor SDH

Using docker:

    $ docker run -it --rm -v /medias:/medias -u $(id -u username):$(id -g username) ratoaq2/pgsrip -l en -l de -l pt-BR -l pt /medias
    11 PGS subtitles collected from 9 files / 2 files filtered out
    Ripping subtitles  [####################################]  100%  /medias/mymedia.mkv [4:en]
    11 PGS subtitles ripped from 9 files

### API

    from pgsrip import pgsrip, Mkv, Options, SubtitleTypeFilter
    from babelfish import Language

    media = Mkv('/subtitle/path/mymedia.mkv')
    options = Options(languages={Language('eng')},
                      overwrite=True,
                      one_per_lang=False,
                      subtitle_type_filter=SubtitleTypeFilter.FORCED_ONLY)
    pgsrip.rip(media, options)

## Technical Details

### Subtitle Type Detection

PGSRip automatically detects subtitle types based on MKVToolNix metadata:

- **FORCED**: Detected via the `forced_track` property in MKV metadata
- **SDH**: Detected by analyzing track names for keywords like "SDH", "Hearing Impaired", "Deaf", or "CC"
- **FULL**: Regular subtitles that are neither forced nor SDH, or explicitly marked as "Full"/"Complete"

The filtering options work as follows:

- `--full-only`: Only FULL subtitles (excludes forced and SDH)
- `--forced-included`: FULL + FORCED subtitles
- `--forced-only`: Only FORCED subtitles
- `--sdh-included`: FULL + SDH subtitles
- `--sdh-only`: Only SDH subtitles
