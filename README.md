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

Nothing to do: pgsrip downloads the language data it needs on the first rip
and reuses it afterwards. See [Tesseract language data](#tesseract-language-data).

To install every language upfront instead:

    $ git clone https://github.com/tesseract-ocr/tessdata_best.git
    export TESSDATA_PREFIX=~/tessdata_best

If you prefer to build the docker image Build Docker:

    $ git clone https://github.com/ratoaq2/pgsrip.git
    cd pgsrip
    docker build . -t pgsrip

## Tesseract language data

Each subtitle language needs its own tesseract `.traineddata` file. pgsrip
looks for the languages of the subtitles it collected and downloads the ones
tesseract does not have yet, before it starts to rip:

    $ pgsrip mymedia.mks
    1 PGS subtitle collected from 1 file
    Downloading tesseract data for por...
    Ripping subtitles  [####################################]  100%  mymedia.mks [3:pt-BR]
    1 PGS subtitle ripped from 1 file

The data is downloaded only once and is used by every later rip. It is stored
in the first writable directory of:

  - `--tessdata-dir` or the `PGSRIP_TESSDATA_DIR` environment variable
  - the `TESSDATA_PREFIX` environment variable
  - `%LOCALAPPDATA%\pgsrip\tessdata` (Windows),
    `~/Library/Caches/pgsrip/tessdata` (macOS) or
    `~/.cache/pgsrip/tessdata` (Linux)

Languages that tesseract already has are never downloaded, and a subtitle is
always ripped with the data that tesseract finds first. To turn the download
off and use only the installed languages, use `--no-tessdata-download`.

Data comes from <https://github.com/tesseract-ocr/tessdata_best>. Use
`--tessdata-repository fast` (or `PGSRIP_TESSDATA_REPO=fast`) for the smaller
and quicker models of <https://github.com/tesseract-ocr/tessdata_fast>, or set
`PGSRIP_TESSDATA_URL` to the base URL of a mirror.

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

Using docker:

    $ docker run -it --rm -v /medias:/medias -u $(id -u username):$(id -g username) ratoaq2/pgsrip -l en -l de -l pt-BR -l pt /medias
    11 PGS subtitles collected from 9 files / 2 files filtered out
    Ripping subtitles  [####################################]  100%  /medias/mymedia.mkv [4:en]
    11 PGS subtitles ripped from 9 files

### API

``` python
from pgsrip import pgsrip, Mkv, Options
from babelfish import Language

media = Mkv('/subtitle/path/mymedia.mkv')
options = Options(languages={Language('eng')}, overwrite=True, one_per_lang=False)
pgsrip.rip(media, options)
```
