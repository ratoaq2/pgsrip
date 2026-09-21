# pgsrip

CLI + library: extracts PGS/SUP subtitles (`.mkv`/`.mks`/`.sup`) and OCRs them into `.srt`.

## Commands

`uv` only (not poetry/pip). Python 3.11–3.14.

```
uv sync
uv run pytest -q --tb=short tests
uv run ruff check .
uv run ruff format .
uv run mypy pgsrip
bash scripts/test.sh
```

pre-commit runs ruff/mypy and Conventional Commits.

## Code style

- Strict mypy: annotate everything. Narrow `X | None` at point of use, never assume non-`None`.
- Ruff formats (single quotes, 120-char lines) — don't hand-format against it.
- Conventional Commits, single-line subject, no attribution trailers.
- Flat package layout (`pgsrip/`, not `src/pgsrip/`).
- YAGNI: minimum viable code, no speculative features.
- Quiet/short flags only (`-q --tb=short`, `-q` on install) — never pipe full logs into context.

## Docs policy

Read only when touching the matching code; skip `docs/` otherwise.

- `ripper.py` → `docs/ocr_batching.md` (call-minimization constraint)
- `pgs.py` / `media.py`'s `auto_fix` → `docs/corrupted_data.md` (degrade-gracefully constraint)
- `tests/fabricate.py` / `tests/test_rip_e2e.py` → `docs/rip-e2e.md` (fabrication API, backend model)
- Restructuring files/modules → update `docs/architecture.md` after
- Any doc whose claims your change invalidates → update it, same commit
