# Corrupted data handling

Malformed PGS (bad muxing, truncated segments) is the norm, not exceptional. Degrade gracefully:

- `media.py`'s `auto_fix` and `pgs.py`'s `Optional[int]` fields (`from_hex` → `None` on empty slices) log +
  drop bad items rather than crash the rip.
- Don't tighten these into hard failures without confirming that's actually wanted.
