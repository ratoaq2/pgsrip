# Usage details

This page gives the details that the [README](../README.md) does not show.

## Language data

Tesseract needs one `.traineddata` file for each subtitle language. pgsrip finds the languages of the
subtitles that it collected. Before it starts to rip, it downloads the files that tesseract does not have:

```text
$ pgsrip mymedia.mks
1 PGS subtitle collected from 1 file
Downloading tesseract data for por...
Ripping subtitles  [####################################]  100%  mymedia.mks [3:pt-BR]
1 PGS subtitle ripped from 1 file
```

pgsrip downloads each file one time only. Every later rip uses it again.

### Where pgsrip stores the data

pgsrip uses the first directory in this list that it can write to:

1. `--tessdata-dir`, or the `PGSRIP_TESSDATA_DIR` environment variable
2. the `TESSDATA_PREFIX` environment variable
3. the user cache directory:
   - Windows: `%LOCALAPPDATA%\pgsrip\tessdata`
   - macOS: `~/Library/Caches/pgsrip/tessdata`
   - Linux: `~/.cache/pgsrip/tessdata`

pgsrip never downloads a language that tesseract already has. Tesseract always uses the first data that it
finds for a language.

### Download options

| Option | Environment variable | What it does |
| --- | --- | --- |
| `--no-tessdata-download` | | Do not download. Use only the installed languages. |
| `--tessdata-repository fast` | `PGSRIP_TESSDATA_REPO=fast` | Download the smaller and faster models of [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast). |
| | `PGSRIP_TESSDATA_URL` | Download from a mirror. Set the base URL of the mirror. |

The default source is [tessdata_best](https://github.com/tesseract-ocr/tessdata_best). It gives the best OCR
quality.

### Install all languages manually

You can also install all languages before the first rip:

```bash
git clone https://github.com/tesseract-ocr/tessdata_best.git ~/tessdata_best
export TESSDATA_PREFIX=~/tessdata_best
```

The Docker image already contains all languages of `tessdata_best`.

## Select tracks

### Flags

A subtitle track can have flags. pgsrip knows these flags, in this order: `forced`, `sdh`, `cc`, `commentary`,
`descriptive`.

- `--with FLAG` rips only the tracks that have at least one of the given flags. Use `--with full` for a track
  that has no flag.
- `--without FLAG` does not rip a track that has one of the given flags.
- When a track matches both options, `--without` has priority.
- You can use each option more than one time.

```bash
pgsrip --with forced --with full mymedia.mkv
pgsrip --without commentary mymedia.mkv
```

### One track or more for each language

By default, pgsrip keeps one track for each combination of language and flags. Thus, it rips a plain English
track and an SDH English track. SDH means subtitles for the deaf and hard of hearing.

- `--one-per-language` keeps only one track for each language. It ignores the flags.
- `--all` rips all the selected tracks. It does not remove duplicates.

### Filtered files

`--language` and `--age` remove some files from the rip. Use `-vvv` to see these files.

## File names

pgsrip writes `<video>.<language>[.<flag>]*.srt`. The flags come in the order of the [flags](#flags) list:

```text
movie.en.srt              a plain English track
movie.en.sdh.srt          a hearing-impaired English track
movie.pt-BR.forced.srt    a forced Brazilian Portuguese track
```

Two selected tracks of one media file can get the same name. Then pgsrip adds `.track<n>` to the name. The first
track keeps the plain name. pgsrip numbers each next track in order, for example `movie.en.srt` and
`movie.en.track2.srt`. The name is the same at each run. It does not change with the other tracks or with the
`.srt` files that are in the folder.

## Parallel processes

pgsrip runs more than one tesseract process at the same time. The default is the number of CPUs that pgsrip can
use, at most 4. Use `-w` to change it. For example, use `-w 16` on a large machine, or `-w 1` on a shared
machine.

A container with a CPU limit (`docker run --cpus`) shows all the CPUs of the host. Thus, set `-w` to the same
value as the limit.
