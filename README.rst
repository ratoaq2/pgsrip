PGSRip
==========
Rip your PGS subtitles.

.. image:: https://img.shields.io/pypi/v/pgsrip.svg
    :target: https://pypi.python.org/pypi/pgsrip
    :alt: Latest Version

.. image:: https://travis-ci.org/ratoaq2/pgsrip.svg?branch=master
   :target: https://travis-ci.org/ratoaq2/pgsrip
   :alt: Travis CI build status

.. image:: https://img.shields.io/github/license/ratoaq2/pgsrip.svg
   :target: https://github.com/ratoaq2/pgsrip/blob/master/LICENSE
   :alt: License

:Project page: https://github.com/ratoaq2/pgsrip

**PGSRip** is a command line tool that allows you to extract and convert
PGS subtitles into SRT format. This tool requires MKVToolNix and
tesseract-ocr and tessdata (https://github.com/tesseract-ocr/tessdata
or https://github.com/tesseract-ocr/tessdata_best)

Installation
------------
pgsrip::

    $ pip install pgsrip

MKVToolNix::

    $ sudo apt-get install mkvtoolnix

tesseract::

    $ sudo apt-get install tesseract-ocr

tessdata::

    $ git clone https://github.com/tesseract-ocr/tessdata_best.git
    export TESSDATA_PREFIX=~/tessdata_best


If you prefer to build the docker image
Build Docker::

    $ git clone https://github.com/ratoaq2/pgsrip.git
    cd pgsrip
    docker build . -t pgsrip

Usage
-----
CLI
^^^
Rip from a .mkv::

    $ pgsrip mymedia.mkv
    3 PGS subtitles collected from 1 file
    Ripping subtitles  [####################################]  100%  mymedia.mkv [5:de]
    3 PGS subtitles ripped from 1 file

Rip from a .mks::

    $ pgsrip mymedia.mks
    3 PGS subtitles collected from 1 file
    Ripping subtitles  [####################################]  100%  mymedia.mks [3:pt-BR]
    3 PGS subtitles ripped from 1 file

Rip from a .sup::

    $ pgsrip mymedia.en.sup
    1 PGS subtitle collected from 1 file
    Ripping subtitles  [####################################]  100%  mymedia.en.sup
    1 PGS subtitle ripped from 1 file


Rip from a folder path::

    $ pgsrip -l en -l pt-BR ~/medias/
    11 PGS subtitles collected from 9 files / 2 files filtered out
    Ripping subtitles  [####################################]  100%
    268 subtitles saved / 155 subtitles unchanged


Using docker::

    $ docker run -it --rm -v /medias:/medias -u $(id -u username):$(id -g username) pgsrip -l en -l de -l pt-BR -l pt /medias
    11 PGS subtitles collected from 9 files / 2 files filtered out
    Ripping subtitles  [####################################]  100%


API
^^^
.. code:: python

    from pgsrip import pgsrip, Mkv, Options
    from babelfish import Language

    media = Mkv('/subtitle/path/mymedia.mkv')
    options = Options(languages={Language('eng')}, overwrite=True, one_per_lang=False)
    pgsrip.rip(media, options)
