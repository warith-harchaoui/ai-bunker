"""WCAG contrast audit over the site figures' colour tokens.

Why this exists
---------------
``scripts/audit_contrast.py`` audits the dashboard, whose colours are plain
``--token: #hex`` declarations. The site's figures are different: they are
hand-authored SVG whose text sits on **tints of the brand colours themselves**
(a stage card is its own hue at 8-10% over a 5% band over the page), so the
background a label lands on is a function of the label's own colour. A token
that passes against white can fail against its own card, and
``--brand-orange-rgb`` did exactly that.

The failures this catches are light-scheme-only, which is the point. The
figures originally carried a fixed ``#8A8A92`` for sub-labels: 5.74:1 against
the dark page and 3.43:1 against white. A review done in dark mode cannot see
it, and that is how it shipped.

Declared pairs, not discovered ones
-----------------------------------
Reading which text lands on which rectangle out of the SVG would mean
implementing SVG painting order and geometry. Instead the pairs are written
down here, from the figures' source. That has a real cost -- a new figure whose
pairing is not listed is not audited -- and a real benefit: it refuses to
report pairs that never render. An earlier version of this audit "found" grey
text failing on the green bar of ``floor_bar``; the bar spans y=42..56 and the
text sits at y=76. Nothing was wrong, and fixing it would have made the figure
worse.

    python scripts/audit_figures.py

Exits non-zero on a failure, so it can gate a commit.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from ai_bunker.adopt import site_root

ROOT = Path(__file__).resolve().parent.parent

#: The stylesheet the figure tints are declared in. `None` when the site is
#: not on this machine -- it lives outside this repository now, so this gate
#: has nothing to audit rather than something to fail on.
_SITE = site_root()
CSS = (_SITE / "css" / "tailwind-input.css") if _SITE else None

#: Page background per scheme, read from ``<body>``'s classes rather than a token.
PAGE = {"light": (255, 255, 255), "dark": (0x0B, 0x0B, 0x0C)}

#: The band every flow-diagram card sits on: the blue token at 5% over the page.
BAND = ("blue", 0.05)

#: Each card: the token tinting it and the opacity, over the band.
CARDS = {
    "orange card": ("orange", 0.10),
    "blue card": ("blue", 0.10),
    "red card": ("red", 0.08),
}

#: (ink token, surface, what renders it). Written from web/pages/_figures.py.
#: ``None`` as a surface means the page itself.
PAIRS = [
    ("muted", None, "floor_bar / roofline axis labels"),
    ("muted", "band", "flow: text inside the gateway band"),
    ("muted", "orange card", "flow 01: 'secrets out, injection in'"),
    ("muted", "blue card", "flow 02/03 sub-labels"),
    ("muted", "red card", "flow 04: 'the command has not run yet'"),
    ("blue", "orange card", "flow 01 title"),
    ("blue", "blue card", "flow 02/03 titles and markers"),
    ("blue", "red card", "flow 04 title"),
    ("orange", "orange card", "flow: the '01' marker"),
    ("red", "red card", "flow: the '04' marker and 'refused as a tool result'"),
    ("red", "blue card", "flow 03: '413 - names the culprit'"),
]

#: Every pair above is text at 10.5-13px, which is never WCAG "large text"
#: (>=18.66px bold / >=24px), so they all carry the 4.5:1 floor.
FLOOR = 4.5


def _tokens(scheme: str) -> dict[str, tuple[int, int, int]]:
    """Resolve the brand + figure tokens for one scheme out of the CSS source."""
    text = CSS.read_text(encoding="utf-8")
    dark_at = text.find('[data-color-scheme="dark"]')
    if dark_at < 0:
        raise SystemExit(f"{CSS}: no dark-scheme block; the audit cannot be trusted")
    block = text[:dark_at] if scheme == "light" else text[dark_at:]
    found = {}
    for name, r, g, b in re.findall(
        r"--(?:brand|fig)-([a-z]+)-rgb:\s*(\d+)\s+(\d+)\s+(\d+)", block
    ):
        found.setdefault(name, (int(r), int(g), int(b)))
    return found


def _luminance(colour: tuple[int, int, int]) -> float:
    def channel(v: float) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = colour
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _over(fg: tuple[int, int, int], alpha: float, bg: tuple[int, int, int]):
    return tuple(round(fg[i] * alpha + bg[i] * (1 - alpha)) for i in range(3))


def audit(scheme: str, quiet: bool = False) -> list[str]:
    tok = _tokens(scheme)
    missing = {t for t, _, _ in PAIRS} | {BAND[0]} | {c[0] for c in CARDS.values()}
    if absent := sorted(missing - set(tok)):
        raise SystemExit(
            f"{scheme}: tokens declared in the audit but absent from the CSS: {absent}"
        )

    page = PAGE[scheme]
    band = _over(tok[BAND[0]], BAND[1], page)
    surfaces = {None: page, "band": band}
    for name, (token, alpha) in CARDS.items():
        surfaces[name] = _over(tok[token], alpha, band)

    failures = []
    for ink, surface, what in PAIRS:
        ratio = contrast(tok[ink], surfaces[surface])
        if not quiet:
            # `--quiet` said "only report failures" and printed every pair
            # anyway. A flag that does not do what it says is a flag that
            # teaches people not to read the others.
            verdict = "ok " if ratio >= FLOOR else "FAIL"
            print(f"  {verdict} {ratio:5.2f}  {ink:6} on {surface or 'page'!s:11}  {what}")
        if ratio < FLOOR:
            failures.append(f"{scheme}: {ink} on {surface or 'page'} is {ratio:.2f}:1 ({what})")
    return failures


# ---------------------------------------------------------------------------
# The repository's own figures, which are always on this machine
# ---------------------------------------------------------------------------
#
# The half above audits the website, which lives outside this repository -- so
# in continuous integration it finds no stylesheet, prints a line saying so,
# and exits zero. A gate that is a no-op in the only place it gates is not a
# gate, and `assets/figure-*.svg` closes that: they are committed here, they
# are read on GitHub in both colour schemes, and they are drawn from the two
# palettes in `scripts/make_figures.py`.
#
# Those palettes are the source, rather than the SVG files, because the files
# are generated from them and `make_figures.py --check` already refuses a file
# that has drifted from its generator. Reading the palette is reading what the
# figures are made of; parsing the output would be checking the same thing
# twice and missing the generator.

#: The page each scheme's figures are read on. The light one is white; the
#: dark one is GitHub's canvas, not the site's `#0B0B0C`. The difference is
#: eight points of lightness and it is enough to fail a pair: the site's muted
#: grey scores 4.41:1 on the orange card over this page.
ASSET_PAGE = {"light": "page", "dark": "page"}

#: Surfaces a label can land on, in painting order. A stage card in the
#: pipeline figure sits inside the gateway band, so its backdrop is a tint
#: over a tint over the page -- which is exactly the composition that makes a
#: colour pass against white and fail against its own card.
ASSET_SURFACES = {
    "band": ("blue", "BAND", None),
    "blue card": ("blue", "CARD", "band"),
    "orange card": ("orange", "CARD", "band"),
}

#: (ink, surface, what renders it). Declared from the figures' source, in the
#: same spirit as `PAIRS` above: a pair that never renders is a pair worth not
#: reporting.
ASSET_PAIRS = [
    ("ink", None, "plan / trade: titles, row names, point labels"),
    ("muted", None, "plan / trade: sub-labels, axis ticks, the closing note"),
    ("blue", None, "plan / trade: the section heading"),
    ("orange", None, "plan: the marker on the text-to-image row"),
    ("green", None, "plan: the marker on the coder row"),
    ("red", None, "trade: the note naming the machines that lose the coder"),
    ("blue", "band", "pipeline: AI-BUNKER, inside the gateway band"),
    ("ink", "orange card", "pipeline 01/04: the stage titles"),
    ("muted", "orange card", "pipeline 01/04: the sub-labels"),
    ("orange", "orange card", "pipeline: the '01' and '04' markers"),
    ("ink", "blue card", "pipeline 02/03: the stage titles"),
    ("muted", "blue card", "pipeline 02/03: the sub-labels"),
    ("blue", "blue card", "pipeline 02/03: the markers"),
]


def _figures_module():
    """`scripts/make_figures.py`, imported by path.

    `scripts/` is a directory of programs rather than a package, so there is
    no name to import. Loading it by path is the honest spelling of "read the
    palette out of the file that defines it".
    """
    import importlib.util

    path = ROOT / "scripts" / "make_figures.py"
    spec = importlib.util.spec_from_file_location("make_figures", path)
    if spec is None or spec.loader is None:  # pragma: no cover - unreachable
        raise SystemExit(f"{path}: cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rgb(value: str) -> tuple[int, int, int]:
    """`#RRGGBB` as three integers."""
    h = value.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def audit_assets(scheme: str, quiet: bool = False) -> list[str]:
    """Every declared pair in `assets/figure-*.svg`, for one scheme."""
    figures = _figures_module()
    palette = {
        k: _rgb(v) for k, v in (figures.LIGHT if scheme == "light" else figures.DARK).items()
    }
    alphas = {"BAND": figures.BAND_ALPHA, "CARD": figures.CARD_ALPHA}

    surfaces: dict[str | None, tuple[int, int, int]] = {None: palette["page"]}
    for name, (token, alpha, over) in ASSET_SURFACES.items():
        weight = alphas[alpha] if isinstance(alpha, str) else alpha
        surfaces[name] = _over(palette[token], weight, surfaces[over])

    failures = []
    for ink, surface, what in ASSET_PAIRS:
        ratio = contrast(palette[ink], surfaces[surface])
        if not quiet:
            verdict = "ok " if ratio >= FLOOR else "FAIL"
            print(f"  {verdict} {ratio:5.2f}  {ink:6} on {surface or 'page'!s:11}  {what}")
        if ratio < FLOOR:
            failures.append(f"{scheme}: {ink} on {surface or 'page'} is {ratio:.2f}:1 ({what})")
    return failures


# ---------------------------------------------------------------------------
# Geometry: the half a contrast audit cannot see
# ---------------------------------------------------------------------------
#
# The audit above measures the one thing that is easy to measure, and it was
# green while `assets/figure-trade.svg` had dashed gridlines running through
# the glyphs of two labels. Contrast was never what was wrong. A reader's
# first complaint about a figure is almost never a ratio -- it is a rule
# through a word, or a word off the edge -- and both are decidable from the
# markup, with no browser and no model.
#
# What this does NOT do: it does not know whether the chart answers the
# question, whether the colours carry meaning, or whether the story is the
# right one. Those need eyes. This is the part that does not.

#: Roboto's vertical metrics as fractions of the font size: how far a capital
#: reaches above the baseline, and a descender below it. From the font's own
#: `capHeight` (1456/2048) and `descender` (512/2048), rounded outward.
CAP_HEIGHT = 0.72
DESCENDER = 0.26

#: How far a rule has to stay outside that ink band before it stops reading as
#: a strikethrough. Two pixels is not aesthetic slack -- a rule one pixel under
#: a baseline is an underline, and an underline nobody asked for is the same
#: defect wearing a different name.
CLEARANCE = 2.0

#: Average advance per character, in em, for the font stack these figures
#: declare. Measured rather than assumed: eleven real strings from the three
#: figures were rendered with `rsvg-convert` at eight times size and their ink
#: extents divided by their character counts. The weighted mean is 0.457 em;
#: the spread is 0.437 (lower-case prose) to 0.547 (a line of capitals), which
#: is why there are two numbers here instead of one.
#:
#: They are used in opposite directions on purpose. A collision test wants the
#: **widest** a string could be, so it cannot miss an overlap. An off-canvas
#: test wants the **narrowest**, so it cannot invent an overflow. Anything in
#: between is reported by neither, which is the honest shape for an estimate.
ADVANCE_WIDE = 0.55
ADVANCE_NARROW = 0.43

#: Characters a `<text>` may contain that the advance model does not describe.
#: An ampersand entity is five characters of markup and one of ink, and left
#: unexpanded it would inflate every width that contains one.
ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"}

SVG_NS = "{http://www.w3.org/2000/svg}"


def _font_sizes(style: str) -> dict[str, float]:
    """`font-size` per selector, read out of the figure's own stylesheet.

    Read rather than imported from `make_figures.py` because this half is a
    parse of the committed file: the contrast half reads the generator, since
    a palette is what the figures are *made of*, while a collision is a fact
    about the bytes that shipped.
    """
    sizes: dict[str, float] = {}
    for selectors, block in re.findall(r"([^{}]+)\{([^}]*)\}", style):
        found = re.search(r"font-size:\s*([\d.]+)px", block)
        if not found:
            continue
        for selector in selectors.split(","):
            sizes[selector.strip()] = float(found.group(1))
    return sizes


def _size_of(classes: str, sizes: dict[str, float]) -> float:
    """The size a `<text class="...">` renders at.

    Later rules win, as in a stylesheet, and `text` is the base every one of
    them overrides. The figures use single-class selectors only, which is why
    this is six lines rather than a cascade.
    """
    size = sizes.get("text", 12.0)
    for name in classes.split():
        if f".{name}" in sizes:
            size = sizes[f".{name}"]
    return size


def _text_width(content: str, size: float, advance: float) -> float:
    """A string's width in user units, from the measured advance model."""
    for entity, char in ENTITIES.items():
        content = content.replace(entity, char)
    return len(content) * size * advance


