# OCR batching (`ripper.py`)

One tesseract call per subtitle item = hundreds of slow roundtrips per episode. Instead:

- `FullImage`/`ImageArea` bin-pack many subtitle bitmaps (by vertical overlap, max width) into one or a few
  composite PNGs.
- One `image_to_data` call per composite.
- `TsvData` maps recognized words back to source items by correlating `item.place` pixel regions against
  tesseract's per-word boxes.
- `PgsToSrtRipper.rip()` retries unresolved items with smaller batches / lower confidence thresholds until
  done or given up on.

Invariant: minimize tesseract invocations, not code complexity.
