---
paths:
  - "**/*.md"
  - ".claude/**"
---

# Knowledge files: where each fact goes

Each fact has one owner file. Other files link to the owner. Do not copy the fact.

| Load tier | File | Put here |
| --- | --- | --- |
| HOT (every session) | `CLAUDE.md` | Commands and rules that almost every task needs. Keep it short. |
| COLD (linked) | `CONTRIBUTING.md` | Setup, branch, commit, and PR rules, for humans and AI. `ship` reads it. |
| WARM (by path) | `.claude/rules/<topic>.md` | A constraint for some paths: 1-5 lines, then a link to the doc. |
| WARM (by task) | `.claude/skills/<name>/SKILL.md` | A repeated procedure. Templates go next to it. |
| COLD (linked) | `docs/<topic>.md` | Domain knowledge, design, and reasons. Humans read it too. |
| Local | `plans/<item>/` | Work in progress. See `docs/workflow.md`. |

Rules for knowledge files:

- The HOT files cost tokens in every session. Add a line there only when almost every task needs it.
  Move everything else to a rule, a skill, or a doc. Do not import other files into `CLAUDE.md`.
- Keep each skill `description` short (about 40 tokens). Give it the trigger words. Add
  `disable-model-invocation: true` to a skill that only a person must start.
- A rule has `paths:` frontmatter. Every glob must match a tracked file (`scripts/check_knowledge.py`
  checks it).
- Write paths in backticks, relative to the repo root, so the check can find them.
- Write what is true now. Do not write history ("we changed X to Y"). Git keeps the history.
- Write in STE100 (`writing-style` skill).
- Do not save project facts in personal Claude memory. Put them in the repo, so every contributor gets
  them.
- When your change makes a statement wrong, fix it in the same commit.
