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

And a geometry half
-------------------
The contrast audit was green while two labels of ``figure-trade.svg`` had a
dashed gridline through their glyphs, so a second half reads the committed
markup for rules through words, labels on labels and text off the canvas.

Both need the width of a string, and that width is **bounded, not computed**:
the figures declare a font *stack*, so the same label is not the same width on
two readers' machines. The bounds come from
``assets/font-metrics.json`` — every character's narrowest and widest advance
and how far its ink reaches above and below the baseline, across the faces a
renderer could pick, written by ``scripts/measure_type.py``. The two width
ends are used in opposite directions, widest for collisions and narrowest for
overflow, so that neither can invent a finding; the ink extents are used
outward in both, because a rule inside that band strikes the word on
*somebody's* machine.

    python scripts/audit_figures.py

Exits non-zero on a failure, so it can gate a commit.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import argparse
import json
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
    # Added in round 37 by `undeclared_pairs`, not by reading the figures
    # again: `AU RETOUR` and `ON THE WAY IN` are muted type inside the band,
    # they have been in the shipped figures the whole time, and this list did
    # not have them. 5.38:1 in light and 5.79:1 in dark, so nothing was
    # broken -- but nothing was watching either, and the twin list for the
    # website had the pair all along.
    ("muted", "band", "pipeline: the direction labels inside the band"),
    ("ink", "orange card", "pipeline 01/04: the stage titles"),
    ("muted", "orange card", "pipeline 01/04: the sub-labels"),
    ("orange", "orange card", "pipeline: the '01' and '04' markers"),
    ("ink", "blue card", "pipeline 02/03: the stage titles"),
    ("muted", "blue card", "pipeline 02/03: the sub-labels"),
    ("blue", "blue card", "pipeline 02/03: the markers"),
]


#: A rect class, and the surface in :data:`ASSET_SURFACES` it paints. Classes
#: the stylesheet gives ``fill: none`` are not surfaces at all -- a stroked
#: outline leaves the page showing through -- and :func:`undeclared_pairs`
#: reads that from the stylesheet rather than listing them here.
RECT_SURFACES = {"band": "band", "card-blue": "blue card", "card-orange": "orange card"}


def _unfilled(style: str) -> set[str]:
    """Class names the stylesheet paints with no fill."""
    out = set()
    for selector, body in re.findall(r"\.([a-z-]+)\s*\{([^}]*)\}", style):
        if re.search(r"fill:\s*none", body):
            out.add(selector)
    return out


def undeclared_pairs() -> list[str]:
    """Ink-on-surface combinations the committed figures render and nothing audits.

    :data:`ASSET_PAIRS` is a hand-written list, and round 36 spent itself on
    what hand-written lists in this repository cost. This derives the same
    thing from the artefacts: every ``<text>`` in every committed figure, its
    ink token read off its class, and its surface found by asking which
    filled rectangle encloses its anchor.

    A rectangle with ``fill: none`` is not a surface -- the page shows
    through a stroked outline -- which is why that is read from the
    stylesheet. A filled rectangle this does not recognise *is* reported,
    because a new tinted shape with type on it is exactly the thing a
    contrast audit must not be silent about.
    """
    import xml.etree.ElementTree as ET

    tokens = {"ink", "muted", "blue", "orange", "green", "red"}
    declared = {(ink, surface) for ink, surface, _ in ASSET_PAIRS}
    findings: list[str] = []
    seen: set[tuple[str, str | None]] = set()

    for path in sorted((ROOT / "assets").glob("figure-*.svg")):
        root = ET.fromstring(path.read_text(encoding="utf-8"))
        style = "".join("".join(n.itertext()) for n in root.iter(f"{SVG_NS}style"))
        hollow = _unfilled(style)

        boxes = []
        for node in root.iter(f"{SVG_NS}rect"):
            name = node.get("class", "")
            if name in hollow:
                continue
            try:
                x, y = float(node.get("x")), float(node.get("y"))
                w, h = float(node.get("width")), float(node.get("height"))
            except (TypeError, ValueError):
                continue
            boxes.append((name, x, y, x + w, y + h))

        for node in root.iter(f"{SVG_NS}text"):
            if not (node.text or "").strip():
                continue
            classes = (node.get("class") or "").split()
            ink = next((c for c in classes if c in tokens), "ink")
            try:
                x, y = float(node.get("x")), float(node.get("y"))
            except (TypeError, ValueError):
                continue
            over = [b for b in boxes if b[1] <= x <= b[3] and b[2] <= y <= b[4]]
            if over:
                nearest = min(over, key=lambda b: (b[3] - b[1]) * (b[4] - b[2]))
                surface = RECT_SURFACES.get(nearest[0])
                if surface is None:
                    findings.append(
                        f"{path.name}: {(node.text or '')[:28]!r} sits on a filled "
                        f"{nearest[0]!r} rectangle, which is not a surface this audit knows"
                    )
                    continue
            else:
                surface = None
            if (ink, surface) in declared or (ink, surface) in seen:
                continue
            seen.add((ink, surface))
            findings.append(
                f"{path.name}: {ink!r} on {surface or 'the page'} renders "
                f"({(node.text or '')[:28]!r}) and ASSET_PAIRS does not declare it"
            )
    return findings


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

