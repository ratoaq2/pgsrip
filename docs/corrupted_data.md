# Corrupted data handling

Malformed PGS (bad muxing, truncated segments) is the norm, not exceptional. Degrade gracefully:

- `make_item` reads the optional fields of `formats/pgs.py` (`to_int` → `None` on empty slices). It fixes a
  missing end time, or logs and drops a bad item. An `Item` is made only with plain values.
- `read_segments` stops at a bad `PG` marker, at a short segment header, and at an unknown segment type, with a
  warning. The display sets before that point are read.
- `read_items` drops a display set with no PCS, with a composition state or an object sequence type that does
  not exist, or with a PCS or a WDS that is too short (`DisplaySet.error`), with a warning. `formats/scrub.py`
  keeps these display sets byte for byte: they reproduce the bug.
- The palette of an item is the PDS with the `palette_id` of the PCS, else the last PDS. An item with no PDS is
  dropped, with a warning.
- The debug files (`Segment.to_json`) write `invalid` for a field that cannot be read.
- Don't tighten these into hard failures without confirming that's actually wanted.
