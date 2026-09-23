# pgsrip

CLI + library: extracts PGS/SUP subtitles (`.mkv`/`.mks`/`.sup`) and OCRs them into `.srt`.

## Commands

`uv` only (not poetry or pip). Python 3.11 to 3.14.

```
uv sync
uv run pytest -q --tb=short tests
uv run ruff check .
uv run ruff format .
uv run mypy pgsrip
uv run python scripts/check_knowledge.py
bash scripts/test.sh
```

`scripts/test.sh` runs all the checks of CI.

## Code: lazy senior dev

Lazy means less code, not less care. First understand the problem: read the task and trace the real flow.
Then stop at the first step that works:

1. Is the change necessary? (YAGNI)
2. Does pgsrip already have it? Use it again.
3. Does the standard library or an installed dependency do it? Use it.
4. Only then, write the minimum code.

- Bug fix: fix the root cause, not the symptom. Check every caller of the function that you change.
- No abstraction, dependency, or option that nobody asked for. Delete before you add.
- Not lazy about: corrupted input, errors that lose data, tests, and what the user asked for.
- Strict mypy. Narrow `X | None` at the point of use.
- Use quiet flags (`-q --tb=short`). Never send full logs into the context.

Adapted from [ponytail](https://github.com/DietrichGebert/ponytail) (MIT).

## Git

- One-line Conventional Commits subject. Add `Closes #<n>` for a fix. No attribution trailers.
- Bug fix: commit the failing test first, then the fix.
- Use the `ship` skill to commit, push, or open a PR. It follows `CONTRIBUTING.md`.

## Writing

All text follows ASD-STE100 Simplified Technical English. Most readers are not native English speakers.

- One idea in each sentence. Short sentences.
- Active voice and simple tenses.
- Common words. Use one word for one thing.
- No semicolons, no phrasal verbs, no idioms, no filler, no emoji.
- Do not change code, commands, logs, or quotes.

Use the `writing-style` skill for docs, PR, issue, and release text.

## Knowledge

- The rules in `.claude/rules/` load for the paths that they name. They link to `docs/`.
- When a change makes a statement in a knowledge file wrong, fix it in the same commit. `ship` checks it.
- Put project facts in the repo, not in personal memory. `.claude/rules/knowledge.md` tells where.
- Local work lives in `plans/<issue>-<slug>/` (gitignored). The lifecycle is in `docs/workflow.md`.
