---
name: writing-style
description: ASD-STE100 rules and examples. Use to write or review docs, comments, commits, PRs, issues, release notes, or error messages.
---

# Writing style (ASD-STE100)

Most readers of pgsrip are technical people who are not native English speakers. Many use a translation
tool. Write so that a reader or a tool cannot read a sentence in two ways.

Two modes:

- **Strict**: error messages, log messages, CLI help, procedures, and issue replies. Apply all rules.
- **Light**: docs, PR bodies, comments, and release notes. Apply the structure rules. Use the word rules
  as a direction.

## Structure rules

1. One idea in each sentence. At most 20 words for an instruction, and at most 25 words for a description.
2. Active voice: "The ripper drops the item", not "The item is dropped".
3. Simple tenses: "We found", not "We have found". Keep a compound tense only when it carries
   information, for example "may have failed".
4. No semicolons. Use two sentences.
5. No phrasal verbs: "start", not "spin up". "remove", not "take out".
6. Verbs, not nouns: "analyze the log", not "perform an analysis of the log".
7. At most 3 nouns in a row.
8. Use a list for 3 or more steps or conditions.
9. One topic in each paragraph, at most 6 sentences.

## Word rules

- Use one word for one thing in a document. Do not change between "track", "stream", and "subtitle" for
  the same thing.
- Use common words. Define a domain term (PGS, ODS, PCS) once, where the reader first sees it.
- No filler: "simply", "just", "easily", "basically", "in order to", "leverage".
- No marketing adjectives: "robust", "seamless", "powerful", "blazing-fast". Give the number.
- No idioms and no emoji.

## Do not change

- Code, commands, log output, error text from other tools, and quotes. Copy them exactly.
- A hedge ("may", "sometimes"). A shorter sentence must not claim more than the source.
- Facts. Do not add a cause or a number that the source does not give.

## Before you finish

Scan the text for these 6 problems: many names for one thing, stacked hedges, nouns made from verbs,
marketing adjectives, long joined sentences, and phrasal verbs. `reference.md` has examples.

Adapted from [danyuchn/asd-ste100-skill](https://github.com/danyuchn/asd-ste100-skill) (MIT). This skill
does not contain the ASD-STE100 dictionary.