#: How far ink falls below the baseline, as a fraction of the font size. From
#: Roboto's own `descender` (512/2048), rounded outward — and it survives the
#: round that deleted its twin because it is a bound that holds: not one of
#: the 201 measured characters descends past it in any of the four faces.
#:
#: Its twin did not. `CAP_HEIGHT = 0.72` stood here and was used as the top of
#: every label's ink, and **147 of the 201 measured characters reach above
#: it** — including every capital letter, since a plain `E` already tops out
#: at 0.729. An accented capital is the extreme: `É` reaches 0.927 em and `Å`
#: 0.950, a quarter of an em over the line the audit drew, and the French half
#: of every figure is built from them — `UN MODÈLE D'IMAGE`, `SYSTÈMES
#: MÉMOIRE`. A rule three pixels above such a heading was not a near miss; it
#: was outside a band that stopped below the accents, so nothing looked at it.
#:
#: Which is the same defect as the one the previous round fixed in the
#: horizontal direction, left standing in the vertical one, and found by
#: asking the question that round ended on: a bound is only a bound if it
#: points outward for *every* character, not for the character somebody had
#: in mind. The tops now come from `assets/font-metrics.json`, per character.
DESCENDER = 0.26

#: How close a rule may come to a label's ink before it reads as a
#: strikethrough, over and above the rule's own thickness.
#:
#: This replaced `CLEARANCE = 2.0`, which was the last chosen number in this
#: module and was doing two jobs at once. A rule is not a line: a `<path>` at
#: y with `stroke-width: 2` covers y-1 to y+1, and that half-width is a
#: **measurable** fact read from the figure's own stylesheet rather than a
#: constant. What is left over is genuinely perceptual -- a rule a pixel clear
#: of a descender is still an underline nobody asked for -- so it is one
#: number with one argument instead of one number with two.
#:
#: Set to 1.5 rather than lower on purpose: the pad for a dashed gridline,
#: whose stroke is 1, then comes to 0.5 + 1.5 = 2.0, exactly what `CLEARANCE`
#: gave it. Nothing becomes less sensitive than it was, and a thicker rule
#: becomes more so, which is the only direction a bound may move.
PROXIMITY = 1.5

#: Default stroke width for a `<path>` whose class declares none. SVG's own
#: initial value, so a rule with no stroke declared is still given a body
#: rather than treated as infinitely thin.
DEFAULT_STROKE = 1.0

