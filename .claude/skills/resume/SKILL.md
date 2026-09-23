---
name: resume
description: Continue a work item from its plans/ folder in a new session. Use for resume, continue, or "where were we".
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
