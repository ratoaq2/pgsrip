---
name: demo-gif
description: Record the README terminal demo docs/images/demo.gif with VHS, from a media file that the user gives. Use to make or update the demo GIF.
---

# Demo GIF

`docs/images/demo.gif` shows a pgsrip session in a terminal. VHS records it in a container:

- `scripts/demo.tape`: the session that VHS types and records. It is the source of the current GIF.
- `scripts/demo.Dockerfile`: the pgsrip image, plus VHS, ttyd, and Chromium.
- `scripts/demo.sh DIR`: builds the pgsrip image and the VHS image, mounts DIR on `/demo`, and records.

The media file is not in the repository. The user gives it.

## 1. Inputs

Get these values from the user. Use the default when the user does not give a value.

| Input | Default |
| --- | --- |
| Media file (`.mkv`, `.mks`, or `.sup`) | None. Ask for it. |
| Languages to rip | `en` and `pt-BR` |
| Other `pgsrip rip` options | None |
| File name in the GIF | `media.mkv` |
| Part of the media to use | The first 10 minutes |

Do not move or change the media file of the user.

## 2. Make a small sample

Work in `plans/demo-gif/` (gitignored). The sample goes in `plans/demo-gif/sample/`. This folder must
contain only the sample file, because the GIF shows `ls`.

1. List the tracks: `mkvmerge -J <media>`. Find the PGS track (`HDMV PGS`) of each language
   (`language_ietf`). If a language has more than one PGS track, ask the user which one to use.
2. Cut the sample with only these PGS tracks:

   ```
   mkvmerge -q -o plans/demo-gif/sample/media.mkv -D -A -s <id1>,<id2> --split parts:00:00:00-00:10:00 <media>
   ```

   Keep `-D -A` (no video, no audio). The container reads the files through the mount of the Podman
   machine. On Windows, this mount is very slow: a 4 GB sample stays at 0% until the tape stops. pgsrip
   reads only the subtitle tracks, so the result is the same. `ls` shows only the names.
3. For a `.sup` file, copy the file to the sample folder. mkvmerge cannot cut it.

## 3. Rehearse

Run the rip on the host, then look at the result:

```
cd plans/demo-gif/sample
uv run --project <repo> pgsrip rip -l <lang> -l <lang> <options> media.mkv
grep -c -- '-->' *.srt
head -n 12 *.srt
```

- Each `.srt` must have cues, and the text must be correct. About 20 to 40 cues for each language is
  good.
- If the first cue comes late, use a different part (`--split parts:<start>-<end>`).
- The tape deletes the `.srt` files before it records. You do not have to delete them.

## 4. Edit the tape

Edit `scripts/demo.tape`. Change only the lines that the inputs change:

- The `pgsrip rip` command: the languages, the options, and the file name.
- The `head -n 8 ...srt` command: the names of the output files (`<stem>.<language>.srt`). Show at most
  two files. `-n 8` shows the first two cues when each cue has at most two lines.
- If you changed the file name, rename the sample file to the same name.

Keep the hidden setup at the top. It goes to `/demo`, deletes the `.srt` files, and sets the prompt to
`$ `. The GIF must not show the path.

## 5. Record

1. On Windows or macOS, start the Podman machine: `podman machine start`. It is not an error if it runs
   already.
2. From the repository root, run `bash scripts/demo.sh plans/demo-gif/sample`. The first build takes
   some minutes. The next runs take about 2 minutes.
3. The output ends with `Creating docs/images/demo.gif...`. If it ends with `recording failed`, the rip
   took more than the 120 s wait of the tape. Make the sample smaller.

Known problems that the scripts already solve:

- Debian has no `ttyd` package. `scripts/demo.Dockerfile` downloads the static binary.
- Podman on Windows ignores `-f -`. Keep the VHS layer in `scripts/demo.Dockerfile`.
- Git Bash changes `/demo` into a Windows path. `scripts/demo.sh` sets `MSYS_NO_PATHCONV=1`.

## 6. Check the frames

Save some frames as PNG, then read them:

```
uv run --no-project --with pillow python -c "
from PIL import Image
im = Image.open('docs/images/demo.gif')
n = im.n_frames
print(im.size, n, 'frames', sum((im.seek(i), im.info.get('duration', 0))[1] for i in range(n)) / 1000, 's')
for k, f in enumerate([n // 2, n - 1]):
    im.seek(f)
    im.convert('RGB').save(f'plans/demo-gif/frame{k}.png')
"
```

Look for these problems:

- The first `ls` is not in the last frame: increase `Set Height` in the tape.
- A large empty area at the bottom of the last frame: decrease `Set Height`.
- A cue is cut in the middle: change `head -n`.
- The GIF is more than about 2 MB or 30 s: make the sample shorter.

Record again after each change. Delete the PNG files when you are done.

## 7. Finish

1. Show the last frame to the user, with the size and the duration of the GIF.
2. `README.md` shows `docs/images/demo.gif` with an absolute `raw.githubusercontent.com` URL, so that
   PyPI shows it too. Change its alt text if the languages changed.
3. To commit, use the `ship` skill. Commit `docs/images/demo.gif` and `scripts/demo.tape` together.
