# Writing style: examples

## Before and after

| Problem | Before | After |
| --- | --- | --- |
| Passive voice | The item is dropped when the PCS is corrupted. | The ripper drops the item when the PCS is corrupted. |
| Compound tense | We have added a check for empty segments. | We added a check for empty segments. |
| Semicolon | The track is long; tesseract refuses it. | The track is long. Tesseract refuses it. |
| Phrasal verb | Spin up one worker per composite. | Start one worker for each composite. |
| Noun from a verb | This performs a validation of the header. | This validates the header. |
| Noun cluster | the PGS segment header length field | the length field of the segment header |
| Hedge stack | This may potentially help to improve speed. | This can make the rip faster. |
| Marketing word | A blazing-fast OCR pass. | The OCR pass takes 15 s for 2065 items. |
| Idiom | This is a moving target. | This changes often. |
| Many names | the stream ... the track ... the sub | the track ... the track ... the track |
| Filler | Simply run the tests in order to check. | Run the tests to check. |

## Issue reply (strict mode)

Before:

> Thanks so much for reporting! It looks like this might be related to some weird muxing going on in your
> file, so we'd need you to grab a sample for us so we can dig into it.

After:

> Thank you for the report. The error can come from a corrupted subtitle track. To find the cause, we
> need a sample of the track. Run this command and attach the output file to this issue:
>
>     pgsrip scrub "your-file.mkv"
>
> The command removes the text of the subtitles. It keeps only the structure of the track.

## Commit subject

- Before: `fix: fixed a bug where timestamps were sometimes being read wrong`
- After: `fix: read PTS 0 as 00:00:00,000 instead of a missing timestamp`

## Code comment

Before:

```python
# we basically need to make sure we don't blow up on garbage data here
```

After:

```python
# Corrupted input is normal. Drop the item and continue.
```
