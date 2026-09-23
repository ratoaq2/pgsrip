---
paths:
  - "tests/**"
---

# Tests

- Bug fix: commit a failing test that shows the bug first, then the fix. See `docs/workflow.md`.
- Add only scrubbed subtitle samples. Real subtitle images are copyrighted content. See
  `tests/samples/README.md`.
- Run with quiet flags: `uv run pytest -q --tb=short tests`.
