# OCR batching (`ripper.py`)

One tesseract call per subtitle item = hundreds of slow roundtrips per episode. Instead:

- `FullImage`/`ImageArea` bin-pack many subtitle bitmaps (by vertical overlap, max width) into one or a few
  composite PNGs.
- `FullImage.from_items` bounds each composite in both dimensions (`MAX_TESS_DIMENSION`): tesseract refuses
  any image side above 32767 px (`Image too large`, issue #136). A long track with wide bitmaps yields
  several composites instead of one oversized image. They are yielded one at a time, so only one composite
  is in memory at once.
- One `image_to_data` call per composite. A normal track still fits in one composite per pass.
- `TsvData` maps recognized words back to source items by correlating `item.place` pixel regions against
  tesseract's per-word boxes. `item.place` is relative to the composite the item was drawn in, so each
  call's output is matched only against that composite's `items`.
- `PgsToSrtRipper.rip()` retries unresolved items with smaller batches / lower confidence thresholds until
  done or given up on.

Invariant: minimize tesseract invocations, not code complexity.
