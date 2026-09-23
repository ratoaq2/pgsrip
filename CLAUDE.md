# pgsrip

CLI + library: extracts PGS/SUP subtitles (`.mkv`/`.mks`/`.sup`) and OCRs them into `.srt`.

@CONTRIBUTING.md

## Code

- Narrow `X | None` at the point of use. Never assume that a value is not `None`.
- YAGNI: write the minimum code. No speculative features.
- Use quiet flags (`-q --tb=short`, `-q` on install). Never send full logs into the context.

## Writing

All text follows ASD-STE100 Simplified Technical English. Most readers are not native English speakers.

- One idea in each sentence. Short sentences.
- Active voice and simple tenses.
- Common words. Use one word for one thing.
- No semicolons, no phrasal verbs, no idioms, no filler, no emoji.
- Do not change code, commands, logs, or quotes.

Use the `writing-style` skill for docs, PR, issue, and release text.

## Knowledge

- The rules in `.claude/rules/` load for the paths that they name. They link to `docs/`.
- When a change makes a statement in a knowledge file wrong, fix it in the same commit. The `ship` skill
  runs this check.
- Put project facts in the repo, not in personal memory. `.claude/rules/knowledge.md` tells where.

## Work items

Local work lives in `plans/<issue>-<slug>/` (gitignored). The lifecycle is in `docs/workflow.md`.
Skills: `triage-issue`, `investigate`, `spec`, `plan`, `resume`, `ship`, `release`, `knowledge-audit`.
