# Contributing

## Setup

MKVToolNix and tesseract must be on `PATH` to rip real media.

```
uv sync
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
```

pre-commit runs ruff, mypy, the knowledge check, and the Conventional Commits check.

## Commands

The command list is in `CLAUDE.md`. Claude Code loads that file in each session, and people can read it
too.

## Code

- Keep the code small. See "Code: lazy senior dev" in `CLAUDE.md`.
- Strict mypy: annotate every function.
- Ruff formats the code (single quotes, 120-character lines). Do not format by hand against it.
- Flat package layout: `pgsrip/`, not `src/pgsrip/`.
- Do not add tests with real subtitle content. See `tests/samples/README.md`.

## Tests

`tests/test_rip_e2e.py` rips fabricated media from end to end through the CLI. It checks the `.srt` files that
it writes. By default, the tests use a fake MKVToolNix. Tesseract is always fake. `--media-backend real` or
`--media-backend both` runs the same scenarios with a real `mkvmerge`. See `docs/rip-e2e.md`.

## Branches

- `fix/<issue>-<slug>`, `feat/<issue>-<slug>`, `chore/<slug>`. Example: `fix/135-pts-zero`.
- Never push to `main`. Force-push (`--force-with-lease`) only on your own feature branch.

## Commits

- Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`), with a one-line subject.
- No body, except one `Closes #<n>` line when the commit fixes an issue.
- No attribution trailers (`Co-Authored-By` and similar).
- Bug fix: first commit a test that fails and shows the bug, then commit the fix.
- A change that users can see: add a line under `## Unreleased` in `CHANGELOG.md`.

## Pull requests

- Open the PR as a draft. Mark it ready after a final read-through.
- Title: short and plain, like a commit subject, but with no `feat:` or `fix:` prefix.
- Body: use `.github/pull_request_template.md`.
- We merge with a merge commit, so all commits stay in the history.

## Writing

Write all text (comments, docs, commits, PRs, issues) in ASD-STE100 Simplified Technical English. Most
contributors are not native English speakers. See `.claude/skills/writing-style/SKILL.md`.
