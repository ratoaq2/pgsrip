---
paths:
  - "pgsrip/engines/chain.py"
  - "pgsrip/engines/openai.py"
  - "pgsrip/engines/tesseract.py"
  - "pgsrip/engines/tsv.py"
---

# OCR batching

Keep the number of tesseract calls low. This is more important than simple code. Many subtitle bitmaps go
into a few large composite images, about one for each worker. Each image is one `image_to_data` call, and
the calls run in parallel.

The OpenAI-compatible engine is different. It sends one request for each text line of each item, on purpose.
One image never holds more than one item.

Read `docs/ocr_batching.md` before you change the batching, the composite size, or the retry passes.
