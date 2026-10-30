#!/usr/bin/env python3
"""
Measure how wide each character actually is, for the fonts the figures ask for.

Why
---
`scripts/audit_figures.py` decides whether a dashed gridline runs through a
word and whether a label falls off the canvas. Both answers need the width of
a string, and until now it had one number for every character: 0.457 em,
measured across eleven real strings and used at 0.55 for collisions and 0.43
for overflow so that neither direction could invent a finding.

That is honest and it is coarse. A lower-case `l` is a quarter of an em and a
capital `W` is nearly a whole one, so a label of narrow letters was reported as
up to twice its real width and a line of capitals as two thirds of it. A figure
clearing by three pixels was not verified; it was unreported.

So the widths are read from the fonts themselves — `hmtx` divided by
`unitsPerEm`, which is what a renderer uses — one font at a time rather than
one glyph at a time, which is why this finishes in a second where rendering
each character separately did not.

Why a **range** and not a number
---------------------------------
The figures do not ask for a font. They ask for a stack:

    Roboto, 'Helvetica Neue', Helvetica, Arial, sans-serif

A reader gets whichever of those their machine has, and the four differ — the
same string is not the same width on two people's screens. A table of exact
Roboto advances would be exact for a Roboto reader and quietly wrong for
everybody else, which is the false precision this repository refuses
everywhere. So each character gets the **narrowest and widest** advance across
every face a renderer could legitimately pick, and the audit keeps using the
two ends in opposite directions.

The last entry in the stack, `sans-serif`, is whatever the machine decides,
and nothing here can bound it. That is the reason the model stays a range: it
is not an estimate waiting to be sharpened, it is a fact about a font stack.

    python3 scripts/measure_advances.py            # rewrite the table
    python3 scripts/measure_advances.py --check    # fail if it has drifted

Needs `fontTools` and the fonts themselves, so it is a developer tool rather
than a lane step — the table it writes is committed, and that is what the lane
reads. What keeps the two in step without the fonts is in
`tests/test_figures.py`: the table records the stack and the weights it was
measured for, and a test fails the day `make_figures.FONT` stops matching.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TABLE = ROOT / "assets" / "font-advances.json"

#: Each family of the stack, and the file carrying each weight the figures
#: use. A `.ttc` needs the index of the face inside it.
#:
#: The 600 column is the interesting one. Roboto ships no SemiBold here and
#: Helvetica has no Medium at all, so a renderer asked for 600 picks the
#: nearest face it has — Medium where one exists, Bold where none does. Both
#: possibilities are measured, which is what makes the range a bound rather
#: than a guess about somebody's font directory.
FACES: dict[str, dict[int, list[tuple[str, int]]]] = {
    "Roboto": {
        400: [("~/Library/Fonts/Roboto-Regular.ttf", 0)],
        600: [("~/Library/Fonts/Roboto-Medium.ttf", 0), ("~/Library/Fonts/Roboto-Bold.ttf", 0)],
        700: [("~/Library/Fonts/Roboto-Bold.ttf", 0)],
    },
    "Helvetica Neue": {
        400: [("/System/Library/Fonts/HelveticaNeue.ttc", 0)],
        600: [
            ("/System/Library/Fonts/HelveticaNeue.ttc", 10),
            ("/System/Library/Fonts/HelveticaNeue.ttc", 1),
        ],
        700: [("/System/Library/Fonts/HelveticaNeue.ttc", 1)],
    },
    "Helvetica": {
        400: [("/System/Library/Fonts/Helvetica.ttc", 0)],
        600: [("/System/Library/Fonts/Helvetica.ttc", 1)],
        700: [("/System/Library/Fonts/Helvetica.ttc", 1)],
    },
    "Arial": {
        400: [("/System/Library/Fonts/Supplemental/Arial.ttf", 0)],
        600: [("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0)],
        700: [("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0)],
    },
}

#: What the table has to cover: everything a figure could plausibly contain,
#: not only what one does today. Printable Latin-1 plus the typography these
#: figures actually use — an em dash, a middle dot, a narrow no-break space
#: (French punctuation) and the arrow the flow diagram draws with.
#:
#: Coverage is not left to chance: `tests/test_figures.py` fails when a
#: committed figure contains a character this does not, and the audit treats an
#: unmeasured character as a problem rather than falling back to an average.
#: Written as code points rather than as the glyphs themselves. `ruff`'s
#: RUF001 exists to stop a look-alike character sneaking into a string, and
#: two files in this repository carry an exemption because confusables are
#: their subject matter. This one would have been a third, and did not need to
#: be: a code point says which character is meant with no ambiguity to
#: suppress, and the comment says what it is for.
TYPOGRAPHY = (
    "\u2014"  # em dash, in every figure caption
    "\u2013"  # en dash
    "\u2018\u2019\u201c\u201d"  # curly quotes
    "\u2026"  # ellipsis
    "\u202f"  # narrow no-break space, before French punctuation
    "\u2192\u2190"  # the arrows the flow diagram draws with
    "\u00d7"  # multiplication sign
)

ALPHABET = (
    "".join(chr(c) for c in range(0x20, 0x7F))
    + "".join(chr(c) for c in range(0xA0, 0x100))
    + TYPOGRAPHY
)


def _font(path: str, index: int):
    from fontTools.ttLib import TTCollection, TTFont

    resolved = Path(path).expanduser()
    if not resolved.exists():
        raise SystemExit(f"missing font: {resolved}")
    if resolved.suffix.lower() == ".ttc":
        return TTCollection(str(resolved), lazy=True).fonts[index]
    return TTFont(str(resolved), lazy=True)


def _advances(path: str, index: int) -> dict[str, float]:
    """Every character of `ALPHABET` this face carries, in em.

    One pass over the font rather than one render per glyph: `cmap` maps the
    character to a glyph name and `hmtx` gives that glyph's advance, which is
    the number a renderer advances the pen by. Dividing by `unitsPerEm` makes
    it independent of the font's internal grid.

    A character the face does not carry is skipped rather than guessed. The
    renderer would fall back to another font for it, and a width invented here
    would be a width nobody renders.
    """
    font = _font(path, index)
    cmap = font.getBestCmap()
    metrics = font["hmtx"].metrics
    upem = font["head"].unitsPerEm
    out = {}
    for char in ALPHABET:
        glyph = cmap.get(ord(char))
        if glyph is None or glyph not in metrics:
            continue
        out[char] = metrics[glyph][0] / upem
    return out


def measure() -> dict:
    """The table: per weight, per character, the narrowest and widest advance."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from make_figures import FONT

    per_weight: dict[str, dict[str, list[float]]] = {}
    measured: list[dict] = []
    for family, weights in FACES.items():
        for weight, files in weights.items():
            for path, index in files:
                widths = _advances(path, index)
                measured.append(
                    {"family": family, "weight": weight, "file": path, "glyphs": len(widths)}
                )
                bucket = per_weight.setdefault(str(weight), {})
                for char, width in widths.items():
                    low, high = bucket.get(char, (width, width))
                    bucket[char] = (min(low, width), max(high, width))

    return {
        "font_stack": FONT,
        "note": (
            "Advance widths in em, as [narrowest, widest] across every face a "
            "renderer could pick for the declared stack. Written by "
            "scripts/measure_advances.py; do not edit by hand."
        ),
        "faces": measured,
        "advances": {
            weight: {
                char: [round(low, 4), round(high, 4)] for char, (low, high) in sorted(chars.items())
            }
            for weight, chars in sorted(per_weight.items())
        },
    }