#: Per-character type metrics, in em, read out of the fonts the figures ask
#: for by `scripts/measure_type.py` and committed beside them.
#:
#: This replaced one number for every character — 0.457 em, with 0.55 and 0.43
#: used as the two ends. That band was measured and it was honest, and it was
#: also four times too coarse to verify anything: a lower-case `l` is 0.22 em
#: and a capital `W` is 0.94, so a label of narrow letters was reported at up
#: to twice its width and a line of capitals at two thirds of it. A figure
#: clearing by three pixels was not verified, it was unreported.
#:
#: The pairs stay pairs because the figures declare a font **stack**, not a
#: font. A reader gets whichever of Roboto, Helvetica Neue, Helvetica or Arial
#: their machine has, the four differ, and the last entry — `sans-serif` — is
#: whatever the machine decides and cannot be bounded at all. So each
#: character carries the narrowest and widest advance any of those faces
#: gives, and the two ends are still used in opposite directions: the
#: **widest** for collisions, so an overlap cannot be missed, the
#: **narrowest** for overflow, so one cannot be invented.
METRICS = json.loads((ROOT / "assets" / "font-metrics.json").read_text(encoding="utf-8"))

#: Keyed "400"/"600"/"700" — the weights the figures' own stylesheet declares.
PER_WEIGHT: dict[str, dict[str, list[float]]] = METRICS["metrics"]

#: Each entry is `[narrowest advance, widest advance, highest ink above the
#: baseline, deepest ink below it]`, in em.
ADVANCE_LOW, ADVANCE_HIGH, INK_TOP, INK_BOTTOM = 0, 1, 2, 3

#: Characters a `<text>` may contain that the advance model does not describe.
#: An ampersand entity is five characters of markup and one of ink, and left
#: unexpanded it would inflate every width that contains one.
ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'"}

SVG_NS = "{http://www.w3.org/2000/svg}"


def _type_rules(style: str) -> dict[str, dict[str, float]]:
    """Size, weight and letter-spacing per selector, from the figure's own
    stylesheet.

    Read rather than imported from `make_figures.py` because this half is a
    parse of the committed file: the contrast half reads the generator, since
    a palette is what the figures are *made of*, while a collision is a fact
    about the bytes that shipped.

    `letter-spacing` was not read here at all until now, and two of the five
    text classes declare it — `.n` adds 0.1 em after every character and `.h`
    0.08. Thirty-six labels in the committed figures carry one of those, and
    every one of them was being measured up to a tenth narrower than it
    renders. That is the direction that makes a collision test miss a
    collision, which is the only direction that matters.
    """
    rules: dict[str, dict[str, float]] = {}
    for selectors, block in re.findall(r"([^{}]+)\{([^}]*)\}", style):
        found: dict[str, float] = {}
        if size := re.search(r"font-size:\s*([\d.]+)px", block):
            found["size"] = float(size.group(1))
        if weight := re.search(r"font-weight:\s*(\d+)", block):
            found["weight"] = float(weight.group(1))
        if tracking := re.search(r"letter-spacing:\s*(\.?[\d.]+)em", block):
            found["tracking"] = float(tracking.group(1))
        if not found:
            continue
        for selector in selectors.split(","):
            rules.setdefault(selector.strip(), {}).update(found)
    return rules


def _stroke_of(classes: str, style: str) -> float:
    """How thick a `<path class="...">` draws, from the figure's stylesheet.

    The figures declare `stroke-width` on four classes -- 1 for `.axis` and
    `.dash`, 1.5 for `.outline`, 2 for `.wire` -- and the geometry half
    ignored all of it, treating every rule as a line of no thickness and
    padding the text band by a flat two pixels instead. A 2-unit wire covers a
    unit either side of its path, which is half the old pad on its own.
    """
    width = DEFAULT_STROKE
    for selectors, block in re.findall(r"([^{}]+)\{([^}]*)\}", style):
        found = re.search(r"stroke-width:\s*([\d.]+)", block)
        if not found:
            continue
        for selector in selectors.split(","):
            if selector.strip().lstrip(".") in classes.split():
                width = float(found.group(1))
    return width


