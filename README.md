# pgsrip

Convert image-based Blu-ray subtitles (PGS) in `.mkv`, `.mks`, and `.sup` files to text `.srt` files, with OCR.

[![PyPI version](https://img.shields.io/pypi/v/pgsrip.svg)](https://pypi.org/project/pgsrip/)
[![Python versions](https://img.shields.io/pypi/pyversions/pgsrip.svg)](https://pypi.org/project/pgsrip/)
[![Tests](https://github.com/ratoaq2/pgsrip/actions/workflows/test.yml/badge.svg)](https://github.com/ratoaq2/pgsrip/actions/workflows/test.yml)
[![Docker pulls](https://img.shields.io/docker/pulls/ratoaq2/pgsrip.svg)](https://hub.docker.com/r/ratoaq2/pgsrip)
[![License](https://img.shields.io/github/license/ratoaq2/pgsrip.svg)](https://github.com/ratoaq2/pgsrip/blob/main/LICENSE)

![A PGS subtitle image and the SRT text that pgsrip makes from it](https://raw.githubusercontent.com/ratoaq2/pgsrip/main/docs/images/before-after.png)

## Why pgsrip

Blu-ray subtitles use the PGS format. A PGS subtitle is an image, not text. Many players, TVs, and subtitle
editors cannot show or edit these images.

pgsrip reads the text in the images with [tesseract](https://github.com/tesseract-ocr/tesseract) OCR. When
tesseract is not installed, it uses [RapidOCR](docs/usage.md#rapidocr) (`pgsrip[rapidocr]`). Then it writes a `.srt` file next to your
video. It downloads the language data that it needs automatically.

## Quick start

1. Install [MKVToolNix](#install-mkvtoolnix-and-tesseract) and [tesseract](#install-mkvtoolnix-and-tesseract).
2. Install pgsrip:

   ```bash
   uv tool install "pgsrip[rapidocr]"
   ```

3. Rip the subtitles of a video:

   ```text
   $ pgsrip mymedia.mkv
   3 PGS subtitles collected from 1 file
   Ripping subtitles  [####################################]  100%  mymedia.mkv [5:de]
   3 PGS subtitles ripped from 1 file
   ```

To try pgsrip without installing it, use `uvx --from "pgsrip[rapidocr]" pgsrip mymedia.mkv`.

## Installation

### Install pgsrip

Use one of these commands:

| Command | When to use it |
| --- | --- |
| `uv tool install "pgsrip[rapidocr]"` | Recommended. [uv](https://docs.astral.sh/uv/getting-started/installation/) also installs Python if necessary. |
| `pipx install "pgsrip[rapidocr]"` | You already use [pipx](https://pipx.pypa.io/). |
| `pip install "pgsrip[rapidocr]"` | You want to use pgsrip as a Python library. Python 3.11 or later. |

`[rapidocr]` also installs the [RapidOCR](docs/usage.md#rapidocr) engine. Without it, pgsrip uses only tesseract.
Remove `[rapidocr]` on a platform where ONNX Runtime has no wheel, for example Alpine Linux (musl) or an old
Linux with glibc before 2.28. On these platforms, the install with `[rapidocr]` fails.

To upgrade, use `uv tool upgrade pgsrip` or `pipx upgrade pgsrip`.

### Install MKVToolNix and tesseract

pgsrip needs 2 programs: MKVToolNix and tesseract. uv, pipx, and pip do not install them.

Tesseract is optional when you installed pgsrip with `[rapidocr]`. Without tesseract, pgsrip uses RapidOCR for
all languages.

**Ubuntu, Debian, and WSL**

```bash
sudo apt-get install mkvtoolnix tesseract-ocr
```

The PPA below gives the latest tesseract 5. It is optional.

```bash
sudo add-apt-repository ppa:alex-p/tesseract-ocr5
sudo apt update
sudo apt-get install tesseract-ocr
```

**Windows** (with [Chocolatey](https://chocolatey.org/))

```bash
choco install mkvtoolnix tesseract-ocr
```

**macOS** (with [Homebrew](https://brew.sh/))

```bash
brew install mkvtoolnix tesseract
```

To make sure that all programs are installed, run `pgsrip doctor`.

### Language data

You do not need to install it. pgsrip downloads the language data at the first rip. See
[Language data](docs/usage.md#language-data).

### Docker

The [Docker image](https://hub.docker.com/r/ratoaq2/pgsrip) contains pgsrip, MKVToolNix, tesseract, and all
languages. It also contains the RapidOCR PP-OCRv6 small model in `/usr/src/rapidocr`. You do not need to install
anything else:

```bash
docker run -it --rm -v /medias:/medias -u $(id -u):$(id -g) ratoaq2/pgsrip -l en /medias
```

To build the image from the source code:

```bash
git clone https://github.com/ratoaq2/pgsrip.git
cd pgsrip
docker build . -t pgsrip
```

## Usage

Rip a `.mkv`, `.mks`, or `.sup` file:

```bash
pgsrip mymedia.mkv
pgsrip mymedia.mks
pgsrip mymedia.en.sup
```

Rip all the files in a folder, only in English and Brazilian Portuguese:

```text
$ pgsrip -l en -l pt-BR ~/medias/
11 PGS subtitles collected from 9 files / 2 files filtered out
Ripping subtitles  [####################################]  100%  ~/medias/mymedia.mkv [4:en]
11 PGS subtitles ripped from 9 files
```

Rip only the forced subtitles:

```bash
pgsrip --with forced mymedia.mkv
```

When pgsrip does not rip a file, it tells you why:

```text
$ pgsrip -l fr ~/medias/
~/medias/mymedia.mkv ignored: mkvmerge not found, install MKVToolNix and make sure that it is in the PATH
0 PGS subtitle collected from 0 file / 1 path ignored
```

pgsrip does not rip a subtitle again when the `.srt` file exists. Use `-f` to rip it again.

### Main options

| Option | What it does |
| --- | --- |
| `-l`, `--language` | Rip only this language, for example `en` or `pt-BR`. You can use it more than one time. |
| `-f`, `--force` | Rip again and replace the `.srt` files that exist. |
| `--with FLAG` | Rip only the tracks with this flag, for example `forced` or `sdh`. |
| `--without FLAG` | Do not rip the tracks with this flag, for example `commentary`. |
| `--all` | Rip all the selected tracks. Do not remove duplicates. |
| `--one-per-language` | Rip only one track for each language. |
| `-a`, `--age` | Rip only the videos that are newer than this age, for example `12h` or `1w2d`. |
| `-e`, `--encoding` | Write the `.srt` files with this encoding. |
| `-w`, `--max-workers` | Number of OCR jobs that run at the same time, for example tesseract processes. The default is the number of CPUs, at most 4. `--tesseract-workers` overrides it for tesseract. |
| `--no-tesseract-download` | Do not download language data. Use only the installed languages. |
| `--engine NAME` | OCR engine: [`auto`](docs/usage.md#the-default-engine-auto) (default: tesseract, else RapidOCR), `tesseract`, [`rapidocr`](docs/usage.md#rapidocr), or an engine of a plug-in. Use it more than one time for a [chain](docs/usage.md#ocr-engines). |
| `--log-file FILE` | Write a debug log to this file. |

Run `pgsrip --help` for all options. [docs/usage.md](docs/usage.md) gives more details.

### Configuration file

A configuration file can contain the options of `pgsrip rip`. The keys are the option names, with `_` in
place of `-`. For `--with` and `--without`, use `with_flags` and `without_flags`.

A section groups the options with the same prefix. For example, `threshold` in the `tesseract` section is
`--tesseract-threshold`.

```yaml
language:
  - en
  - pt-BR
max_workers: 4
without_flags:
  - commentary
engine:
  - tesseract
tesseract:
  workers: 2
  threshold: 90
  repository: fast
  dir: /data/tessdata
  download: false
cleanit:
  tag:
    - no-sdh
```

pgsrip reads the configuration files in this order. A later file overrides an earlier file.

1. `config.json`, `config.yml`, or `config.yaml` in the pgsrip user configuration folder:
   - Linux: `~/.config/pgsrip/` (or `$XDG_CONFIG_HOME/pgsrip/`)
   - macOS: `~/Library/Application Support/pgsrip/`
   - Windows: `%LOCALAPPDATA%\pgsrip\pgsrip\`
2. `pgsrip.json`, `pgsrip.yml`, or `pgsrip.yaml` in the current folder.
3. Each file that you give with `--config`, in the order of the command line.

An option on the command line overrides the configuration files. An unknown key is an error.

`pgsrip doctor` reads the same files. It uses only the OCR engine and post-processor sections, for example
`tesseract` and `cleanit`.

For the cleanit options (`--cleanit-config`, `-t/--tag`), see [Post-processors](docs/usage.md#post-processors).

### Output file names

pgsrip writes the `.srt` file next to the video. The name contains the language and the flags of the track:

```text
movie.en.srt              a plain English track
movie.en.sdh.srt          a hearing-impaired English track
movie.pt-BR.forced.srt    a forced Brazilian Portuguese track
```

For the rules, see [File names](docs/usage.md#file-names).

### Python API

```python
from babelfish import Language
from pgsrip import pgsrip, Mkv, Options

media = Mkv('/subtitle/path/mymedia.mkv')
options = Options(languages={Language('eng')}, overwrite=True)
pgsrip.rip(media, options)
```

The OCR engines are an option too, in chain order. The default is `[AutoEngine()]` (`pgsrip.engines.auto`): tesseract,
else RapidOCR, for each language. This example uses tesseract only:

```python
from pgsrip.engines.tesseract import TesseractEngine

options = Options(engines=[TesseractEngine(workers=2, threshold=90)])
```

## FAQ

**What is PGS?**
PGS (Presentation Graphic Stream) is the subtitle format of Blu-ray discs. Each subtitle is an image. A `.sup`
file contains only a PGS subtitle. A `.mkv` or `.mks` file can contain PGS subtitle tracks.

**The text in the `.srt` file has errors. What can I do?**
Make sure that the language of the track is correct. The default language data
([tessdata_best](https://github.com/tesseract-ocr/tessdata_best)) gives the best quality. If the errors
continue, [report a bug](#report-a-bug) with a scrubbed sample.

**Does pgsrip support DVD subtitles (VobSub, `.sub`/`.idx`)?**
No. pgsrip supports only PGS subtitles.

**Where does pgsrip store the language data?**
In a user cache directory. See [Where pgsrip stores the data](docs/usage.md#where-pgsrip-stores-the-data).

## Report a bug

1. Run `pgsrip doctor` and copy the output.
2. Run `pgsrip scrub mymedia.mkv`. It writes a copy of the subtitle without the images, so you do not share the
   content of your media.
3. Run `pgsrip --log-file pgsrip.log mymedia.mkv`.
4. Fill in the [bug report form](https://github.com/ratoaq2/pgsrip/issues/new/choose) and attach the files.

For more information, see [docs/bug-reports.md](docs/bug-reports.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
