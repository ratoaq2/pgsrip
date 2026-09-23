---
paths:
  - "pgsrip/pgs.py"
  - "pgsrip/media.py"
---

# Corrupted data

Malformed PGS input is normal. Log and drop a bad item. Do not stop the whole rip. Do not change a
graceful fallback into an error unless the user agrees.

Read `docs/corrupted_data.md` before you change parsing, `auto_fix`, or the `None` handling.
