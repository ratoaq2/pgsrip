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

1. `--tesseract-dir`, or the `PGSRIP_TESSDATA_DIR` environment variable
2. the `TESSDATA_PREFIX` environment variable
3. the user cache directory:
   - Windows: `%LOCALAPPDATA%\pgsrip\tessdata`
   - macOS: `~/Library/Caches/pgsrip/tessdata`
   - Linux: `~/.cache/pgsrip/tessdata`

pgsrip never downloads a language that tesseract already has. Tesseract always uses the first data that it
finds for a language.

Tesseract cannot read a language when the tesseract program is not found, or when the data is not installed
and cannot be downloaded. The download is off, or it failed. The [engine chain](#a-chain-of-ocr-engines) then skips
tesseract for the tracks in this language.

### Download options

| Option | Environment variable | What it does |
| --- | --- | --- |
| `--no-tesseract-download` | | Do not download. Use only the installed languages. |
| `--tesseract-repository fast` | `PGSRIP_TESSDATA_REPO=fast` | Download the smaller and faster models of [tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast). |
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

`-w` applies to each OCR engine of a [chain](#a-chain-of-ocr-engines). `--tesseract-workers` overrides it for
tesseract only. For example, `-w 1 --tesseract-workers 4` runs 4 tesseract processes, and the next engine gets 1.

## OCR engines

pgsrip reads the text of the subtitle images with an OCR engine. The default engine is tesseract. Other Python
packages can add an engine (see [Add an OCR engine](#add-an-ocr-engine)).

### A chain of OCR engines

Use `--engine` more than one time to make a chain:

```bash
pgsrip --engine tesseract --engine myocr mymedia.mkv
```

The first engine reads all the cues. Each next engine reads only these cues:

- The cues that the engines before it could not read.
- The cues that the engine before it is not sure of ("doubtful" cues).

Tesseract marks a cue as doubtful when a word of the cue has a confidence below 80. `--tesseract-threshold`
changes this value (0 to 100). A higher value sends more cues to the next engine. When the next engine gives no
text for a cue, pgsrip keeps the tesseract text.

pgsrip skips an engine of the chain for a track in a language that the engine cannot read. It shows one line for
each such engine before the rip starts. When no engine of the chain can read the language, the track fails.

A [configuration file](../README.md#configuration-file) can also set the chain and the threshold:

```yaml
engine:
  - tesseract
  - myocr
tesseract:
  threshold: 90
```

### Add an OCR engine

A Python package can add an OCR engine. Declare an entry point in the `pgsrip.engines` group. Its value is the
engine class:

```toml
[project.entry-points."pgsrip.engines"]
myocr = "myocr.engine:MyEngine"
```

The class declares its options, and creates the engine from their values (see `OcrEngineFactory` in
`pgsrip/ripper.py`):

```python
import click

from pgsrip.ripper import OcrEngine, PluginOption


class MyEngine(OcrEngine):
    options = (
        PluginOption('model', click.Choice(['small', 'large']), default='small', help='Model to use.'),
        PluginOption('url', required=True, envvar='MYOCR_URL', help='URL of the server.'),
        PluginOption('gpu', flag=True, help='Use the GPU.'),
    )

    @classmethod
    def from_settings(cls, settings, workers):
        return cls(settings['model'], settings['url'], settings['gpu'], workers=workers)
```

pgsrip makes a command line option from each declared option, with the engine name as prefix:
`--myocr-model`, `--myocr-url`, and `--myocr-gpu/--no-myocr-gpu`. Each engine also gets `--myocr-workers`.
`workers` is its value, or the `-w` value, or `None`. A configuration file sets the options in a section:

```yaml
myocr:
  model: large
  url: http://127.0.0.1:8080
```

- The value of a `required` option is necessary only when the engine is in `--engine`.
- An `envvar` option also reads this environment variable.
- The `--myocr-*` options on the command line need `--engine myocr`.

pgsrip loads every plug-in class when it starts, also for `pgsrip --help`. Import the large libraries of the
engine (for example onnxruntime) only in its methods. A plug-in that cannot be loaded is left out, with a
warning.

The engine has 3 methods (see `OcrEngine` in `pgsrip/ripper.py`):

- `prepare(languages, reporter)`: get ready before the rip starts. Raise `pgsrip.ripper.OcrError` when the
  engine cannot rip at all.
- `supports(language)`: `True` when the engine can read this language. pgsrip calls it after `prepare`. When
  it returns `False`, pgsrip skips the engine for the tracks in this language.
- `recognize(pgs, items)`: set `item.text` for each item that the engine can read. Leave `None` for the next
  engine of the chain. Set `item.doubtful` when the text can be wrong. Set `item.confidence` (0 to 1) when the
  engine has one. Raise `OcrError` when the engine fails: pgsrip then writes no `.srt` file for that track.

Subclass `OcrEngine` to get the default `engine_for(language)`: the engine itself when it supports the
language, else `None`. Override `engine_for` only when the engine sends a track to another engine. A class
that does not subclass `OcrEngine` must also write `engine_for`.

The class can also have a `check(settings)` classmethod. It returns a list of `pgsrip.diagnostics.Check`.
`pgsrip doctor` shows the checks of all engines, and the debug log shows the checks of the engines in
`--engine`. A check must not fail when an option has no value: show `not set`.

Use the engine by name, alone or in a chain. A plug-in cannot replace `tesseract`.

## Post-processors

After the chain of OCR engines, a chain of post-processors changes the text of the cues of the track. The
default post-processor is cleanit. It removes, for example, speaker labels, lyrics, and ads. Other Python
packages can add a post-processor (see [Add a post-processor](#add-a-post-processor)).

Use `--post-processor` more than one time to make a chain. Each post-processor gets the cues of the one before
it:

```bash
pgsrip --post-processor cleanit --post-processor myfix mymedia.mkv
```

`--no-post-process` keeps the text of the OCR engines.

pgsrip leaves out the cues that have no text at the end of the chain.

### cleanit options

- `--cleanit-config`: a cleanit rules file. Its rules are added to the default rules.
- `-t`, `--tag`, or `--cleanit-tag`: the rule tags to use, e.g. `ocr`, `tidy`, `no-sdh`, `no-style`,
  `no-lyrics`, `no-spam`. The default tag is `default`. Use it more than one time for more tags.

A [configuration file](../README.md#configuration-file) can also set the chain and the cleanit options:

```yaml
post_processor:
  - cleanit
  - myfix
cleanit:
  config: /data/cleanit.yml
  tag:
    - no-sdh
    - no-spam
```

### The cues as JSON

With `--keep-temp-files`, pgsrip writes 2 files in the temporary folder of each track:

- `ocr.json`: the cues after the chain of OCR engines.
- `cues.json`: the cues after the chain of post-processors.

Each cue has its `index`, `start`, `end`, `text`, `confidence` (0 to 1, or `null`), `doubtful`, and `engine`
(the class name of the engine that read it). `seconds` gives the time of each OCR engine for the track.

### Add a post-processor

A Python package can add a post-processor. Declare an entry point in the `pgsrip.postprocessors` group. Its
value is the post-processor class:

```toml
[project.entry-points."pgsrip.postprocessors"]
myfix = "myfix.postprocessor:MyFix"
```

The class declares its options like an [OCR engine](#add-an-ocr-engine), with `PluginOption`. pgsrip makes
the `--myfix-*` options and reads the `myfix` section of a configuration file. A post-processor has no
`workers` option. `from_settings` gets only the settings (see `PostProcessorFactory` in
`pgsrip/postprocess.py`). Raise `ValueError` when a value is wrong: pgsrip shows it as a usage error.

```python
from pgsrip.ripper import PluginOption


class MyFix:
    options = (PluginOption('model', default='small', help='Model to use.'),)

    @classmethod
    def from_settings(cls, settings):
        return cls(settings['model'])

    def process(self, pgs, cues):
        for cue in cues:
            if cue.text and cue.doubtful:
                cue.text = self.fix(cue.text, cue.item.image)
        return cues
```

`process(pgs, cues)` gets all the cues of one track, and returns the new list (see `PostProcessor` in
`pgsrip/postprocess.py` and `Cue` in `pgsrip/ripper.py`). It can change, remove, add, or merge cues. A cue with
`text=None` was not read by any engine. `cue.item` gives the subtitle image. An error stops the track: pgsrip
then writes no `.srt` file for that track.

The class can also have a `check(settings)` classmethod, like an OCR engine. `pgsrip doctor` shows the checks of
all post-processors.

A post-processor cannot replace `cleanit`, and cannot have the name of an OCR engine.
