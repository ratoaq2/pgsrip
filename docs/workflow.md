# Development workflow

A work item is one issue, fix, or feature. It can take many AI sessions. This file is the single source
for how a work item moves from start to merge.

## Where the work lives

| What | Where | Shared |
| --- | --- | --- |
| Working files: notes, findings, spec, plan, repro scripts, samples | `plans/<item>/` | No (gitignored) |
| Problem, agreed approach, decisions | The GitHub issue | Yes |
| Final result, changes, how to test | The PR body | Yes |
| Knowledge that stays true after the merge | `docs/`, `.claude/rules/`, `CONTRIBUTING.md` | Yes |

Only `plans/` is local. When other people must see a decision, post it to the issue. Never commit media
or subtitle samples from `plans/`.

## Names

- Folder: `plans/<issue>-<slug>/`, for example `plans/135-pts-zero/`. Without an issue:
  `plans/<yyyy-mm-dd>-<slug>/`.
- Branch: the same slug, see `CONTRIBUTING.md`. For example `fix/135-pts-zero`.
- `plans/_samples/` holds media that is not linked to one item.

The SessionStart hook (`.claude/hooks/session_start.py`) finds the issue number in the branch name and
shows the status of the matching folder.

## Folder content

| File | Stage | Content |
| --- | --- | --- |
| `README.md` | always | Handoff file: title, issue link, size, stage, last result, next step. |
| `notes.md` | any | Brainstorm and scratch notes. No fixed format. |
| `findings.md` | investigate | Reproduction, root cause, measured numbers. |
| `spec.md` | spec | Goal, approach, rejected options, test strategy. |
| `plan.md` | plan | Ordered steps, files, tests, checks for each step. |
| `summary.md` | ship | Result and deviations from the plan. It becomes the PR body. |
| `repro/` | any | Scripts and sample files. |

Every skill updates `README.md` before it stops. A new session reads `README.md` first (`resume` skill).

## Size and stages

Decide the size when you start, and write it in `README.md`. Change it if the work grows.

**Small** (one module, clear cause, no design choice):

1. `investigate`: reproduce, then commit a failing test.
2. Fix, then `ship`.

**Large** (more than one module, a design choice, or a performance or format change):

1. `investigate`: `findings.md`.
2. `spec`: `spec.md`. Stop until the user approves. Post a short summary to the issue.
3. `plan`: `plan.md`. Stop until the user approves.
4. Implement, one round at a time. Write the result of each round in `README.md`.
5. `ship`: `summary.md` goes into the PR body.

## Tests first for bug fixes

A bug fix has at least 2 commits: a `test:` commit with a test that fails and shows the bug, then the
`fix:` commit that makes it pass. PRs use a merge commit, so both commits stay on `main`.

## Knowledge upkeep

When a change makes a statement in the knowledge files wrong, fix the statement in the same commit.
`ship` runs `scripts/check_knowledge.py --changed` to find the files to check. `.claude/rules/knowledge.md`
tells where each kind of knowledge goes.
