#!/usr/bin/env python3
"""
Measure how wide and how tall each character actually is, in the fonts the
figures ask for.

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

And the heights, for the same reason and after the same mistake. The audit
took the top of a label's ink to be `capHeight`, one number for every string:
0.72 em, from Roboto, rounded outward. An accented capital does not stop at
the cap height. `É` reaches **0.907** em in Roboto, 0.915 in Helvetica, 0.896
in Arial — nearly a fifth of an em above the line the audit drew — and the
French half of every figure is full of them: `UN MODÈLE D'IMAGE`, `SYSTÈMES
MÉMOIRE`. A rule two pixels above such a heading sat outside a band that
stopped below the accents, so it was not a near miss, it was not looked at.

Brackets do it too (`(` reaches 0.80 in Roboto) and so does `j`. The ink
extents here are per character, measured with a bounds pen over the glyph
outline, which works for the quadratic and the cubic fonts alike.

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

    python3 scripts/measure_type.py            # rewrite the table
    python3 scripts/measure_type.py --check    # fail if it has drifted

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

TABLE = ROOT / "assets" / "font-metrics.json"

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
    # And the tail of the stack. `sans-serif` is whatever the machine decides,
    # which on a bare Linux box is DejaVu Sans — and DejaVu is **wider than
    # all four named families for 163 of the 201 measured characters**, by up
    # to 0.30 em on a brace. Leaving it out and still calling the result a
    # bound was the residual the previous round wrote down and shipped
    # anyway; a bound that holds for macOS, Windows and Android and fails for
    # Linux is a bound with an asterisk, and an asterisk nobody reads.
    #
    # Liberation Sans is deliberately **not** here, and that is an argument
    # rather than an omission: it is metric-compatible with Arial by design —
    # same advances, glyph for glyph — so it is already inside the Arial
    # column and measuring it would add a column of duplicates.
    #
    # `sans-serif` still is not bounded in general: a reader can configure
    # anything. What changes is that the one font the overwhelming majority of
    # unconfigured Linux readers actually get is now inside the range.
    "DejaVu Sans": {
        400: [("@dejavu/DejaVuSans.ttf", 0)],
        600: [("@dejavu/DejaVuSans-Bold.ttf", 0)],
        700: [("@dejavu/DejaVuSans-Bold.ttf", 0)],
    },
}

#: Where DejaVu Sans might be. Searched in order, and the last entry is the
#: honest one: it is not a system font on macOS, and `matplotlib` bundles it,
#: so a developer who has run anything scientific already has the file. The
#: script fails loudly when none of these exists rather than measuring one
#: family fewer and still calling the result a bound.
DEJAVU_DIRS = (
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    "/opt/homebrew/share/fonts",
    "~/Library/Fonts",
    "@matplotlib",
)

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


def _resolve(path: str) -> Path:
    """A font path, with `@dejavu/` searched over `DEJAVU_DIRS`."""
    if not path.startswith("@dejavu/"):
        return Path(path).expanduser()
    name = path.removeprefix("@dejavu/")
    for directory in DEJAVU_DIRS:
        if directory == "@matplotlib":
            try:
                import matplotlib
            except ImportError:
                continue
            base = Path(matplotlib.__file__).parent / "mpl-data" / "fonts" / "ttf"
        else:
            base = Path(directory).expanduser()
        if (base / name).exists():
            return base / name
    raise SystemExit(
        f"{name} is not in any of {', '.join(DEJAVU_DIRS)} — install DejaVu Sans, or "
        f"the table would be written without the font most Linux readers get"
    )


def _font(path: str, index: int):
    from fontTools.ttLib import TTCollection, TTFont

    resolved = _resolve(path)
    if not resolved.exists():
        raise SystemExit(f"missing font: {resolved}")
    if resolved.suffix.lower() == ".ttc":
        return TTCollection(str(resolved), lazy=True).fonts[index]
    return TTFont(str(resolved), lazy=True)


def _metrics(path: str, index: int) -> dict[str, tuple[float, float, float]]:
    """Every character of `ALPHABET` this face carries: advance, ink top, ink
    bottom — all three in em, all three positive.

    One pass over the font rather than one render per glyph. `cmap` maps the
    character to a glyph name, `hmtx` gives that glyph's advance — the number
    a renderer advances the pen by — and a bounds pen over the outline gives
    how far its ink actually reaches above and below the baseline. Dividing by
    `unitsPerEm` makes all of it independent of the font's internal grid.

    The pen rather than the font's declared `capHeight` and `descender`: those
    are one number for the whole alphabet, and the whole point here is that
    `E` and `É` are not the same height. It also works for both outline
    formats, which matters because Helvetica is cubic and Roboto quadratic.

    A character the face does not carry is skipped rather than guessed. The
    renderer would fall back to another font for it, and a measurement
    invented here would be one nobody renders.
    """
    from fontTools.pens.boundsPen import BoundsPen

    font = _font(path, index)
    cmap = font.getBestCmap()
    advances = font["hmtx"].metrics
    glyphs = font.getGlyphSet()
    upem = font["head"].unitsPerEm
    out = {}
    for char in ALPHABET:
        glyph = cmap.get(ord(char))
        if glyph is None or glyph not in advances or glyph not in glyphs:
            continue
        pen = BoundsPen(glyphs)
        glyphs[glyph].draw(pen)
        # A space has an advance and no outline. Its ink is nothing, which is
        # the right answer rather than a missing one.
        #
        # And both extents are clamped at zero, because a glyph can sit
        # entirely on one side of the baseline: `"` never descends, so its raw
        # `yMin` is *above* the line and a signed depth would be negative. A
        # negative depth used as a band edge pulls the band the wrong way, so
        # a glyph that does not cross the baseline contributes nothing on that
        # side rather than a credit.
        top, bottom = (0.0, 0.0) if pen.bounds is None else (pen.bounds[3], -pen.bounds[1])
        out[char] = (advances[glyph][0] / upem, max(top, 0.0) / upem, max(bottom, 0.0) / upem)
    return out


def measure() -> dict:
    """The table: per weight, per character, four numbers.

    `[narrowest advance, widest advance, highest ink, deepest ink]`, each taken
    across every face a renderer could pick, so each is the extreme in the
    direction the audit needs it. The two advances bound a label's width from
    both sides; the two ink extents bound the band it occupies, and only
    outward — a rule inside that band strikes the word on *somebody's*
    machine, which is the finding worth having.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    from make_figures import FONT

    per_weight: dict[str, dict[str, list[float]]] = {}
    measured: list[dict] = []
    for family, weights in FACES.items():
        for weight, files in weights.items():
            for path, index in files:
                found = _metrics(path, index)
                measured.append(
                    {
                        "family": family,
                        "weight": weight,
                        "file": _resolve(path).name,
                        "glyphs": len(found),
                    }
                )
                bucket = per_weight.setdefault(str(weight), {})
                for char, (advance, top, bottom) in found.items():
                    low, high, over, under = bucket.get(char, (advance, advance, top, bottom))
                    bucket[char] = (
                        min(low, advance),
                        max(high, advance),
                        max(over, top),
                        max(under, bottom),
                    )

    return {
        "font_stack": FONT,
        "note": (
            "Per character, per font-weight: [narrowest advance, widest advance, "
            "highest ink above the baseline, deepest ink below it], in em, across "
            "every face a renderer could pick for the declared stack. Written by "
            "scripts/measure_type.py; do not edit by hand."
        ),
        "faces": measured,
        "metrics": {
            weight: {char: [round(v, 4) for v in values] for char, values in sorted(chars.items())}
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
    lines.append('  "metrics": {')
    weights = list(table["metrics"])
    for windex, weight in enumerate(weights):
        lines.append(f"    {json.dumps(weight)}: {{")
        chars = table["metrics"][weight]
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
    covered = {len(chars) for chars in fresh["metrics"].values()}
    print(
        f"wrote {TABLE.relative_to(ROOT)}: {len(fresh['faces'])} faces, "
        f"{sorted(covered)} characters per weight"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
