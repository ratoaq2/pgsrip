# OCR batching (`engines/tesseract.py`, `engines/rapidocr.py`)

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

## RapidOCR (`engines/rapidocr.py`)

RapidOCR loads its model one time, in the pgsrip process. There is no cost for each call that composites can
save. The cost grows with the number of pixels. So the engine batches text lines, not composites:

- The recognition model reads one text line, scaled to 48 px high. `split_lines` (`utils.py`) cuts each cue at
  its empty rows. The RapidOCR detector is not used: it is one more model call for each cue, and it missed
  lines on short cues.
- Each line gets a white border of 4 px (`--rapidocr-border`). A larger border makes the letters small. Cue
  errors on 751 cues of 3 tracks: 0 px 34, 4 px 8, 8 px 9, 20 px 12.
- All the lines of a track go to `read_lines` in one call. It sorts them by width and runs them in batches of
  `--rapidocr-batch` (default 6) lines. Batch 1 was 60 % slower than batch 6. From batch 6 to 64 there was no
  clear change.
- Composites (lines side by side in one image) were not faster (37.9-40.8 s against 34.6 s), because the gaps
  add pixels. With 8 lines in a composite, new errors appeared.
- `--rapidocr-workers` (else `-w`) sets the ONNX Runtime threads. 8 threads was the fastest, 16 was slower.
- `read_lines` runs the model and decodes its output itself (greedy CTC, `ctc`). The cue score is the lowest
  character score of its lines. The RapidOCR line score is a mean, and one bad character is hidden in it.
  `read_lines` uses `TextRecognizer` internals: `rapidocr` is pinned to one minor version. The real-model test
  in `tests/test_rapidocr.py` finds a change.

## Engine chain (`ripper.py`)

`Options.engines` is a list of OCR engines (`OcrEngine`). `PgsRipper.rip` gives all the items to the
first engine. Each next engine gets only the items that are still unread (`item.text is None`) or doubtful
(`item.doubtful`). An engine failure (`OcrError`) fails the track.

- Before the first engine, the ripper replaces each engine with `engine.engine_for(pgs.language)`, and removes
  the `None` results. By default, `engine_for` gives the engine itself when `supports` is `True`, else `None`.
  When no engine is left, the track fails with `OcrError`. The cues and the times use the name of the returned
  engine. `AutoEngine`, the default, returns tesseract or RapidOCR: one engine for the track, not a chain.
- A doubtful cue keeps its text when no next engine reads it, also when the ripper removed the next engines.
- `TesseractEngine.accept` marks a cue as doubtful when its lowest word confidence is below `threshold`
  (`--tesseract-threshold`, default 80). The retry passes do not use this threshold. It also sets
  `item.confidence` to this lowest word confidence divided by 100.
- Before the next engine, the ripper clears the text of the items that it gives to that engine. When the
  engine gives no text for an item, the ripper puts back the text, the doubtful flag, and the confidence of the
  engine before it. No text is lost.
- `PgsRipper.rip` returns a `Cue` for each item, with the engine that gave its text. The post-processors
  run after the whole chain (see `docs/usage.md`, "Post-processors").
- Measured on 2 real tracks: a lowest word confidence below 80 is 8.5 % and 4.5 % of the cues. It finds
  some tesseract errors, not all: tesseract can be wrong with a high confidence.
- Do not use a floor on the retry passes for this. The last pass accepts every word with a confidence of 1
  or more, so a floor of 1 sends almost no cue to the next engine.
