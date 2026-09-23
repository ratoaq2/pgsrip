---
name: knowledge-audit
description: Do a full check of all pgsrip AI knowledge files (CLAUDE.md, CONTRIBUTING.md, .claude/rules, .claude/skills, docs) against the current code, and fix wrong, duplicated, or misplaced statements. Use before a release, after a large refactor, or when the user asks to audit, clean up, or check the AI docs.
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
4. Check the HOT cost. `CLAUDE.md` plus `CONTRIBUTING.md` should stay below about 150 lines. Each skill
   `description` should stay below about 300 characters.
5. Show the user a table: file, problem, and proposed fix. Apply the fixes that the user approves.
6. Commit as `docs: update AI knowledge files`.
