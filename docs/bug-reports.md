# Report a bug

A good bug report contains 3 things:

1. the output of `pgsrip doctor`
2. the debug log
3. a scrubbed subtitle sample

The [bug report form](https://github.com/ratoaq2/pgsrip/issues/new/choose) asks for each of them.

When pgsrip cannot rip a subtitle, it prints the error. It also prints the commands that collect the data for a
bug report:

```text
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
```

## Environment

`pgsrip doctor` shows the installed programs. Add its output to the bug report:

```text
$ pgsrip doctor
pgsrip                       0.2.1
python                       3.13.1 (/usr/bin/python3)
platform                     Linux-6.8.0-generic-x86_64
mkvmerge                     mkvmerge v90.0 (/usr/bin/mkvmerge)
mkvextract                   mkvextract v90.0 (/usr/bin/mkvextract)
tesseract                    5.5.1 (/usr/bin/tesseract)
tesseract languages          eng, osd, por
...

Everything that pgsrip needs is installed.
```

When a program is missing, the command shows how to install it, and exits with code 1.

## Subtitle sample

A PGS subtitle contains 2 types of data:

- segments that tell when and where the subtitle shows
- images that contain the text

Only the images contain the content of your media. Most bugs are in the segments.

`pgsrip scrub` writes a copy of your PGS subtitles without the images:

```text
$ pgsrip scrub mymedia.mkv
pgsrip-a25b6c81.en.sup written: 1043/1043 display sets, 1043/1043 images redacted, 412088 bytes
The scrubbed files hold no subtitle image, only timing, layout and palettes.
Attach them to a new issue: https://github.com/ratoaq2/pgsrip/issues
```

The result is a real `.sup` file. pgsrip reads it with the same code as the original, so the bug occurs again. But
the file contains no text, and it is much smaller than the original.

The file name is a hash of the name of your media file. Use `--keep-name` to keep the original name. The name
follows the same [rules](usage.md#file-names) as a ripped `.srt`. For example, a hearing-impaired track gives
`pgsrip-a25b6c81.en.sdh.sup`.

### OCR bugs

When the bug is about the OCR, an empty image does not show the bug. Use one of these options:

```bash
pgsrip scrub --redact synthetic mymedia.mkv
pgsrip scrub --keep-images 412 mymedia.mkv
```

- `--redact synthetic` draws placeholder text in each subtitle image. The text has the same size and the same
  colors as the original.
- `--keep-images` keeps the original image of the given display sets only, for example `412` or `400-420`.
  Usually, a small number of subtitle lines is sufficient, and the file stays small.

To make a long subtitle shorter, use `--only 0-99`. It writes only the given display sets.

## Debug log

`--debug` prints debug messages to the console. `--log-file` writes the same messages to a file. Attach this
file to the bug report:

```text
$ pgsrip --log-file pgsrip.log mymedia.mkv
1 PGS subtitle collected from 1 file
Ripping subtitles  [####################################]  100%  mymedia.mkv [4:en]
1 PGS subtitle ripped from 1 file
Debug log written to pgsrip.log
```

The log starts with the pgsrip, Python, and tesseract versions. It contains the paths of the ripped files. If you
do not want to share the names of your media files, remove or replace these paths.
