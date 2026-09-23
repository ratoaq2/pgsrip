---
name: resume
description: Continue a pgsrip work item in a new session. Read its plans/ folder, report the status, and do the next step. Use when the user says resume, continue, pick up, or "where were we", or names an issue that already has a plans/ folder.
---

# Resume

1. Find the folder:
   - The SessionStart hook shows it when the branch has an issue number.
   - Otherwise, use the number or slug that the user gives: `plans/<n>-*/`.
   - Otherwise, list `plans/*/README.md` with their `Stage` lines and ask the user.
2. Read `README.md`. Then read the stage files in this order, only as far as the current stage:
   `findings.md`, `spec.md`, `plan.md`.
3. Check the real state: `git status`, `git log --oneline main..HEAD`, and `gh issue view <n>`.
   The code and git are correct if `README.md` does not agree with them. Fix `README.md`.
4. Tell the user in 3 to 5 lines: stage, last result, and next step.
5. Do the next step with the skill for that stage: `investigate`, `spec`, `plan`, or `ship`.