def _type_of(classes: str, rules: dict[str, dict[str, float]]) -> tuple[float, int, float]:
    """How a `<text class="...">` renders: size, weight, letter-spacing in em.

    Later rules win, as in a stylesheet, and `text` is the base every one of
    them overrides. The figures use single-class selectors only, which is why
    this is ten lines rather than a cascade. A class that sets a size and not a
    weight inherits the weight, which is what a cascade does and what an
    earlier version of this — one dictionary per property — got right by
    accident and would have got wrong at the first class that set two.
    """
    base = rules.get("text", {})
    size = base.get("size", 12.0)
    weight = base.get("weight", 400.0)
    tracking = base.get("tracking", 0.0)
    for name in classes.split():
        rule = rules.get(f".{name}")
        if rule is None:
            continue
        size = rule.get("size", size)
        weight = rule.get("weight", weight)
        tracking = rule.get("tracking", tracking)
    return size, int(weight), tracking


def _unmeasured(content: str, weight: int) -> set[str]:
    """Characters of `content` the metrics table has no measurement for.

    A weight the table has never been measured at makes every character of the
    label unmeasured, which is the right answer: a class that starts declaring
    `font-weight: 800` has to be measured before anything here can be said
    about it.
    """
    table = PER_WEIGHT.get(str(weight), {})
    return {char for char in _plain(content) if char not in table}


def _plain(content: str) -> str:
    """The ink of a `<text>`: markup entities collapsed to the one character
    each of them renders as."""
    for entity, char in ENTITIES.items():
        content = content.replace(entity, char)
    return content


def _text_width(content: str, size: float, weight: int, tracking: float, widest: bool) -> float:
    """A string's width in user units, summed character by character.

    `widest` picks which end of each character's range to take, and the same
    choice is applied to letter-spacing: the wide bound pays for the space
    after the final character and the narrow one does not, because
    implementations disagree about that last one and a bound must not depend
    on which is right.

    Every character must be in the table. There is no fallback, and the
    previous round's was wrong: it gave an unmeasured character the widest
    advance in the table and called the result "still a bound", which it is
    not — nothing says an unmeasured character is narrower than the widest
    measured one, and a glyph wider than 1 em is ordinary. `audit_geometry`
    checks `_unmeasured` first and skips the label, the way it already skips
    rotated text, because a finding computed from an invented width is a
    finding about a label nobody measured.
    """
    table = PER_WEIGHT[str(weight)]
    plain = _plain(content)
    end = ADVANCE_HIGH if widest else ADVANCE_LOW
    total = sum(table[char][end] for char in plain)
    spaced = len(plain) if widest else max(len(plain) - 1, 0)
    return size * (total + spaced * tracking)


def _ink(content: str, size: float, weight: int) -> tuple[float, float]:
    """How far a label's ink reaches above and below its baseline, in user
    units.

    The tallest character sets the top and the deepest sets the bottom, which
    is what a band around a line of type is. One number for every string --
    `capHeight` -- was the bug this replaced: `E` and `É` are not the same
    height, and a figure captioned in French is mostly the second kind.

    One band for the whole label is an approximation, and it is pessimistic in
    a specific way: exact for a rule that crosses the line of type, too
    cautious for a rule passing over a word whose only tall letter is at the
    other end. A silhouette per character would be exact. Measured before
    building it, which is the whole point -- across the 260 pairs of
    horizontal rule and label that share an x-range in the committed figures,
    the band comes within **6.35px** of reporting a crossing and an exact
    silhouette would come within 10.00px. The widest margin the band gives
    away anywhere is 9.88px, and the number of pairs where the two models
    reach a different verdict is **zero**.

    So the exact model buys nothing here, and the band stays. `band_slack`
    recomputes those figures, and
    `test_figures.py::test_the_single_band_per_label_is_not_load_bearing` is
    the trigger: if an edit ever brings a figure within twice `PROXIMITY` of
    the band firing, the pessimism has become load-bearing and the silhouette
    is worth building after all.
    """
    table = PER_WEIGHT[str(weight)]
    plain = _plain(content)
    above = max((table[char][INK_TOP] for char in plain), default=0.0)
    below = max((table[char][INK_BOTTOM] for char in plain), default=DESCENDER)
    return size * above, size * below


