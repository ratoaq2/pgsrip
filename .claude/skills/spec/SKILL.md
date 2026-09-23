---
name: spec
description: Write spec.md for a large work item, then stop for approval. Use for a spec, a design, or to brainstorm a solution.
---

# Spec

Use this for a large work item (see `docs/workflow.md`). A small item does not need a spec.

## Steps

1. Read the item `README.md`, `findings.md`, and `notes.md`.
2. If the goal is not clear, ask the user questions first. Ask one question at a time, and propose an
   answer.
3. Find 2 or 3 approaches. For each one, check the constraints of the rules and docs of the modules that
   it touches.
4. Write `spec.md` from `templates/spec.md`. Select one approach. Write why you rejected the others.
5. Update the `README.md`: `Stage: spec`, last result, and next step "user approves the spec".
6. **Stop.** Show the user a short summary and the decisions they must make. Do not write a plan before
   the user approves.
7. After approval, offer to post a short STE100 summary of the approach to the issue. Post only after
   the user agrees.
