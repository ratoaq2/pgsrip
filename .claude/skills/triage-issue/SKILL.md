---
name: triage-issue
description: Label a GitHub issue and draft a reply to the reporter. Use to triage, label, classify, or reply to issues.
---

# Triage an issue

Goal: each open issue has the correct labels and, when necessary, a reply that asks for the missing
information.

## Steps

1. Read the issue and its comments: `gh issue view <n> --comments`.
2. Check that the labels below still exist: `gh label list`. If they do not match, tell the user and
   update this file.
3. Decide the labels:
   - Exactly one `type:` label.
   - One `status:` label while the issue waits for something. Remove it when the issue is ready for work.
   - One `priority:` label when the issue is classified.
   - One or more `comp:` labels.
   - `no sample file` when a bug needs a sample and the reporter did not attach one.
4. Check if a bug has enough information: the pgsrip version, the command, the full error, and a sample.
   The sample must be scrubbed. The reporter makes it with `pgsrip scrub "<media>"`. See
   `tests/samples/README.md`.
5. Draft a reply in strict STE100 (`writing-style` skill). Ask for each missing item in a separate
   sentence.
6. Show the labels and the reply to the user. **Wait for approval.** Then run
   `gh issue edit <n> --add-label ... --remove-label ...` and `gh issue comment <n> --body-file <file>`.
7. If the user wants to start work, continue with the `investigate` skill.

## Labels

| Label | Use when |
| --- | --- |
| `type: bug` | The behavior is wrong and someone can reproduce it. |
| `type: feature` | A new capability or an enhancement. |
| `type: tech-debt` | Refactoring, dependencies, internal tools. |
| `type: docs` | README or other documentation. |
| `status: triage` | New. Nobody reviewed it yet. |
| `status: waiting-on-author` | We asked the reporter for information. |
| `status: blocked` | It waits for another project or library. |
| `priority: critical` | A crash or a regression for many users, or a broken build. |
| `priority: high` | An important bug or feature for many users. |
| `priority: low` | An edge case or a small improvement. |
| `comp: cli` | Command line, options, file selection. |
| `comp: ocr` | Tesseract, OCR batching, text recognition. |
| `comp: image-processing` | Bitmap decoding, crop, colors. |
| `comp: pgs` | The PGS/SUP binary format. |
| `comp: srt` | The `.srt` output: names, timing, text. |
| `no sample file` | A bug that needs a sample we do not have. |

`good first issue` and `help wanted` stay without a prefix. GitHub shows them to new contributors.

## Many issues

For a review of all open issues, run `gh issue list --state open --limit 100`. Make a table: number,
title, current labels, suggested labels, and one line on the next action. Do not change labels until the
user approves the table.