def _char_boxes(label: tuple) -> list[tuple[float, float, float, float]]:
    """Each character's own rectangle, where :func:`_ink` answers with one band.

    Wide advances, laid end to end from the label's left edge, unrotated only.
    This is not what the audit uses and is not meant to be: it exists so the
    cost of the band can be measured rather than argued about. See
    :func:`band_slack`.
    """
    content, x, y, size, weight, tracking, anchor, _ = label
    table = PER_WEIGHT[str(weight)]
    plain = _plain(content)
    left, _ = _span(x, _text_width(content, size, weight, tracking, True), anchor)
    boxes = []
    for char in plain:
        advance = size * (table[char][ADVANCE_HIGH] + tracking)
        boxes.append(
            (
                left,
                left + advance,
                y - size * table[char][INK_TOP],
                y + size * table[char][INK_BOTTOM],
            )
        )
        left += advance
    return boxes


def canvas_margins() -> list[tuple[str, str, float]]:
    """``(figure, label, margin)`` for every measurable label, widest bound.

    The margin is the smallest distance from the label's widest possible box
    to any edge of its canvas; negative means it runs off, which is what
    :func:`audit_geometry` reports. Printed by ``--slack`` so the figures
    quoted in `make_figures.py` beside a hand-wrapped caption can be checked
    rather than believed.
    """
    import xml.etree.ElementTree as ET

    out = []
    for path in sorted((ROOT / "assets").glob("figure-*.svg")):
        root = ET.fromstring(path.read_text(encoding="utf-8"))
        style = "".join("".join(n.itertext()) for n in root.iter(f"{SVG_NS}style"))
        width, height = (float(v) for v in root.get("viewBox", "0 0 0 0").split()[2:4])
        for label in _labels(root, _type_rules(style)):
            if label[7] is None or _unmeasured(label[0], label[4]):
                continue
            x0, x1, y0, y1 = _box(label, widest=True)
            out.append((path.name, label[0][:34], min(x0, width - x1, y0, height - y1)))
    return out


def band_slack() -> list[tuple[str, str, float, float]]:
    """What the one-band-per-label approximation costs, per pair, in pixels.

    ``(figure, label, band clearance, exact clearance)`` for every horizontal
    rule that shares an x-range with a measurable unrotated label in the
    committed figures. Clearance is the vertical gap between the rule's body --
    its stroke plus ``PROXIMITY`` -- and the label's ink: positive is a miss,
    negative is the crossing the audit reports.

    The band's clearance is taken against one band for the whole string. The
    exact one is taken against only those characters the rule actually passes
    over, each with its own ink extent, and is therefore never smaller.
    """
    import xml.etree.ElementTree as ET

    out = []
    for path in sorted((ROOT / "assets").glob("figure-*.svg")):
        root = ET.fromstring(path.read_text(encoding="utf-8"))
        style = "".join("".join(n.itertext()) for n in root.iter(f"{SVG_NS}style"))
        across = []
        for node in root.iter(f"{SVG_NS}path"):
            half = _stroke_of(node.get("class", ""), style) / 2
            horizontal, _ = _rules(node.get("d", ""))
            across += [(*segment, half) for segment in horizontal]

        for label in _labels(root, _type_rules(style)):
            content, _, _, _, weight, _, _, rotation = label
            if rotation != 0.0 or _unmeasured(content, weight):
                continue
            x0, x1, y0, y1 = _box(label, widest=True)
            chars = _char_boxes(label)
            for rule_y, rule_from, rule_to, half in across:
                if not _overlaps((rule_from, rule_to), (x0, x1)):
                    continue
                body = (rule_y - half - PROXIMITY, rule_y + half + PROXIMITY)
                gaps = [
                    max(top - body[1], body[0] - bottom)
                    for left, right, top, bottom in chars
                    if _overlaps((rule_from, rule_to), (left, right))
                ]
                if not gaps:
                    continue
                out.append((path.name, content[:30], max(y0 - body[1], body[0] - y1), max(gaps)))
    return out


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


