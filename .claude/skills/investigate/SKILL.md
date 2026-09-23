---
name: investigate
description: Start work on an issue. Reproduce it, find the root cause, write findings and a failing test. Use to investigate, reproduce, or debug.
---

# Investigate

Read `docs/workflow.md` first. It defines the work folder, the names, and the size decision.

## Steps

1. Get the issue: `gh issue view <n> --comments`.
2. Create `plans/<n>-<slug>/` if it does not exist. Copy `templates/README.md` into it and fill it.
   Set `Stage: investigate`.
3. Create the branch from an up-to-date `main`: `fix/<n>-<slug>` or `feat/<n>-<slug>`.
4. Reproduce the problem:
   - Put scripts and sample files in `plans/<n>-<slug>/repro/`.
   - Try first with the fake backends of the tests (`tests/fabricate.py`). A test that does not need real
     media is better.
   - If you need real media, use a scrubbed sample. Never commit media.
5. Find the root cause. Read the path-scoped rule and the linked doc of each module that you touch.
   Check each claim in the code. Do not guess.
6. Write `findings.md` from `templates/findings.md`. For a small item, notes in `notes.md` are enough.
7. For a bug: write a regression test that fails now. Commit it alone as `test: ...`.
8. Decide the size (small or large) and write it in `README.md`.
9. Update `README.md`: last result and next step. Then:
   - Small: continue with the fix, then `ship`.
   - Large: stop, and propose the `spec` skill.
