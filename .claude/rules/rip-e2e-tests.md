---
paths:
  - "tests/fabricate.py"
  - "tests/test_rip_e2e.py"
  - "tests/test_rip_e2e.yml"
---

# End-to-end rip tests

The tests make media from parameters, rip it through the CLI, and check the `.srt` files. Tesseract is
always a fake. MKVToolNix is a fake by default, and real with `--media-backend real`.

Read `docs/rip-e2e.md` for the fabrication API and the backend model.
