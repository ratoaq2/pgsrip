# OCR batching (`tesseract.py`)

One tesseract call per subtitle item = hundreds of slow roundtrips per episode. Instead:

- `FullImage`/`ImageArea` bin-pack many subtitle bitmaps (by vertical overlap, max width) into a few
  composite PNGs.
- Each bitmap is cropped to its ink box first (`PgsSubtitleItem.bitmap`, `shape` moves by the crop). PGS
  objects often span the full frame width: a 1080p track measured 16% ink. An item with no ink is not
  OCR'd.
- `FullImage.from_items` splits a pass into about one composite per worker, of the same height, and
  `process` runs one `image_to_data` call per composite in parallel (`ThreadPoolExecutor`,
  `OMP_THREAD_LIMIT=1`). One tesseract process uses about one core, whatever its OpenMP threads: on a
  2065-item track, pass 1 took 325 s as 1 composite, 25 s as 8 in parallel, 15.5 s as 15.
- Workers: `--tesseract-workers`, else `-w/--max-workers`, default the CPUs of the process, at most `MAX_DEFAULT_WORKERS` (4). A
  container with a CPU quota still reports every host core, so the default is capped.
- `FullImage.from_items` also bounds each composite in both dimensions (`MAX_TESS_DIMENSION`): tesseract
  refuses any image side above 32767 px (`Image too large`, issue #136). A long track can give more
  composites than workers.
- `TsvData` maps recognized words back to source items by correlating `item.place` pixel regions against
  tesseract's per-word boxes. `item.place` is relative to the composite the item was drawn in, so each
  call's output is matched only against that composite's `items`.
- `TesseractEngine.recognize()` retries unresolved items with smaller batches / lower confidence thresholds
  (first pass 65, steps of 5, last pass 0) until done or given up on. It stops when the next pass would be
  the same as the last one.

Invariant: a few large tesseract calls per pass, about one per worker, run in parallel. Never one call per
item: the per-call cost (process start, model load) is what batching avoids.

## Engine chain (`ripper.py`)

`Options.engines` is a list of OCR engines (`OcrEngine`). `PgsToSrtRipper.rip` gives all the items to the
first engine. Each next engine gets only the items that are still unread (`item.text is None`) or doubtful
(`item.doubtful`). An engine failure (`OcrError`) fails the track.

- `TesseractEngine.accept` marks a cue as doubtful when its lowest word confidence is below `threshold`
  (`--tesseract-threshold`, default 80). The retry passes do not use this threshold.
- Before the next engine, the ripper clears the text of the items that it gives to that engine. When the
  engine gives no text for an item, the ripper puts back the text of the engine before it. No text is lost.
- Measured on 2 real tracks: a lowest word confidence below 80 is 8.5 % and 4.5 % of the cues. It finds
  some tesseract errors, not all: tesseract can be wrong with a high confidence.
- Do not use a floor on the retry passes for this. The last pass accepts every word with a confidence of 1
  or more, so a floor of 1 sends almost no cue to the next engine.