#: `rotate(-90 24 216)` — the angle, and the centre it turns about.
ROTATE = re.compile(r"rotate\(\s*(-?[\d.]+)(?:[\s,]+(-?[\d.]+)[\s,]+(-?[\d.]+))?\s*\)")


def _rotation(transform: str) -> float | None:
    """The angle a `<text>` is turned by, or None when nothing can be said.

    Only quarter turns are handled, because only quarter turns appear: the
    y-axis title of `figure-trade.svg` is `rotate(-90 24 216)`. An angle this
    cannot reason about returns None and is **reported** rather than skipped —
    which is the change this round made. For three rounds `_labels` dropped
    every transformed label and the docstring said so honestly, and the result
    was that the one rotated label in the repository was the only one nothing
    ever looked at, while "the figures are clean" was written three times.
    """
    if not transform:
        return 0.0
    found = ROTATE.fullmatch(transform.strip())
    if found is None:
        return None
    angle = float(found.group(1)) % 360
    return angle if angle in (0.0, 90.0, 270.0) else None


def _labels(root, rules: dict[str, dict[str, float]]) -> list[tuple]:
    """Every `<text>`, as `(content, x, y, size, weight, tracking, anchor,
    rotation)`.

    `rotation` is 0, 90 or 270 degrees, or None for a transform this cannot
    read — the caller reports that rather than ignoring it.
    """
    out = []
    for node in root.iter(f"{SVG_NS}text"):
        content = "".join(node.itertext()).strip()
        if not content:
            continue
        out.append(
            (
                content,
                float(node.get("x", 0)),
                float(node.get("y", 0)),
                *_type_of(node.get("class", ""), rules),
                node.get("text-anchor", "start"),
                _rotation(node.get("transform", "")),
            )
        )
    return out


def _span(x: float, width: float, anchor: str) -> tuple[float, float]:
    """A label's extent along its own baseline, given where it is anchored."""
    if anchor == "middle":
        return x - width / 2, x + width / 2
    if anchor == "end":
        return x - width, x
    return x, x + width


def _box(label: tuple, widest: bool) -> tuple[float, float, float, float]:
    """The rectangle a label occupies: `(x0, x1, y0, y1)`.

    For unrotated text the length runs along x and the ink band along y. For a
    quarter turn the two swap, and the arithmetic is exact rather than
    approximate because `rotate(a cx cy)` is: for `rotate(-90 cx cy)`, a point
    `(px, py)` becomes `(cx + py - cy, cy - px + cx)`. The label is anchored at
    the centre of its own rotation in every figure here, which is what makes
    the result one subtraction rather than a matrix.

    `widest` picks which end of the width range to use, and the caller decides
    per check: the wide box for anything whose failure is *missing* a defect,
    the narrow one for anything whose failure is *inventing* one.
    """
    content, x, y, size, weight, tracking, anchor, rotation = label
    above, below = _ink(content, size, weight)
    length = _span(x, _text_width(content, size, weight, tracking, widest), anchor)

    if rotation == 0.0:
        return length[0], length[1], y - above, y + below
    if rotation == 270.0:  # rotate(-90): the text reads bottom-to-top
        return x - above, x + below, y - (length[1] - x), y - (length[0] - x)
    # rotate(90): top-to-bottom
    return x - below, x + above, y + length[0] - x, y + length[1] - x


def _overlaps(one: tuple[float, float], two: tuple[float, float]) -> bool:
    """Whether two closed intervals share any point."""
    return one[0] <= two[1] and two[0] <= one[1]