def _render(table: dict) -> str:
    """The table as JSON, one character per line.

    `json.dumps(indent=2)` puts each end of each pair on its own line, which
    triples the file and makes a diff unreadable — three hundred lines move
    when one advance changes. A pair belongs on one line, so this writes the
    structure and lets `json.dumps` write the leaves.
    """
    lines = ["{"]
    for key in ("font_stack", "note"):
        lines.append(f"  {json.dumps(key)}: {json.dumps(table[key], ensure_ascii=False)},")
    lines.append('  "faces": [')
    for index, face in enumerate(table["faces"]):
        comma = "," if index < len(table["faces"]) - 1 else ""
        lines.append(f"    {json.dumps(face, ensure_ascii=False)}{comma}")
    lines.append("  ],")
    lines.append('  "advances": {')
    weights = list(table["advances"])
    for windex, weight in enumerate(weights):
        lines.append(f"    {json.dumps(weight)}: {{")
        chars = table["advances"][weight]
        for cindex, (char, pair) in enumerate(chars.items()):
            comma = "," if cindex < len(chars) - 1 else ""
            lines.append(f"      {json.dumps(char, ensure_ascii=False)}: {json.dumps(pair)}{comma}")
        lines.append("    }" + ("," if windex < len(weights) - 1 else ""))
    lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--check", action="store_true", help="fail if the table has drifted")
    args = parser.parse_args()

    fresh = measure()
    rendered = _render(fresh)

    if args.check:
        if not TABLE.exists():
            print(f"{TABLE.relative_to(ROOT)} does not exist; run this without --check")
            return 1
        if TABLE.read_text(encoding="utf-8") != rendered:
            print(f"{TABLE.relative_to(ROOT)} no longer matches the fonts on this machine")
            return 1
        print(f"the advance table matches {len(fresh['faces'])} measured face(s)")
        return 0

    TABLE.write_text(rendered, encoding="utf-8")
    covered = {len(chars) for chars in fresh["advances"].values()}
    print(
        f"wrote {TABLE.relative_to(ROOT)}: {len(fresh['faces'])} faces, "
        f"{sorted(covered)} characters per weight"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
