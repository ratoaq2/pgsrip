"""Make the pgsrip logo, icon, and social preview card.

Run from the repository root:

    uv run --no-project --with fonttools --with resvg-py python scripts/brand.py

It writes these files to docs/images/:

- logo-light.svg, logo-dark.svg, logo-light.png, logo-dark.png: the README header (GitHub light and dark mode)
- icon.svg, icon-32.png ... icon-512.png: favicon and avatar
- social.png: the GitHub social preview. Upload it by hand: Settings, General, Social preview.

The tagline on the social card is the `description` in pyproject.toml. The README shows the same
sentence under the logo. Change both together. To show new file formats, change FORMATS.

All text is drawn as paths from scripts/brand/CascadiaMono.ttf (SIL Open Font License, see
scripts/brand/OFL.txt). So the output does not depend on the fonts of the computer.

The pgsrip name, logo, and icon are not covered by the MIT license of this repository.
"""

import tomllib
from pathlib import Path

import resvg_py
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs' / 'images'
FONT = ROOT / 'scripts' / 'brand' / 'CascadiaMono.ttf'
TAGLINE = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['description']
FORMATS = '.mkv  .mks  .sup  →  .srt  with OCR'

TILE, CREAM, RED, GRAY = '#1c1917', '#fef3c7', '#dc2626', '#a8a29e'
LIGHT = {'text': '#1c1917', 'red': RED}
DARK = {'text': CREAM, 'red': '#ef4444'}
GITHUB_DARK = '#0d1117'

# 'pgs' as pixel letters: 4 columns, 5 rows above the baseline, 2 rows below
GLYPHS = {
    'p': ['1110', '1001', '1001', '1001', '1110', '1000', '1000'],
    'g': ['0111', '1001', '1001', '1001', '0111', '0001', '1110'],
    's': ['0111', '1000', '0110', '0001', '1110', '0000', '0000'],
}
CELL, GAP = 7, 0.4
X_HEIGHT = 5 * CELL - GAP
RIP_X = 3 * 5 * CELL + 4  # 'rip' starts after 'pgs', plus a small space


def font(weight: int) -> TTFont:
    f = TTFont(FONT)
    return instantiateVariableFont(f, {a.axisTag: weight if a.axisTag == 'wght' else None for a in f['fvar'].axes})


def text_path(f: TTFont, text: str, scale: float, baseline: float) -> tuple[str, float]:
    """Text as SVG path data, from x=0. Returns (d, width)."""
    glyphs, cmap = f.getGlyphSet(), f.getBestCmap()
    pen, x = SVGPathPen(glyphs), 0.0
    for ch in text:
        glyph = glyphs[cmap[ord(ch)]]
        glyph.draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        x += glyph.width * scale
    return pen.getCommands(), x


def squares(x: float, y: float, rows: list[str], size: float, color: str, gap: float) -> str:
    return ''.join(
        f'<rect x="{x + c * size:.1f}" y="{y + r * size:.1f}" width="{size - gap:.1f}" height="{size - gap:.1f}" '
        f'fill="{color}"/>'
        for r, row in enumerate(rows)
        for c, v in enumerate(row)
        if v == '1'
    )


def icon() -> str:
    """A clapperboard. Under the stick, two subtitle lines: red pixels that become cream text."""
    stripes = ''.join(
        f'<path d="M{x} 14 h14 l-10.8 18 h-14 Z" fill="{CREAM if i % 2 else RED}"/>'
        for i, x in enumerate(range(12, 106, 14))
    )
    out = (
        f'<rect width="100" height="100" rx="22" fill="{TILE}"/>'
        '<clipPath id="stick"><rect x="12" y="14" width="76" height="18" rx="3"/></clipPath>'
        f'<g clip-path="url(#stick)">{stripes}</g>'
    )
    s = 7.5
    h = 2 * s - s * 0.24
    for y, end in ((44, 86), (66, 70)):
        x = 14 + 4 * s + 2
        out += squares(14, y, ['1011', '1101'], s, RED, s * 0.24)
        out += f'<rect x="{x}" y="{y}" width="{end - x}" height="{h:.1f}" rx="{h / 2:.1f}" fill="{CREAM}"/>'
    return out


def logo(colors: dict[str, str], rip: tuple[str, float]) -> tuple[str, float]:
    """The icon, then 'pgs' in pixels and 'rip' in letters. Returns (SVG body, width). The height is 100."""
    word = ''.join(squares(i * 5 * CELL, 0, GLYPHS[ch], CELL, colors['red'], GAP) for i, ch in enumerate('pgs'))
    word += f'<path transform="translate({RIP_X} 0)" d="{rip[0]}" fill="{colors["text"]}"/>'
    body = (
        f'<svg width="100" height="100" viewBox="0 0 100 100">{icon()}</svg>'
        f'<g transform="translate(124 {50 - X_HEIGHT / 2:.1f})">{word}</g>'
    )
    return body, 124 + RIP_X + rip[1]


def svg(body: str, w: float, h: float) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.1f} {h:.1f}" width="{w:.0f}" height="{h:.0f}">'
        f'{body}</svg>'
    )


def png(name: str, content: str, w: float, h: float) -> None:
    data = resvg_py.svg_to_bytes(svg_string=content, width=round(w), height=round(h), skip_system_fonts=True)
    (OUT / name).write_bytes(bytes(data))


def centered(f: TTFont, text: str, size: float, baseline: float, color: str) -> str:
    d, w = text_path(f, text, size / f['head'].unitsPerEm, baseline)
    return f'<path transform="translate({(1280 - w) / 2:.1f} 0)" d="{d}" fill="{color}"/>'


def main() -> None:
    bold, regular = font(700), font(400)
    rip = text_path(bold, 'rip', X_HEIGHT / bold['OS/2'].sxHeight, X_HEIGHT)

    for name, colors in (('logo-light', LIGHT), ('logo-dark', DARK)):
        body, w = logo(colors, rip)
        (OUT / f'{name}.svg').write_text(svg(body, w, 100) + '\n', encoding='utf-8')
        png(f'{name}.png', svg(body, w, 100), w * 4, 400)

    (OUT / 'icon.svg').write_text(svg(icon(), 100, 100) + '\n', encoding='utf-8')
    for size in (32, 64, 256, 512):
        png(f'icon-{size}.png', svg(icon(), 100, 100), size, size)

    body, w = logo(DARK, rip)
    scale = 2.6
    card = (
        f'<rect width="1280" height="640" fill="{GITHUB_DARK}"/>'
        f'<g transform="translate({(1280 - w * scale) / 2:.1f} 130) scale({scale})">{body}</g>'
        + centered(regular, TAGLINE, 44, 470, CREAM)
        + centered(regular, FORMATS, 28, 530, GRAY)
    )
    png('social.png', svg(card, 1280, 640), 1280, 640)


if __name__ == '__main__':
    main()
