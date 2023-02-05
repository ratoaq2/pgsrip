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
