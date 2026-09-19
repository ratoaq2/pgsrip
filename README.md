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

When a path is not ripped, pgsrip prints the reason:

    $ pgsrip -l fr ~/medias/
    ~/medias/mymedia.mkv ignored: mkvmerge not found, install MKVToolNix and make sure that it is in the PATH
    0 PGS subtitle collected from 0 file / 1 path ignored

Use `-vvv` to also see the files that the `--language` and `--age` filters
removed.

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

## Reporting a bug

When a subtitle cannot be ripped, pgsrip prints the error and the commands that
collect what a bug report needs:

    $ pgsrip mymedia.mkv
    1 PGS subtitle collected from 1 file
    0 PGS subtitle ripped from 1 file

    1 PGS subtitle could not be ripped:
      mymedia.en.mkv: <ValueError> [max() iterable argument is empty]
    To report this, run:
      pgsrip scrub mymedia.mkv
      pgsrip --log-file pgsrip.log mymedia.mkv
    The scrubbed subtitle holds no image, only what is needed to reproduce the error.
    Attach it to a new issue: https://github.com/ratoaq2/pgsrip/issues

### Environment

`pgsrip doctor` shows what is installed. Add its output to the bug report:

    $ pgsrip doctor
    pgsrip                       0.1.13
    python                       3.13.1 (/usr/bin/python3)
    platform                     Linux-6.8.0-generic-x86_64
    mkvmerge                     mkvmerge v90.0 (/usr/bin/mkvmerge)
    mkvextract                   mkvextract v90.0 (/usr/bin/mkvextract)
    tesseract                    5.5.1 (/usr/bin/tesseract)
    tesseract languages          eng, osd, por
    ...

    Everything that pgsrip needs is installed.

The command exits with code 1 if something is missing, and prints how to
install it.

### Subtitle sample

A PGS subtitle holds two different things: the segments that say when and where
a subtitle is shown, and the images that hold the text. Only the images hold the
content of your media, and most bugs are in the first part.

`pgsrip scrub` writes a copy of your PGS subtitles without the images:

    $ pgsrip scrub mymedia.mkv
    pgsrip-a25b6c81.en.sup written: 1043/1043 display sets, 1043/1043 images redacted, 412088 bytes
    The scrubbed files hold no subtitle image, only timing, layout and palettes.
    Attach them to a new issue: https://github.com/ratoaq2/pgsrip/issues

The result is a real `.sup` file. pgsrip reads it through the very same code, so
it reproduces the bug, but there is no text to read on it and it is much smaller
than the original. The file name is a hash of the name of your media file. Use
`--keep-name` to keep the original name.

If the bug is about the OCR itself, an empty image reproduces nothing. There are
two other options:

    $ pgsrip scrub --redact synthetic mymedia.mkv
    $ pgsrip scrub --keep-images 412 mymedia.mkv

`--redact synthetic` draws placeholder text in each subtitle image, with the
same size and the same palette as the original. `--keep-images` keeps the
original image of the given display sets only, e.g. `412` or `400-420`. A few
subtitle lines are usually enough, and they stay small.

`--only 0-99` writes only the given display sets, to cut a long subtitle short.

### Debug log

`--debug` prints debug messages to the console. `--log-file` writes the same
messages to a file, so you can attach it to a bug report:

    $ pgsrip --log-file pgsrip.log mymedia.mkv
    1 PGS subtitle collected from 1 file
    Ripping subtitles  [####################################]  100%  mymedia.mkv [4:en]
    1 PGS subtitle ripped from 1 file
    Debug log written to pgsrip.log

The log starts with the pgsrip, Python and tesseract versions. It contains the
paths of the files that were ripped. Remove or replace them if you do not want
to share the names of your media files.