def _rules(d: str) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    """A path's straight segments, split into horizontal and vertical.

    Each is `(constant, from, to)`: a horizontal is `(y, x0, x1)` and a
    vertical is `(x, y0, y1)`. A tiny walker over the `M`/`H`/`V`/`L` subset
    these figures use. A curve contributes nothing, which is the right answer:
    a rule this cannot read is a rule it must not guess about.

    Both orientations are collected because both can strike a word, and the
    first version of this collected only one. The budget figure's compaction
    trigger is a vertical dash the length of two bars, and it ran straight
    through a label while the audit reported the figure clean.
    """
    tokens = re.findall(r"([MHVL])\s*([-\d.\s]*)", d)
    horizontal: list[tuple[float, float, float]] = []
    vertical: list[tuple[float, float, float]] = []
    x = y = 0.0
    for command, raw in tokens:
        numbers = [float(n) for n in re.findall(r"-?[\d.]+", raw)]
        if command == "M" and len(numbers) >= 2:
            x, y = numbers[0], numbers[1]
        elif command == "H" and numbers:
            horizontal.append((y, min(x, numbers[-1]), max(x, numbers[-1])))
            x = numbers[-1]
        elif command == "V" and numbers:
            vertical.append((x, min(y, numbers[-1]), max(y, numbers[-1])))
            y = numbers[-1]
        elif command == "L" and len(numbers) >= 2:
            if abs(numbers[1] - y) < 0.01:
                horizontal.append((y, min(x, numbers[0]), max(x, numbers[0])))
            elif abs(numbers[0] - x) < 0.01:
                vertical.append((x, min(y, numbers[1]), max(y, numbers[1])))
            x, y = numbers[0], numbers[1]
    return horizontal, vertical


