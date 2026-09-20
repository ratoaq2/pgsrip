# Subtitle samples

Small PGS subtitles used as test fixtures.

`placeholder.en.sup` holds three subtitles of placeholder text. It was made with
`pgsrip scrub --redact synthetic`, so it has the structure of a real subtitle
track but none of its content.

To add a sample from a bug report, ask the reporter for a scrubbed subtitle:

    pgsrip scrub "their-media.mkv"

Add only scrubbed samples. A sample that holds the original images holds the
content of a commercial media, and cannot be part of this repository.
