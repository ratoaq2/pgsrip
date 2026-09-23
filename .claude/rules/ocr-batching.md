---
paths:
  - "pgsrip/ripper.py"
  - "pgsrip/tsv.py"
---

# OCR batching

Keep the number of tesseract calls low. This is more important than simple code. Many subtitle bitmaps go
into a few large composite images, about one for each worker. Each image is one `image_to_data` call, and
the calls run in parallel.

Read `docs/ocr_batching.md` before you change the batching, the composite size, or the retry passes.