def _labels(root, sizes: dict[str, float]) -> list[tuple[str, float, float, float, str]]:
    """Every untransformed `<text>`, as `(content, x, y, size, anchor)`.

    Rotated text is skipped and said to be skipped: the y-axis title is turned
    ninety degrees, so its baseline is a column rather than a row and none of
    the arithmetic below applies to it. Pretending otherwise would be a
    finding about a label that is fine.
    """
    out = []
    for node in root.iter(f"{SVG_NS}text"):
        if node.get("transform"):
            continue
        content = "".join(node.itertext()).strip()
        if not content:
            continue
        out.append(
            (
                content,
                float(node.get("x", 0)),
                float(node.get("y", 0)),
                _size_of(node.get("class", ""), sizes),
                node.get("text-anchor", "start"),
            )
        )
    return out


def _span(x: float, width: float, anchor: str) -> tuple[float, float]:
    """A label's horizontal extent, given where it is anchored."""
    if anchor == "middle":
        return x - width / 2, x + width / 2
    if anchor == "end":
        return x - width, x
    return x, x + width


def audit_geometry(path: Path, quiet: bool = False) -> list[str]:
    """Rules through words, and words off the canvas, in one committed figure."""
    import xml.etree.ElementTree as ET

    source = path.read_text(encoding="utf-8")
    root = ET.fromstring(source)
    style = "".join("".join(n.itertext()) for n in root.iter(f"{SVG_NS}style"))
    sizes = _font_sizes(style)
    labels = _labels(root, sizes)

    rules: list[tuple[float, float, float]] = []
    uprights: list[tuple[float, float, float]] = []
    for node in root.iter(f"{SVG_NS}path"):
        across, down = _rules(node.get("d", ""))
        rules += across
        uprights += down

    _, _, view_w, view_h = (float(v) for v in root.get("viewBox", "0 0 0 0").split())

    findings = []
    for content, x, y, size, anchor in labels:
        top = y - CAP_HEIGHT * size - CLEARANCE
        bottom = y + DESCENDER * size + CLEARANCE
        wide = _span(x, _text_width(content, size, ADVANCE_WIDE), anchor)
        for rule_y, rule_from, rule_to in rules:
            if top <= rule_y <= bottom and rule_from < wide[1] and rule_to > wide[0]:
                findings.append(
                    f"{path.name}: a rule at y={rule_y:.1f} crosses "
                    f"{content[:44]!r} (baseline y={y:.1f}, {size:g}px)"
                )
                break

        narrow = _span(x, _text_width(content, size, ADVANCE_NARROW), anchor)
        for rule_x, rule_from, rule_to in uprights:
            if narrow[0] <= rule_x <= narrow[1] and rule_from < y and rule_to > top:
                findings.append(
                    f"{path.name}: a rule at x={rule_x:.1f} crosses "
                    f"{content[:44]!r} (x {narrow[0]:.0f}..{narrow[1]:.0f})"
                )
                break

        if narrow[0] < 0 or narrow[1] > view_w or y - size > view_h or y < 0:
            findings.append(
                f"{path.name}: {content[:44]!r} leaves the "
                f"{view_w:g}x{view_h:g} canvas (x {narrow[0]:.0f}..{narrow[1]:.0f}, y {y:.0f})"
            )

    # Labels against each other. Two strings whose ink bands overlap and whose
    # spans overlap are one unreadable string, and this is the failure that
    # arrives when a figure is edited rather than when it is drawn: a word
    # grows by four characters and lands on its neighbour. The narrow advance
    # is used here, as for the canvas -- a reported overlap has to be one that
    # is certainly there, not one an estimate could have invented.
    boxes = []
    for content, x, y, size, anchor in labels:
        span = _span(x, _text_width(content, size, ADVANCE_NARROW), anchor)
        boxes.append((content, y - CAP_HEIGHT * size, y + DESCENDER * size, *span))
    for i, (one, top1, bottom1, from1, to1) in enumerate(boxes):
        for two, top2, bottom2, from2, to2 in boxes[i + 1 :]:
            if top1 < bottom2 and top2 < bottom1 and from1 < to2 and from2 < to1:
                findings.append(f"{path.name}: {one[:30]!r} overlaps {two[:30]!r}")

    if not quiet:
        verdict = f"{len(findings)} finding(s)" if findings else "clean"
        count = len(rules) + len(uprights)
        print(f"  {verdict:16} {len(labels):3d} labels, {count:2d} rules   {path.name}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="only report failures")
    args = parser.parse_args()

    failures, checked = [], 0
    for scheme in ("light", "dark"):
        if not args.quiet:
            print(f"{scheme} — assets/figure-*.svg:")
        failures += audit_assets(scheme, quiet=args.quiet)
        checked += len(ASSET_PAIRS)

    figures = sorted((ROOT / "assets").glob("figure-*.svg"))
    if not args.quiet:
        print("geometry — assets/figure-*.svg:")
    for figure in figures:
        failures += audit_geometry(figure, quiet=args.quiet)
    checked += len(figures)

    if CSS is None:
        # The site lives outside this repository, so this half has nothing to
        # read in continuous integration. It used to be the whole program, and
        # the gate was therefore a no-op in the one place it gated.
        print("the site is not on this machine; its figures were not audited")
    else:
        for scheme in ("light", "dark"):
            if not args.quiet:
                print(f"{scheme} — the site:")
            failures += audit(scheme, quiet=args.quiet)
            checked += len(PAIRS)

    print()
    if failures:
        print(f"{len(failures)} finding(s):")
        for f in failures:
            print(f"  {f}")
        return 1
    print(f"{checked} checks across 2 colour schemes and {len(figures)} figure(s)")
    print(f"every pair meets the {FLOOR}:1 floor; no rule crosses a word")
    return 0


if __name__ == "__main__":
    sys.exit(main())
