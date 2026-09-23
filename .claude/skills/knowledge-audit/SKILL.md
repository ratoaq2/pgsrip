---
name: knowledge-audit
description: Check all AI knowledge files against the code. Fix wrong, duplicated, or misplaced statements.
disable-model-invocation: true
---

# Knowledge audit

`ship` checks only the files that a change touches. This skill checks all of them.

## Steps

1. Run `uv run python scripts/check_knowledge.py`. Fix each error first.
2. List the knowledge files: `CLAUDE.md`, `CONTRIBUTING.md`, `docs/*.md`, `.claude/rules/*.md`,
   `.claude/skills/*/SKILL.md`.
3. For each file, check each statement against the code, `pyproject.toml`, the CI workflows, and
   `gh label list`. Look for:
   - **Wrong**: a name, a number, a command, or a behavior that the code does not have now.
   - **Duplicated**: the same fact in two files. Keep it in the owner file (see
     `.claude/rules/knowledge.md`). Replace the other copy with a link.
   - **Misplaced**: a HOT line that only some tasks need. Move it to a rule, a skill, or a doc.
   - **Missing**: a module without a line in `docs/architecture.md`, or a rule `paths:` glob that does not
     cover a related file.
   - **Style**: text that does not follow `writing-style`.
4. Check the HOT cost with `/context` in a new session:
   - `CLAUDE.md` should stay below about 900 tokens. It imports no other file.
   - Each project skill should stay below about 50 tokens in the skill list.
   - The `skillOverrides` in `.claude/settings.json` should still hide the built-in skills that pgsrip
     does not use.
5. Show the user a table: file, problem, and proposed fix. Apply the fixes that the user approves.
6. Commit as `docs: update AI knowledge files`.
