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

#: version value rendered/parsed as a filename token rather than a boolean field.
ALTERNATE = 'alternate'

#: matches()-only pseudo-flag: a track carrying none of FLAG_TOKENS' fields.
FULL = 'full'

#: every token accepted by --with/--without: the filename tokens, plus the non-rendered
#: default/original flags and the alternate/full pseudo-flags matches() also understands.
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
    version: str | None = None

    def tokens(self) -> tuple[str, ...]:
        """Filename tokens in canonical order: forced, sdh, cc, commentary, descriptive, alternate."""
        result = [token for token, field in FLAG_TOKENS.items() if getattr(self, field)]
        if self.version == ALTERNATE:
            result.append(ALTERNATE)
        return tuple(result)

    @classmethod
    def parse(cls, tokens: Sequence[str]) -> tuple[TrackFlags, list[str]]:
        """Consume recognised flag tokens off the END of tokens. Return (flags, remaining)."""
        remaining = list(tokens)
        forced = hearing_impaired = closed_caption = commentary = descriptive = False
        version: str | None = None
        while remaining:
            token = remaining[-1]
            field = FLAG_TOKENS.get(token) or FLAG_ALIASES.get(token)
            if token == ALTERNATE:
                version = ALTERNATE
            elif field == 'forced':
                forced = True
            elif field == 'hearing_impaired':
                hearing_impaired = True
            elif field == 'closed_caption':
                closed_caption = True
            elif field == 'commentary':
                commentary = True
            elif field == 'descriptive':
                descriptive = True
            else:
                break
            remaining.pop()

        flags = cls(
            forced=forced,
            hearing_impaired=hearing_impaired,
            closed_caption=closed_caption,
            commentary=commentary,
            descriptive=descriptive,
            version=version,
        )
        return flags, remaining

    def matches(self, include: frozenset[str], exclude: frozenset[str]) -> bool:
        """Empty include = allow all. 'full' means no forced/sdh/cc/commentary/descriptive.
        exclude wins over include."""
        if any(self._has_token(token) for token in exclude):
            return False
        return not include or any(self._has_token(token) for token in include)

    def _has_token(self, token: str) -> bool:
        if token == FULL:
            return not any(getattr(self, field) for field in FLAG_TOKENS.values())
        if token == ALTERNATE:
            return self.version == ALTERNATE
        if token in FLAG_TOKENS:
            return bool(getattr(self, FLAG_TOKENS[token]))
        return bool(getattr(self, token, False))
