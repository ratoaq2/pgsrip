---
name: ship
description: Check knowledge, run checks, commit, push, and open the draft PR. Use to commit, push, open a PR, or finish work.
---

# Ship

Read `CONTRIBUTING.md` first. Follow it for the branch, commit, and PR rules. Do not copy them here.

## 1. Smaller diff

Read the diff (`git diff main...`) with the "Code: lazy senior dev" steps of `CLAUDE.md`. Remove code
that the change does not need: unused options, new helpers that copy existing code, and extra
abstractions. For a large diff, also run `/simplify`.

## 2. Knowledge check

This step keeps the AI knowledge correct. Do not skip it.

1. Run `uv run python scripts/check_knowledge.py --changed`. It lists the rules that cover the changed
   files, and the docs that the rules link to.
2. Read each listed rule and doc. Compare each statement with the diff (`git diff main...`).
3. Also check:
   - `docs/architecture.md`, if you added, removed, or renamed a module.
   - The commands in `CLAUDE.md` and the setup in `CONTRIBUTING.md`, if you changed the tools.
   - `CLAUDE.md`, if the change makes one of its rules wrong.
4. Fix each wrong statement in the same commit as the code change. Follow `.claude/rules/knowledge.md`.
5. If you learned a fact that the next person needs, add it to the correct owner file.

## 3. Checks

Run `bash scripts/test.sh`. It must pass. It also runs `uv run python scripts/check_knowledge.py`.
Fix the failures. Do not skip hooks.

## 4. Commits

- Bug fix: the `test:` commit with the failing test must come before the `fix:` commit.
- One-line Conventional Commits subject. Add a `Closes #<n>` line to the fix commit.
- Show the user the commit list before you push.

## 5. Push and PR

1. **Ask before you push.** Then run `git push -u origin <branch>`.
2. Write the PR body from `.github/pull_request_template.md`. For a large item, use
   `plans/<item>/summary.md` as the source. Write in STE100 (`writing-style` skill).
3. Run `gh pr create --draft --title "<plain title>" --body-file <file>`.
4. Read the PR diff and the body one more time. Fix problems. Then ask the user, and run `gh pr ready`.
5. Update the item `README.md`: `Stage: ship`, the PR link, and the next step (review or merge).
