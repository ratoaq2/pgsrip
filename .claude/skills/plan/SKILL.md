---
name: plan
description: Turn an approved pgsrip spec into an ordered implementation plan (steps, files, tests, commits), and stop for user approval. Use when the user asks for an implementation plan for a work item that has a spec.
---

# Plan

## Steps

1. Read the item `README.md` and `spec.md`. The spec must be approved. If it is not, stop and ask.
2. Read the code that each step changes. Find existing functions to use again.
3. Write `plan.md` from `templates/plan.md`:
   - Steps in order. Each step has files, a change, and a check.
   - The first commit is the failing test, for a bug.
   - A table of deviations from the spec, with the reason for each one.
4. Update the `README.md`: `Stage: plan`, and next step "user approves the plan".
5. **Stop** for approval.
6. After approval, set `Stage: implement`. Do one step at a time. After each step, run its check and
   write the result in `README.md`. If the work needs more than one round, write each round result in
   `README.md` and keep `plan.md` correct.
