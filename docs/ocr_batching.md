# OCR batching (`ripper.py`)

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
- Workers: `-w/--max-workers`, default the CPUs of the process, at most `MAX_DEFAULT_WORKERS` (4). A
  container with a CPU quota still reports every host core, so the default is capped.
- `FullImage.from_items` also bounds each composite in both dimensions (`MAX_TESS_DIMENSION`): tesseract
  refuses any image side above 32767 px (`Image too large`, issue #136). A long track can give more
  composites than workers.
- `TsvData` maps recognized words back to source items by correlating `item.place` pixel regions against
  tesseract's per-word boxes. `item.place` is relative to the composite the item was drawn in, so each
  call's output is matched only against that composite's `items`.
- `PgsToSrtRipper.rip()` retries unresolved items with smaller batches / lower confidence thresholds until
  done or given up on.

Invariant: a few large tesseract calls per pass, about one per worker, run in parallel. Never one call per
item: the per-call cost (process start, model load) is what batching avoids.