def audit_geometry(path: Path, quiet: bool = False) -> list[str]:
    """Rules through words, and words off the canvas, in one committed figure."""
    import xml.etree.ElementTree as ET

    source = path.read_text(encoding="utf-8")
    root = ET.fromstring(source)
    style = "".join("".join(n.itertext()) for n in root.iter(f"{SVG_NS}style"))
    labels = _labels(root, _type_rules(style))

    # Each rule carries its own half-thickness. A `<path>` at y with
    # `stroke-width: 2` covers y-1 to y+1, and the geometry half used to treat
    # every rule as a line of no width and pad the text band by a flat two
    # pixels instead -- one chosen number doing the job of a measurement and a
    # judgement at once.
    across: list[tuple[float, float, float, float]] = []
    down: list[tuple[float, float, float, float]] = []
    for node in root.iter(f"{SVG_NS}path"):
        half = _stroke_of(node.get("class", ""), style) / 2
        horizontal, vertical = _rules(node.get("d", ""))
        across += [(*segment, half) for segment in horizontal]
        down += [(*segment, half) for segment in vertical]

    _, _, view_w, view_h = (float(v) for v in root.get("viewBox", "0 0 0 0").split())

    findings = []
    measurable = []
    for label in labels:
        content, _, _, _, weight, _, _, rotation = label
        if rotation is None:
            findings.append(
                f"{path.name}: {content[:30]!r} carries a transform this cannot read; "
                f"only quarter turns are handled"
            )
            continue
        missing = _unmeasured(content, weight)
        if missing:
            shown = " ".join(sorted(repr(c) for c in missing))
            findings.append(
                f"{path.name}: {content[:30]!r} contains {shown}, which "
                f"assets/font-metrics.json has no measurement for at weight {weight} — "
                f"run scripts/measure_type.py"
            )
            continue
        measurable.append(label)

    for label in measurable:
        content, y, size = label[0], label[2], label[3]
        wx0, wx1, wy0, wy1 = _box(label, widest=True)
        nx0, nx1, _, _ = _box(label, widest=False)

        # Both orientations against the wide box. A rule through a word is a
        # defect, so the failure to avoid is missing one -- and the vertical
        # case used the *narrow* box for three rounds, inherited from the
        # label-against-label test below where the argument is the opposite.
        for rule_y, rule_from, rule_to, half in across:
            body = (rule_y - half - PROXIMITY, rule_y + half + PROXIMITY)
            if _overlaps(body, (wy0, wy1)) and _overlaps((rule_from, rule_to), (wx0, wx1)):
                findings.append(
                    f"{path.name}: a rule at y={rule_y:.1f} crosses "
                    f"{content[:44]!r} (baseline y={y:.1f}, {size:g}px)"
                )
                break

        for rule_x, rule_from, rule_to, half in down:
            body = (rule_x - half - PROXIMITY, rule_x + half + PROXIMITY)
            if _overlaps(body, (wx0, wx1)) and _overlaps((rule_from, rule_to), (wy0, wy1)):
                findings.append(
                    f"{path.name}: a rule at x={rule_x:.1f} crosses "
                    f"{content[:44]!r} (x {wx0:.0f}..{wx1:.0f})"
                )
                break

        # The canvas, on the *wide* box, and the reason is the same one round
        # 33 used to move the rule check here: one side of this comparison is
        # exact. A canvas edge is a number, not a bound, so "the widest this
        # label can be runs past it" is a sound statement about some reader's
        # machine, and a figure broken only for other people is still broken.
        #
        # This used the narrow box, on the argument that a reported overflow
        # has to be one that is certainly there. That argument is the right
        # one for a check whose failure is inventing a finding, and the wrong
        # one here: round 36 found `figure-path.svg` with 1,019 pixels of
        # caption on a 900-pixel canvas at the wide bound and 877 at the
        # narrow one, so the audit had been green over a caption that ran off
        # the edge for anybody whose browser chose a wide face. Exactly the
        # defect class round 33 named, surviving in the one check it had not
        # been applied to.
        #
        # The label-against-label check below deliberately keeps the narrow
        # box, and that is not inconsistency: there, *both* sides are bounds.
        # Two upper bounds overlapping does not mean any single face puts the
        # two strings on top of each other, so the inference is weaker than
        # this one. Measured rather than assumed: switching that check to wide
        # boxes would report four pairs in the committed figures today, and
        # deciding whether any of them is real needs a rendering, not an
        # assertion. Written down here so the next round starts from the
        # number.
        if wx0 < 0 or wx1 > view_w or wy1 > view_h or wy0 < 0:
            findings.append(
                f"{path.name}: {content[:44]!r} can leave the "
                f"{view_w:g}x{view_h:g} canvas (widest x {wx0:.0f}..{wx1:.0f}, "
                f"y {wy0:.0f}..{wy1:.0f}); narrowest x {nx0:.0f}..{nx1:.0f}"
            )

    # Labels against each other. Two strings whose boxes overlap are one
    # unreadable string, and this is the failure that arrives when a figure is
    # edited rather than when it is drawn: a word grows by four characters and
    # lands on its neighbour. The narrow box here, as for the canvas -- a
    # reported overlap has to be one that is certainly there, not one an
    # estimate could have invented.
    boxes = [(label[0], _box(label, widest=False)) for label in measurable]
    for index, (one, (ax0, ax1, ay0, ay1)) in enumerate(boxes):
        for two, (bx0, bx1, by0, by1) in boxes[index + 1 :]:
            if _overlaps((ax0, ax1), (bx0, bx1)) and _overlaps((ay0, ay1), (by0, by1)):
                findings.append(f"{path.name}: {one[:30]!r} overlaps {two[:30]!r}")

    if not quiet:
        verdict = f"{len(findings)} finding(s)" if findings else "clean"
        count = len(across) + len(down)
        print(f"  {verdict:16} {len(labels):3d} labels, {count:2d} rules   {path.name}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="only report failures")
    parser.add_argument(
        "--slack",
        action="store_true",
        help="what the one-band-per-label approximation costs, in pixels",
    )
    args = parser.parse_args()

    if args.slack:
        pairs = band_slack()
        if not pairs:
            print("no horizontal rule in any committed figure shares an x-range with a label")
            return 0
        band = min(pair[2] for pair in pairs)
        exact = min(pair[3] for pair in pairs)
        away = max(pair[3] - pair[2] for pair in pairs)
        disagree = sum(1 for pair in pairs if (pair[2] < 0) != (pair[3] < 0))
        print(f"{len(pairs)} (horizontal rule, label) pairs share an x-range")
        print(f"  band comes within        {band:6.2f}px of reporting a crossing")
        print(f"  an exact silhouette      {exact:6.2f}px")
        print(f"  widest margin given away {away:6.2f}px")
        print(f"  pairs the two models judge differently: {disagree}")

        # And the other room a figure can run out of, for the same reason the
        # first half is printed: round 35 left itself the rule that a number
        # in committed prose comes with the command that reproduces it, and
        # the canvas margins quoted in `make_figures.py` had no such command
        # until this line existed.
        print()
        margins = canvas_margins()
        tightest = min(margins, key=lambda row: row[2])
        print(f"{len(margins)} label(s) measured against their canvas, widest bound")
        print(f"  tightest margin          {tightest[2]:6.2f}px")
        print(f"  on                       {tightest[0]} {tightest[1]!r}")
        return 0

    failures, checked = [], 0
    for scheme in ("light", "dark"):
        if not args.quiet:
            print(f"{scheme} — assets/figure-*.svg:")
        failures += audit_assets(scheme, quiet=args.quiet)
        checked += len(ASSET_PAIRS)

    # The list of pairs has to describe the figures, or the ratios above are
    # a true answer to a question nobody asked. Round 37 found `muted` type
    # inside the gateway band rendering in every shipped figure and declared
    # nowhere.
    missing = undeclared_pairs()
    failures += missing
    if not args.quiet and not missing:
        print("  ok           every ink-on-surface the figures render is declared")

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
