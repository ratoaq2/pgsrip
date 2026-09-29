from __future__ import annotations

import dataclasses
from collections.abc import Sequence

#: filename/CLI token -> TrackFlags boolean field, in canonical filename order.
FLAG_TOKENS: dict[str, str] = {
    'forced': 'forced',
    'sdh': 'hearing_impaired',
    'cc': 'closed_caption',
    'commentary': 'commentary',
    'descriptive': 'descriptive',
}

#: tokens parse() accepts for pre-tagged files to round-trip, but tokens() never produces them: Jellyfin
#: resolves `hi` as Hindi, and `foreign` overlaps with `forced` in every player's own convention.
FLAG_ALIASES: dict[str, str] = {
    'hi': 'hearing_impaired',
    'foreign': 'forced',
}

#: the filename token of the `alternate` field.
ALTERNATE = 'alternate'

#: every token that parse() accepts -> TrackFlags boolean field.
PARSED_TOKENS: dict[str, str] = {**FLAG_TOKENS, **FLAG_ALIASES, ALTERNATE: 'alternate'}

#: matches()-only pseudo-flag: a track carrying none of FLAG_TOKENS' fields.
FULL = 'full'

#: every token accepted by --with/--without: the filename tokens, the non-rendered default/original
#: flags, the alternate flag, and the full pseudo-flag.
FLAG_CHOICES: tuple[str, ...] = (*FLAG_TOKENS, 'default', 'original', ALTERNATE, FULL)


@dataclasses.dataclass(frozen=True)
class TrackFlags:
    forced: bool = False
    hearing_impaired: bool = False
    closed_caption: bool = False
    commentary: bool = False
    descriptive: bool = False
    default: bool = False
    original: bool = False
    alternate: bool = False

    def tokens(self) -> tuple[str, ...]:
        """Filename tokens in canonical order: forced, sdh, cc, commentary, descriptive, alternate."""
        result = [token for token, field in FLAG_TOKENS.items() if getattr(self, field)]
        if self.alternate:
            result.append(ALTERNATE)
        return tuple(result)

    @classmethod
    def parse(cls, tokens: Sequence[str]) -> tuple[TrackFlags, list[str]]:
        """Remove the flag tokens from the end of `tokens`. Return the flags and the remaining tokens."""
        remaining = list(tokens)
        fields: dict[str, bool] = {}
        while remaining and (field := PARSED_TOKENS.get(remaining[-1])):
            fields[field] = True
            remaining.pop()

        return cls(**fields), remaining

    def matches(self, with_flags: frozenset[str], without_flags: frozenset[str]) -> bool:
        """True when the track has one of `with_flags` (or `with_flags` is empty) and none of `without_flags`.

        'full' means no forced, sdh, cc, commentary or descriptive flag. `without_flags` wins over `with_flags`.
        """
        if any(self._has_token(token) for token in without_flags):
            return False
        return not with_flags or any(self._has_token(token) for token in with_flags)

    def _has_token(self, token: str) -> bool:
        if token == FULL:
            return not any(getattr(self, field) for field in FLAG_TOKENS.values())
        if token in FLAG_TOKENS:
            return bool(getattr(self, FLAG_TOKENS[token]))
        return bool(getattr(self, token, False))
