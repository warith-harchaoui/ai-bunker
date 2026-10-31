#!/usr/bin/env python3
"""The README's figures, drawn rather than described.

Why this exists
---------------
Three things in this project are a picture and were several hundred words: the
four stages a turn crosses, the order the four model slots are settled in, and
what the text-to-image slot costs on each machine. `README.md` is 1,100 lines
and carried no diagram at all; `assets/` held a logo and a price chart.

Why a generator rather than three files
---------------------------------------
Two reasons, and neither is the drawing.

**The numbers.** Figures 2 and 3 quote figures that come out of
`ai-bunker sizing`. A hand-drawn chart is a quotation nobody can re-run, and
this repository already refuses that for prose -- `scripts/sync_counts.py`
rewrites every quoted count and `tests/test_site.py` fails when one drifts.
The numbers live in :data:`PLAN` and :data:`TRADE` with the command that
produces them written beside them, and `tests/test_figures.py` checks the
committed files are exactly what this script renders.

**The second language.** The site draws each figure once and feeds it a
dictionary of strings, so French and English share one geometry. The same
applies here: `README.md` and `LISEZMOI.md` are twins, and a figure that
existed only in English would be the first place they stopped being.

What it does NOT do
-------------------
No charting library, and no layout engine. These are hand-authored SVG, like
the site's: they stay sharp at any zoom, they carry a `<title>` and a `<desc>`
rather than an alt string repeating the caption, and they answer
`prefers-color-scheme` with two weights of the same palette -- the saturated
originals read beautifully on dark and fail the 4.5:1 floor on white, which is
the mistake a review done in dark mode cannot see.

    python scripts/make_figures.py            # write assets/figure-*.svg
    python scripts/make_figures.py --check    # fail if any is out of date

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"

# ---------------------------------------------------------------------------
# Palette and type, in two weights of one scheme
# ---------------------------------------------------------------------------

#: Light-scheme ink, copied from the site's `tailwind-input.css` so the two
#: surfaces agree. Every one of these clears 4.5:1 against white, which the
#: palette's saturated originals do not -- `#007AFF` scores 4.02:1 there.
LIGHT = {
    "ink": "#1B1B1F",
    "muted": "#656569",
    "blue": "#0062CC",
    "orange": "#995600",
    "red": "#C12F26",
    "green": "#158126",
    "page": "#FFFFFF",
}

#: Dark-scheme ink: the palette originals, which score 8:1 or better against a
#: near-black page. `page` is GitHub's dark canvas rather than the site's
#: `#0B0B0C`, because that is where these files are read.
#:
#: `muted` is the one value that is not the site's. The site uses `#8A8A92`,
#: which clears 4.5:1 on `#0B0B0C` and scores **4.41:1** on the orange stage
#: card over this lighter page -- a failure the audit found and no amount of
#: looking at the figure would have. Lightened until the worst surface in
#: either scheme clears the floor with room to spare.
DARK = {
    "ink": "#E8E8EA",
    "muted": "#92929A",
    "blue": "#3C9BFF",
    "orange": "#FFA52B",
    "red": "#FF5349",
    "green": "#35D94E",
    "page": "#0D1117",
}

#: Opacity of a tinted card over the page. The card is the only surface any
#: label lands on other than the page itself, so these two numbers and the two
#: palettes above are the whole input to the contrast audit.
CARD_ALPHA = 0.10
BAND_ALPHA = 0.05

FONT = "Roboto, 'Helvetica Neue', Helvetica, Arial, sans-serif"


def _style() -> str:
    """The stylesheet every figure carries, in both weights of the palette.

    Literal colours in class rules, and deliberately **no CSS custom
    properties**. A `var(--blue)` is the tidier spelling and it is the wrong
    one here: a figure in a README is read through whatever renders it, and
    the first renderer this was tried in understood class selectors, applied
    every weight and size, and dropped each `var()` to a default -- boxes
    with no outline, arrows with no heads, a chart in black and grey. Two
    literal blocks cost thirty lines and work wherever a stylesheet works.

    The dark block overrides the same class names, so a colour has exactly
    two definitions and `scripts/audit_figures.py` has one place to read both.
    """
    statics = """    text { font-size: 12px; }
    .t { font-size: 13px; font-weight: 600; }
    .s { font-size: 11.5px; }
    .n { font-size: 11px; font-weight: 700; letter-spacing: .1em; }
    .h { font-size: 13px; font-weight: 600; letter-spacing: .08em; }
    .band { fill-opacity: BAND; stroke-opacity: .30; }
    .card-blue, .card-orange { fill-opacity: CARD; }
    .card-blue { stroke-opacity: .45; }
    .card-orange { stroke-opacity: .50; }
    .outline { fill: none; stroke-width: 1.5; }
    .wire, .wire-back { fill: none; stroke-width: 2; }
    .axis { fill: none; stroke-width: 1; }
    .dash { fill: none; stroke-width: 1; stroke-dasharray: 4 4; }"""
    statics = statics.replace("BAND", f"{BAND_ALPHA:.2f}").replace("CARD", f"{CARD_ALPHA:.2f}")
    return (
        "  <style>\n"
        f"    svg {{ font-family: {FONT}; }}\n"
        f"{statics}\n"
        f"{_palette_rules(LIGHT, indent='    ')}\n"
        "    @media (prefers-color-scheme: dark) {\n"
        f"{_palette_rules(DARK, indent='      ')}\n"
        "    }\n"
        "  </style>"
    )


def _palette_rules(p: dict[str, str], indent: str) -> str:
    """One palette, as class rules.

    Every rule that names a colour is here and nowhere else, which is what
    makes the contrast audit a parse rather than a search: not one figure
    carries a colour in an attribute.
    """
    rules = [
        ("text", f"fill: {p['ink']};"),
        (".muted", f"fill: {p['muted']};"),
        (".blue", f"fill: {p['blue']};"),
        (".orange", f"fill: {p['orange']};"),
        (".red", f"fill: {p['red']};"),
        (".green", f"fill: {p['green']};"),
        (".band, .card-blue", f"fill: {p['blue']}; stroke: {p['blue']};"),
        (".card-orange", f"fill: {p['orange']}; stroke: {p['orange']};"),
        (".outline, .wire-back, .axis, .dash", f"stroke: {p['muted']};"),
        (".wire", f"stroke: {p['blue']};"),
        (".seg-muted", f"fill: {p['muted']}; stroke: {p['muted']};"),
        (".seg-blue", f"fill: {p['blue']}; stroke: {p['blue']};"),
        (".seg-orange", f"fill: {p['orange']}; stroke: {p['orange']};"),
        (".seg-red", f"fill: {p['red']}; stroke: {p['red']};"),
        (".seg-green", f"fill: {p['green']}; stroke: {p['green']};"),
        (".dot-blue", f"fill: {p['blue']};"),
        (".dot-red", f"fill: {p['red']};"),
        (".head-fwd", f"fill: {p['blue']};"),
        (".head-back", f"fill: {p['muted']};"),
    ]
    return "\n".join(f"{indent}{sel} {{ {body} }}" for sel, body in rules)


def _svg(view: str, title: str, desc: str, body: str, slug: str) -> str:
    """One finished file: viewBox, stylesheet, accessible name, drawing.

    No width or height attribute on purpose -- the figure is sized by the
    column it lands in, and a fixed width is how a diagram ends up either
    pixellated or clipped on a phone.
    """
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" role="img"\n'
        f'     aria-labelledby="{slug}-t {slug}-d">\n'
        f'  <title id="{slug}-t">{title}</title>\n'
        f'  <desc id="{slug}-d">{desc}</desc>\n'
        f"{_style()}\n{body}\n</svg>\n"
    )


def _arrowheads() -> str:
    """Two markers, because an arrow that carries the request and an arrow
    that carries the answer back are not the same arrow."""
    return """  <defs>
    <marker id="fwd" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7"
            markerHeight="7" orient="auto">
      <path class="head-fwd" d="M0 0 L10 5 L0 10 z"/>
    </marker>
    <marker id="back" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7"
            markerHeight="7" orient="auto">
      <path class="head-back" d="M0 0 L10 5 L0 10 z"/>
    </marker>
  </defs>"""


# ---------------------------------------------------------------------------
# Figure 1 -- a turn across the gateway
# ---------------------------------------------------------------------------


def pipeline(t: dict[str, str]) -> str:
    """The four stages, drawn as the shape they actually are.

    This was four cards in one column with a forward arrow entering at the
    second and a return arrow leaving at the third -- heights chosen for
    symmetry. The caption, the heading above it and the `<desc>` all insisted
    the **order is load-bearing**, and nothing in the geometry said so. A
    reader who learned the mechanism from the picture learned it wrong, which
    is worse than learning nothing.

    So: three stages on the way in, one on the way back, and the round trip
    through the engine drawn as the gap between them. The thing prose keeps
    failing to land -- that 01 and 04 are **the same rule engine**, and that a
    gateway is the only position from which both ends of a turn are visible --
    is now carried by them sharing a colour, with the sentence underneath to
    name it rather than to do the work alone.
    """
    cards = [
        ("01", "orange", 86, "s1", "s1a"),
        ("02", "blue", 172, "s2", "s2a"),
        ("03", "blue", 258, "s3", "s3a"),
        ("04", "orange", 372, "s4", "s4a"),
    ]
    drawn = "\n".join(
        f'  <rect class="card-{tone}" x="226" y="{y}" width="448" height="76" rx="12"/>\n'
        f'  <text class="n {tone}" x="242" y="{y + 22}">{mark}</text>\n'
        f'  <text class="t" x="242" y="{y + 44}">{t[title]}</text>\n'
        f'  <text class="s muted" x="242" y="{y + 64}">{t[sub]}</text>'
        for mark, tone, y, title, sub in cards
    )

    body = f"""{_arrowheads()}
  <rect class="band" x="206" y="24" width="488" height="452" rx="16"/>
  <text class="h blue" x="450" y="50" text-anchor="middle">{t["gateway"]}</text>
  <text class="n muted" x="226" y="76">{t["inbound"]}</text>
  <text class="n muted" x="226" y="362">{t["outbound"]}</text>

  <rect class="outline" x="16" y="100" width="170" height="320" rx="14"/>
  <text class="t" x="101" y="252" text-anchor="middle">{t["client"]}</text>
  <text class="s muted" x="101" y="274" text-anchor="middle">{t["client_sub"]}</text>

  <rect class="outline" x="714" y="100" width="170" height="320" rx="14"/>
  <text class="t" x="799" y="252" text-anchor="middle">{t["engine"]}</text>
  <text class="s muted" x="799" y="274" text-anchor="middle">{t["engine_sub"]}</text>

{drawn}

  <path class="wire" d="M186 124 H226" marker-end="url(#fwd)"/>
  <path class="wire" d="M450 162 V172" marker-end="url(#fwd)"/>
  <path class="wire" d="M450 248 V258" marker-end="url(#fwd)"/>
  <path class="wire" d="M674 296 H714" marker-end="url(#fwd)"/>
  <path class="wire-back" d="M714 410 H674" marker-end="url(#back)"/>
  <path class="wire-back" d="M226 410 H186" marker-end="url(#back)"/>

  <text class="s muted" x="60" y="502">{t["bracket"]}</text>"""
    return _svg("0 0 900 524", t["title"], t["desc"], body, "pipe")


# ---------------------------------------------------------------------------
# Figure 2 -- one card, settled in order
# ---------------------------------------------------------------------------

#: An 80 GiB accelerator with every slot filled, in gibibytes. Reproduce with
#:
#:     ai-bunker sizing --accelerator h100-80 --image auto
#:
#: The six numbers sum to the card, which is the figure's whole point: nothing
#: here is planned as though it were free.
PLAN = [
    ("overhead", 4.0, "muted"),
    ("embed", 1.2, "blue"),
    ("vision", 9.0, "blue"),
    ("image", 26.4, "orange"),
    ("code", 25.0, "green"),
    ("kv", 14.4, "muted"),
]

#: Which slots are settled in which order, and which one is the remainder.
#: `resolve_plan` settles cheapest first and gives the coder what is left.
ORDER = ("embed", "vision", "image", "code")


def plan(t: dict[str, str]) -> str:
    """Where an 80 GiB card goes, and in what order it is decided.

    The bar is the memory; the table is the order. Two rows rather than labels
    on the segments, because the embedder is 1.2 of 80 gibibytes -- eleven
    pixels wide at this scale -- and a label leadered out of an eleven-pixel
    box is a collision waiting for a longer word.

    What ties the two together is the **ordinal**, not the colour. It was the
    colour, and the colour cannot carry it: six segments resolve to four hues
    because the embedder and the vision model are both language models and
    both blue, and the overhead and the cache pool are both grey. So the rank
    each slot is settled at is printed over its segment and again beside its
    row, and an eleven-pixel segment can hold a numeral above it where it
    could never have held a word inside it.

    The scale underneath is the other half of that. A bar whose numbers can
    only be read from the table beside it is a table with a decoration on top.
    """
    total = sum(gib for _, gib, _ in PLAN)
    x0, width = 60, 780
    bar_top, bar_bottom = 100, 154
    parts, x = [], float(x0)
    for key, gib, tone in PLAN:
        w = width * gib / total
        parts.append((key, gib, tone, x, w))
        x += w

    bars = "\n".join(
        f'  <rect class="seg-{tone}" x="{px:.1f}" y="{bar_top}" width="{pw:.1f}" '
        f'height="{bar_bottom - bar_top}" rx="4" '
        f'fill-opacity="{0.55 if key in ORDER else 0.18}" stroke-opacity=".55"/>'
        for key, _gib, tone, px, pw in parts
    )

    # Above the bar rather than inside it. Inside would be the tidier drawing
    # and it fails the contrast floor in one scheme: dark-mode ink over the
    # orange segment at 55% scores 4.1:1, which is the sort of thing a figure
    # reviewed on a dark screen ships with. The page is a surface both
    # schemes are already audited against.
    ranks = "\n".join(
        f'  <text class="n {tone}" x="{px + pw / 2:.1f}" y="88" text-anchor="middle">'
        f"{ORDER.index(key) + 1}</text>\n"
        f'  <path class="axis" d="M{px + pw / 2:.1f} 92 V{bar_top}"/>'
        for key, _gib, tone, px, pw in parts
        if key in ORDER
    )

    scale = "\n".join(
        f'  <path class="axis" d="M{x0 + width * v / total:.1f} {bar_bottom} '
        f'V{bar_bottom + 6}"/>\n'
        f'  <text class="s muted" x="{x0 + width * v / total:.1f}" y="{bar_bottom + 20}" '
        f'text-anchor="{"end" if v == total else "middle"}">'
        f"{v:g}{' ' + t['unit'] if v == total else ''}</text>"
        for v in (0, 20, 40, 60, 80)
    )

    # No leader lines from a segment down to its row. There were, and they
    # crossed two columns of other rows' text on the way -- noise that read as
    # a mistake. The rows are in the bar's own left-to-right order, carry its
    # colours, and now carry its ordinals, which is the same tie three times
    # over without a line crossing anything.
    rows = []
    for i, (key, gib, tone, _px, _pw) in enumerate(parts):
        y = 228 + i * 30
        rank = ORDER.index(key) + 1 if key in ORDER else None
        mark = f"{rank}" if rank else "·"
        rows.append(
            f'  <text class="n {tone}" x="60" y="{y}">{mark}</text>\n'
            f'  <rect class="seg-{tone}" x="84" y="{y - 11}" width="13" '
            f'height="13" rx="3" fill-opacity="{0.55 if rank else 0.18}" '
            f'stroke-opacity=".55"/>\n'
            f'  <text class="t" x="110" y="{y}">{t[key]}</text>\n'
            f'  <text class="s muted" x="330" y="{y}">{t[key + "_sub"]}</text>\n'
            f'  <text class="s" x="840" y="{y}" text-anchor="end">'
            f"{gib:g} {t['unit']}</text>"
        )

    body = f"""  <text class="h blue" x="60" y="40">{t["card"]}</text>
  <text class="s muted" x="60" y="62">{t["card_sub"]}</text>
{ranks}
{bars}
{scale}
  <text class="s muted" x="60" y="198">{t["legend"]}</text>
{chr(10).join(rows)}
  <text class="s muted" x="60" y="{228 + len(parts) * 30 + 24}">{t["note"]}</text>"""
    return _svg("0 0 900 452", t["title"], t["desc"], body, "plan")


# ---------------------------------------------------------------------------
# Figure 3 -- what a picture costs
# ---------------------------------------------------------------------------

#: (label, bandwidth GB/s, seconds per image, does the 80B coder still fit).
#: Reproduce each row with
#:
#:     ai-bunker sizing --accelerator <id> --image auto
#:
#: Every machine chooses the same picture model -- Stable Diffusion 3.5
#: Medium, 26.4 GiB, 28 steps at 1024x1024 -- so the seconds column is one
#: model timed on five memory systems and nothing else.
TRADE = [
    ("macbook", 400, 24.8, True),
    ("studio", 819, 12.1, True),
    ("pro5000", 1344, 7.4, False),
    ("pro6000", 1792, 5.5, True),
    ("h100", 3350, 3.0, False),
]

#: Where each label sits relative to its point. Five points on a hyperbola
#: crowd at the right, so these are placed by eye -- and then checked, which
#: is the part that was missing: `scripts/audit_figures.py` fails the build if
#: any of them lands on a gridline or on a neighbour. The first version of
#: this table put two labels on rules and nothing noticed for a round.
PLACEMENT = {
    "macbook": ("start", 14, 20),
    "studio": ("start", 14, 5),
    "pro5000": ("start", 14, -10),
    "pro6000": ("start", 14, 24),
    "h100": ("end", -14, 5),
}


def trade(t: dict[str, str]) -> str:
    """One picture model, five memory systems, five different waits.

    The argument the chart makes that the table in `docs/SIZING.md` does not:
    the seconds are a bandwidth curve. A denoising loop reads its weights
    twenty-eight times a picture, so the slot obeys the same roofline the
    coder does, and the machine this project recommends buying lands at twelve
    seconds -- which is batch work, said in a shape nobody can skim past.

    One line per point rather than a name over a value. The stacked pair was
    two chances to land on a gridline instead of one, and it took both: the
    rule at ten seconds ran through `12.1 s` and the rule at twenty-five ran
    through `MacBook Pro M2 Max`. The machines that lose the coder are now
    said in red type rather than in a grey suffix repeating the footnote, so
    the colour carries the fact and the label stays short enough to place.
    """
    left, right, top, bottom = 92, 844, 76, 356
    bw_max, s_max = 3500.0, 26.0

    def px(bw: float) -> float:
        return left + (right - left) * bw / bw_max

    def py(sec: float) -> float:
        return bottom - (bottom - top) * sec / s_max

    curve = " ".join(
        f"{'M' if i == 0 else 'L'}{px(bw):.1f} {py(sec):.1f}"
        for i, (_k, bw, sec, _fit) in enumerate(TRADE)
    )

    marks = []
    for key, bw, sec, fits in TRADE:
        anchor, dx, dy = PLACEMENT[key]
        tone = "blue" if fits else "red"
        seconds = f"{sec:g}".replace(".", t["decimal"])
        marks.append(
            f'  <circle class="dot-{tone}" cx="{px(bw):.1f}" '
            f'cy="{py(sec):.1f}" r="5"/>\n'
            f'  <text class="t{"" if fits else " red"}" x="{px(bw) + dx:.1f}" '
            f'y="{py(sec) + dy:.1f}" text-anchor="{anchor}">'
            f"{t[key]} · {seconds}\u202f{t['unit']}</text>"
        )

    ticks = "\n".join(
        f'  <text class="s muted" x="{px(v):.1f}" y="{bottom + 22:.1f}" '
        f'text-anchor="middle">{v:,}</text>'
        for v in (0, 1000, 2000, 3000)
    )
    gridlines = "\n".join(
        f'  <path class="dash" d="M{left} {py(v):.1f} H{right}"/>\n'
        f'  <text class="s muted" x="{left - 12}" y="{py(v) + 4:.1f}" '
        f'text-anchor="end">{v:g}</text>'
        for v in (5, 10, 15, 20, 25)
    )

    body = f"""  <text class="h blue" x="60" y="38">{t["head"]}</text>
  <text class="s muted" x="60" y="58">{t["sub"]}</text>
{gridlines}
  <path class="axis" d="M{left} {top} V{bottom} H{right}"/>
  <path class="wire" d="{curve}" stroke-opacity=".55"/>
{chr(10).join(marks)}
{ticks}
  <text class="s muted" x="{(left + right) / 2:.0f}" y="{bottom + 46}"
        text-anchor="middle">{t["x"]}</text>
  <text class="s muted" x="24" y="{(top + bottom) / 2:.0f}" text-anchor="middle"
        transform="rotate(-90 24 {(top + bottom) / 2:.0f})">{t["y"]}</text>
  <text class="s red" x="60" y="444">{t["foot"]}</text>"""
    return _svg("0 0 900 470", t["title"], t["desc"], body, "trade")


# ---------------------------------------------------------------------------
# Figure 4 -- the window, and what is left of it
# ---------------------------------------------------------------------------

#: The two sessions in README's *Why the server has to count*, in tokens.
#: Both were measured at the relay rather than modelled; `ai-bunker budget`
#: prints each of them today. Reproduce with
#:
#:     ai-bunker budget --capture <session>.json --gate
#:
#: The columns are **owners**, not components, because attribution is the
#: argument: a floor nobody can decompose is a floor nobody can reduce, and
#: the only number here this project is responsible for is the third one.
WINDOW = 26_000
TRIGGER = 20_000
BUDGETS = {
    #            client-owned, ai-bunker-owned
    "works": (5_509, 1_258),
    "loops": (23_263, 1_258),
}


def budget(t: dict[str, str]) -> str:
    """One context window, twice: the session that works and the one that loops.

    This is the project's founding story and it was the only part of the
    document with no picture -- while containing a bar chart typed in
    characters, which is the shape of the thing asking to be drawn.

    The whole argument is one vertical line. Compaction fires at 20,000 of a
    declared 26,000; a floor that ends left of that line leaves room to work,
    and a floor that crosses it is a session that compacts on turn one with
    nothing to compact. The second bar crosses it. Nothing else in the figure
    has to be read for that to land.
    """
    x0, width = 60.0, 780.0
    per = width / WINDOW
    trigger = x0 + TRIGGER * per

    def bar(y: float, key: str) -> str:
        client, ours = BUDGETS[key]
        floor = client + ours
        rest = WINDOW - floor
        # What the remainder *is* differs between the two, and the colour is
        # the only place that difference is stated without a sentence: below
        # the trigger it is conversation and then margin; above it there is no
        # conversation at all, and the leftover is the thing that loops.
        if floor < TRIGGER:
            spans = [
                ("orange", client),
                ("blue", ours),
                ("green", TRIGGER - floor),
                ("muted", WINDOW - TRIGGER),
            ]
        else:
            spans = [("orange", client), ("blue", ours), ("red", rest)]
        out, x = [], x0
        for tone, tokens in spans:
            w = tokens * per
            out.append(
                f'  <rect class="seg-{tone}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
                f'height="40" rx="4" fill-opacity="0.55" stroke-opacity=".55"/>'
            )
            x += w
        return "\n".join(out)

    def number(value: int) -> str:
        return f"{value:,}".replace(",", t["group"])

    # One row per colour, and an em dash where a case does not have that
    # segment at all. The dashes are not a gap in the table -- they are the
    # finding: the looping session has no green and no grey, which is another
    # way of writing the sentence underneath. Both columns sum to the window,
    # and the total row is there so a reader can check that rather than
    # trust it.
    spent = sum(BUDGETS["works"]), sum(BUDGETS["loops"])

    def cell(value: int | None) -> str:
        """A number, or the em dash that means this case has no such segment."""
        return t["none"] if value is None else number(value)

    rows = []
    for i, (key, tone) in enumerate(
        (
            ("client", "orange"),
            ("ours", "blue"),
            ("room", "green"),
            ("margin", "muted"),
            ("over", "red"),
        )
    ):
        y = 310 + i * 25
        works, loops = (
            (BUDGETS["works"][0], BUDGETS["loops"][0]),
            (BUDGETS["works"][1], BUDGETS["loops"][1]),
            (TRIGGER - spent[0], None),
            (WINDOW - TRIGGER, None),
            (None, WINDOW - spent[1]),
        )[i]
        rows.append(
            f'  <rect class="seg-{tone}" x="60" y="{y - 11}" width="13" height="13" '
            f'rx="3" fill-opacity="0.55" stroke-opacity=".55"/>\n'
            f'  <text class="t" x="86" y="{y}">{t[key]}</text>\n'
            f'  <text class="s muted" x="310" y="{y}">{t[key + "_sub"]}</text>\n'
            f'  <text class="s" x="700" y="{y}" text-anchor="end">{cell(works)}</text>\n'
            f'  <text class="s" x="840" y="{y}" text-anchor="end">{cell(loops)}</text>'
        )
    # The rule and the total sit twelve and thirty-two pixels below the last
    # row rather than tight under it: the audit's clearance is two pixels and
    # a line that clears by two still reads as an underline on the number
    # above it.
    rule_y, total_y = 310 + 4 * 25 + 12, 310 + 4 * 25 + 32
    rows.append(
        f'  <path class="axis" d="M600 {rule_y} H840"/>\n'
        f'  <text class="s muted" x="86" y="{total_y}">{t["total"]}</text>\n'
        f'  <text class="s" x="700" y="{total_y}" text-anchor="end">{number(WINDOW)}</text>\n'
        f'  <text class="s" x="840" y="{total_y}" text-anchor="end">{number(WINDOW)}</text>'
    )

    # The trigger line is drawn in two segments rather than one -- `98 V178`
    # and `218 V266` -- and the gap is where the two right-aligned notes live.
    # A single `V266` ran through the band of `loops_note` for any reader
    # whose browser picked a wide face: the note is anchored at x=840 and
    # ends, on the widest measured face, at x=647 -- while the trigger sits at
    # 660. The narrowest face puts it at 675 and clears. So the figure was
    # broken on some machines and fine on others, which is precisely the
    # defect a one-font width model could not see, and `audit_figures.py`
    # reported it the hour the vertical check started using the wide bound.
    #
    # This paragraph spent two rounds inside `trade()`, a hundred and fifty
    # lines above the path it explains, naming a variable that function does
    # not have. `trade` draws horizontal gridlines with the same `.dash` class
    # and no trigger at all, so a reader there was being told about something
    # that was not happening and a reader here was given two segments with no
    # reason. A misfiled explanation is a missing one.
    #
    # The line loses nothing: a threshold means something where it crosses a
    # bar, and the two segments still cover both bars and the connector up to
    # the label. Looked at, by a second pair of eyes and a round later, which
    # was the open question: it holds, and for a reason the first pass did not
    # give. In the upper bar the trigger falls exactly on the boundary between
    # `room` and `margin` -- the compaction margin begins at the trigger by
    # definition -- so the dash there is redundant with the fill it sits on.
    # In the lower bar it falls in the middle of one unbroken client run and
    # is the only thing saying where 20,000 lands. The segment that earns its
    # keep is the second one, and a single rule would have added a third
    # crossing that says nothing while running through the note.
    body = f"""  <text class="h blue" x="60" y="38">{t["head"]}</text>
  <text class="s muted" x="60" y="58">{t["sub"]}</text>

  <text class="s muted" x="{trigger:.0f}" y="90" text-anchor="middle">{t["trigger"]}</text>
  <path class="dash" d="M{trigger:.0f} 98 V178 M{trigger:.0f} 218 V266"/>

  <text class="t" x="60" y="124">{t["works"]}</text>
  <text class="s muted" x="840" y="124" text-anchor="end">{t["works_note"]}</text>
{bar(134, "works")}

  <text class="t" x="60" y="212">{t["loops"]}</text>
  <text class="s red" x="840" y="212" text-anchor="end">{t["loops_note"]}</text>
{bar(222, "loops")}

  <text class="n muted" x="700" y="288" text-anchor="end">{t["col_works"]}</text>
  <text class="n muted" x="840" y="288" text-anchor="end">{t["col_loops"]}</text>
{chr(10).join(rows)}

  <text class="s muted" x="60" y="486">{t["foot1"]}</text>
  <text class="s muted" x="60" y="504">{t["foot2"]}</text>"""
    return _svg("0 0 900 526", t["title"], t["desc"], body, "budget")


# ---------------------------------------------------------------------------
# Figure 5 -- four positions on one path
# ---------------------------------------------------------------------------

#: Who stands where, left to right along a turn. Each entry is
#: `(x, [occupants])`, and the occupant marked `True` is this project -- drawn
#: in the accent so a reader can find the subject of the comparison without
#: reading four columns first.
#:
#: Scored in `assets/landscape.csv`; `tests/test_landscape.py` keeps the star
#: table in `LANDSCAPE.md` and that file from disagreeing. This figure is the
#: half neither of them can draw: a scatter plot says where a tool sits in a
#: space of criteria, and a table says how well it does each one. Neither says
#: **where on the path it stands**, which is the whole argument.
STANDS = (
    (28.0, (("@config", False), ("@guardrails", False))),
    (
        245.0,
        (
            ("LiteLLM · Kong · Portkey", False),
            ("Bifrost · agentgateway", False),
            ("Envoy AI Gateway", False),
            ("ai-bunker", True),
        ),
    ),
    (465.0, ()),
    (670.0, (("ToolHive", False), ("Docker MCP Gateway", False), ("agent-scan", False))),
)


def path(t: dict[str, str]) -> str:
    """Four positions on one path, and why they are not interchangeable.

    `LANDSCAPE.md` argues that the gateway position is the thing, not the
    feature list -- that a file on a laptop drifts, a library only runs when
    the application calls it, and a tool-server gateway sees a call the model
    has already decided to make. That argument is geometric and it was five
    hundred words of prose.

    The positioning map beside it is a principal-component scatter and cannot
    say this: it places tools by how they score, not by where they stand. Two
    tools can sit a centimetre apart there and be on opposite sides of the
    serving engine.
    """
    boxes = (
        (28.0, 197.0, "agent", "agent_sub", False),
        (245.0, 200.0, "gate", "gate_sub", True),
        (465.0, 185.0, "engine", "engine_sub", False),
        (670.0, 200.0, "tools", "tools_sub", False),
    )
    drawn = "\n".join(
        f'  <rect class="{"card-blue" if mine else "outline"}" x="{x}" y="92" '
        f'width="{w}" height="60" rx="12"/>\n'
        f'  <text class="t{" blue" if mine else ""}" x="{x + w / 2}" y="118" '
        f'text-anchor="middle">{t[name]}</text>\n'
        f'  <text class="s muted" x="{x + w / 2}" y="138" text-anchor="middle">'
        f"{t[sub]}</text>"
        for x, w, name, sub, mine in boxes
    )

    arrows = "\n".join(
        f'  <path class="wire" d="M{a} 122 H{b}" marker-end="url(#fwd)"/>'
        for a, b in ((225, 245), (445, 465), (650, 670))
    )

    # The occupant lists hang under the position they occupy rather than in a
    # column of their own, because the column would be a table and the table
    # already exists two screens up.
    columns = []
    for x, occupants in STANDS:
        for i, (name, mine) in enumerate(occupants):
            # A leading `@` means the label is a category rather than a
            # product, so it comes out of the string table and gets translated.
            label = t[name[1:]] if name.startswith("@") else name
            columns.append(
                f'  <text class="s{" blue" if mine else " muted"}" x="{x}" '
                f'y="{192 + i * 20}">{label}</text>'
            )

    body = f"""{_arrowheads()}
  <text class="h blue" x="60" y="38">{t["head"]}</text>
  <text class="s muted" x="60" y="58">{t["sub"]}</text>
{drawn}
{arrows}
  <text class="n muted" x="28" y="172">{t["also"]}</text>
{chr(10).join(columns)}
  <text class="s muted" x="60" y="298">{t["foot1"]}</text>
  <text class="s muted" x="60" y="316">{t["foot2"]}</text>
  <text class="s muted" x="60" y="334">{t["foot3"]}</text>"""
    return _svg("0 0 900 356", t["title"], t["desc"], body, "path")


# ---------------------------------------------------------------------------
# The words, per language
# ---------------------------------------------------------------------------

STRINGS: dict[str, dict[str, dict[str, str]]] = {
    "pipeline": {
        "en": {
            "title": "A turn crossing the gateway, in four stages",
            "desc": (
                "A client on the left and a serving engine on the right, with the gateway "
                "between them. Four stages are marked inside it: screen inbound tool "
                "results, inject the charter, measure and enforce the budget, screen "
                "outbound tool calls. A bracket joins the first and the last, which are "
                "the same rule engine at the two ends of one turn."
            ),
            "gateway": "AI-BUNKER",
            "client": "Coding agent",
            "client_sub": "any OpenAI-compatible client",
            "engine": "Serving engine",
            "engine_sub": "vLLM, Ollama, anything",
            "s1": "Screen inbound tool results",
            "s1a": "secrets out, injected instructions marked",
            "s2": "Inject the charter",
            "s2a": "first system block, byte-stable, idempotent",
            "s3": "Measure and enforce the budget",
            "s3a": "counted with the engine's own tokenizer; 413 names the culprit",
            "s4": "Screen outbound tool calls",
            "s4a": "the command has not run yet — refused as a tool result",
            "inbound": "ON THE WAY IN",
            "outbound": "ON THE WAY BACK",
            "bracket": (
                "01 and 04 are one rule engine, read twice — and a gateway is the only "
                "position from which both ends of a turn are visible."
            ),
        },
        "fr": {
            "title": "Un tour qui traverse la passerelle, en quatre étapes",
            "desc": (
                "Un client à gauche, un moteur d'inférence à droite, la passerelle entre "
                "les deux. Quatre étapes y sont marquées : filtrer les résultats d'outils "
                "entrants, injecter la charte, mesurer et appliquer le budget, filtrer les "
                "appels d'outils sortants. Une accolade relie la première et la dernière, "
                "qui sont le même moteur de règles aux deux bouts du même tour."
            ),
            "gateway": "AI-BUNKER",
            "client": "Agent de code",
            "client_sub": "tout client compatible OpenAI",
            "engine": "Moteur d'inférence",
            "engine_sub": "vLLM, Ollama, autre",
            "s1": "Filtrer les résultats d'outils entrants",
            "s1a": "secrets retirés, injections marquées",
            "s2": "Injecter la charte",
            "s2a": "premier bloc système, octets stables, idempotent",
            "s3": "Mesurer et appliquer le budget",
            "s3a": "compté par le tokeniseur du moteur ; le 413 nomme le coupable",
            "s4": "Filtrer les appels d'outils sortants",
            "s4a": "la commande n'a pas encore tourné — refus en résultat d'outil",
            "inbound": "À L'ALLER",
            "outbound": "AU RETOUR",
            "bracket": (
                "01 et 04 sont un seul moteur de règles, lu deux fois — et la passerelle "
                "est le seul endroit d'où les deux bouts d'un tour sont visibles."
            ),
        },
    },
    "plan": {
        "en": {
            "title": "Where an 80 GiB card goes, and in what order it is decided",
            "desc": (
                "A bar divided into six parts of an 80 gibibyte accelerator: overhead 4, "
                "embedder 1.2, vision 9, text-to-image 26.4, coder 25 and a key-value "
                "cache pool of 14.4 gibibytes. A table below numbers the four model slots "
                "in the order they are settled — embedder, vision, image, coder — and "
                "notes that the coder is settled last and takes the remainder."
            ),
            "unit": "GiB",
            "card": "ONE H100 80 GiB, EVERY SLOT FILLED",
            "card_sub": "ai-bunker sizing --accelerator h100-80 --image auto",
            "legend": "settled cheapest first; the coder takes what is left",
            "overhead": "Overhead",
            "overhead_sub": "context, activations, the room to be useful",
            "embed": "Embedder",
            "embed_sub": "bge-m3 — not ranked; the catalogue carries one",
            "vision": "Vision",
            "vision_sub": "qwen3-vl-8b — leanest within 10 points of the best",
            "image": "Text-to-image",
            "image_sub": "sd35-medium — off unless asked for",
            "code": "Coder",
            "code_sub": "devstral-small-2-24b — the remainder, so it was not the 80B",
            "kv": "Key-value cache pool",
            "kv_sub": "what is left over: concurrency, not weights",
            "note": (
                "Ask for pictures on this card and the coder drops from the 80B "
                "mixture-of-experts to the dense 24B. The report says so before you "
                "deploy it."
            ),
        },
        "fr": {
            "title": "Où passent 80 Gio de carte, et dans quel ordre cela se décide",
            "desc": (
                "Une barre divisée en six parts d'un accélérateur de 80 gibioctets : "
                "surcoût 4, embeddeur 1,2, vision 9, texte-vers-image 26,4, codeur 25 et "
                "une réserve de cache clé-valeur de 14,4 Gio. Un tableau en dessous "
                "numérote les quatre emplacements de modèles dans l'ordre où ils sont "
                "réglés — embeddeur, vision, image, codeur — et précise que le codeur est "
                "réglé en dernier et prend le reste."
            ),
            "unit": "Gio",
            "card": "UNE H100 80 Gio, TOUS LES EMPLACEMENTS REMPLIS",
            "card_sub": "ai-bunker sizing --accelerator h100-80 --image auto",
            "legend": "réglés du moins cher au plus cher ; le codeur prend le reste",
            "overhead": "Surcoût",
            "overhead_sub": "contexte, activations, de quoi être utile",
            "embed": "Embeddeur",
            "embed_sub": "bge-m3 — pas classé ; le catalogue n'en porte qu'un",
            "vision": "Vision",
            "vision_sub": "qwen3-vl-8b — le plus sobre à 10 points du meilleur",
            "image": "Texte vers image",
            "image_sub": "sd35-medium — éteint sauf demande explicite",
            "code": "Codeur",
            "code_sub": "devstral-small-2-24b — le reste, donc pas le 80B",
            "kv": "Réserve de cache clé-valeur",
            "kv_sub": "ce qui subsiste : de la concurrence, pas des poids",
            "note": (
                "Demandez des images sur cette carte et le codeur passe du 80B à mélange "
                "d'experts au 24B dense. Le rapport le dit avant le déploiement."
            ),
        },
    },
    "path": {
        "en": {
            "title": "Four positions on one path, and only one sees both ends",
            "desc": (
                "A turn travelling left to right through four boxes: a coding agent, the "
                "gateway position, a serving engine and the tool servers. Under each box, "
                "the tools that stand there — client-side configuration and guardrail "
                "libraries at the agent; LiteLLM, Kong, Portkey, Bifrost, agentgateway, "
                "the Envoy AI Gateway and ai-bunker at the gateway; ToolHive, the Docker "
                "MCP Gateway and agent-scan around the tool servers. The serving engine "
                "has nothing standing at it."
            ),
            "head": "WHERE A TURN CAN BE READ, AND BY WHOM",
            "sub": "the same field as the positioning map, placed on the path instead of in a space",
            "agent": "Coding agent",
            "agent_sub": "any OpenAI-compatible client",
            "gate": "The gateway position",
            "gate_sub": "every request, no opt-out",
            "engine": "Serving engine",
            "engine_sub": "vLLM, Ollama, anything",
            "tools": "Tool servers",
            "tools_sub": "MCP, the shell, the world",
            "also": "WHO STANDS THERE",
            "config": "Client-side config",
            "guardrails": "Guardrail libraries",
            # Re-wrapped in round 36, against the width model rather than by
            # eye. The previous break put 1,019 pixels of `foot3` on a
            # 900-pixel canvas for any reader whose browser picked a wide
            # face -- 119 pixels of caption off the edge, and `foot2` sat
            # 1.5 pixels inside it. The audit said nothing because its canvas
            # check used the *narrow* bound; it uses the wide one now, which
            # is what found this. Margins at the wide bound are 60, 44 and
            # 101 pixels.
            "foot1": (
                "Four positions, and they are not interchangeable. A file on a laptop "
                "drifts. A library runs only when the application calls it. A tool-server"
            ),
            "foot2": (
                "gateway sees a call the model has already made. Only the gateway sees "
                "every request, from every client, at both ends of the turn — and"
            ),
            "foot3": (
                "most of what stands there forwards the bytes unread. Open Policy Agent "
                "is consulted from anywhere and stands here nowhere."
            ),
        },
        "fr": {
            "title": "Quatre positions sur un trajet, une seule voit les deux bouts",
            "desc": (
                "Un tour qui traverse de gauche à droite quatre boîtes : un agent de code, "
                "la position de passerelle, un moteur d'inférence et les serveurs d'outils. "
                "Sous chaque boîte, les outils qui s'y tiennent — configuration côté client "
                "et bibliothèques de garde-fous chez l'agent ; LiteLLM, Kong, Portkey, "
                "Bifrost, agentgateway, l'Envoy AI Gateway et ai-bunker à la passerelle ; "
                "ToolHive, la Docker MCP Gateway et agent-scan autour des serveurs "
                "d'outils. Rien ne se tient au moteur d'inférence."
            ),
            "head": "OÙ UN TOUR PEUT ÊTRE LU, ET PAR QUI",
            "sub": "le même terrain que la carte de positionnement, posé sur le trajet plutôt que dans un espace",
            "agent": "Agent de code",
            "agent_sub": "tout client compatible OpenAI",
            "gate": "La position de passerelle",
            "gate_sub": "chaque requête, sans exception",
            "engine": "Moteur d'inférence",
            "engine_sub": "vLLM, Ollama, autre",
            "tools": "Serveurs d'outils",
            "tools_sub": "MCP, le shell, le monde",
            "also": "QUI S'Y TIENT",
            "config": "Configuration côté client",
            "guardrails": "Bibliothèques de garde-fous",
            "foot1": (
                "Quatre positions, et elles ne sont pas interchangeables. Un fichier sur un "
                "portable dérive ; une bibliothèque ne tourne que si l'application"
            ),
            "foot2": (
                "l'appelle ; une passerelle de serveurs d'outils voit un appel que le modèle "
                "a déjà décidé. Seule la position de passerelle voit chaque requête, de"
            ),
            "foot3": (
                "chaque client, aux deux bouts du tour — et l'essentiel de ce qui s'y tient "
                "transmet les octets sans les lire. Open Policy Agent, lui, n'y est pas."
            ),
        },
    },
    "budget": {
        "en": {
            "title": "One 26,000-token window, twice",
            "desc": (
                "Two bars of the same 26,000-token context window, with a dashed line at "
                "20,000 where compaction starts. In the first, the floor paid before "
                "anyone speaks is 6,767 tokens — 5,509 owned by the client, 1,258 by "
                "ai-bunker — and 13,233 tokens of conversation reach the line. In the "
                "second, 59 installed agent skills push the client's share to 23,263, so "
                "the floor crosses the line and no conversation fits at all: the session "
                "compacts on every turn with nothing to compact."
            ),
            "head": "ONE 26,000-TOKEN WINDOW, TWICE",
            "sub": "ai-bunker budget --gate · both measured at the relay, 2026-09-28",
            "group": ",",
            "trigger": "compaction starts at 20,000",
            "works": "A session that works",
            "works_note": "13,233 tokens to work in",
            "loops": "A session that loops",
            "loops_note": "no room, and nothing to compact",
            "col_works": "WORKS",
            "col_loops": "LOOPS",
            "client": "The client owns",
            "client_sub": "tool schemas, its system prompt, 59 installed agent skills",
            "ours": "ai-bunker owns",
            "ours_sub": "the charter and the knowledge index — under 5% of the window",
            "room": "Room to work",
            "room_sub": "what reaches the trigger — the only row that is the point",
            "margin": "Compaction margin",
            "margin_sub": "held back so there is something left to compact",
            "over": "Past the trigger",
            "over_sub": "window the floor ran into, with no conversation behind it",
            "none": "—",
            "total": "The window",
            "foot1": (
                "A floor past the line is a session that compacts on turn one and has "
                "nothing to compact: build → compaction → build, eight tokens a turn, the"
            ),
            "foot2": (
                "accelerator busy for nothing. The harness never said a word. "
                "`ai-bunker budget --gate` makes the verdict the exit code instead."
            ),
        },
        "fr": {
            "title": "Une fenêtre de 26 000 tokens, deux fois",
            "desc": (
                "Deux barres de la même fenêtre de contexte de 26 000 tokens, avec une "
                "ligne pointillée à 20 000 où démarre la compaction. Dans la première, le "
                "plancher payé avant que quiconque parle vaut 6 767 tokens — 5 509 à la "
                "charge du client, 1 258 à celle d'ai-bunker — et 13 233 tokens de "
                "conversation atteignent la ligne. Dans la seconde, 59 compétences "
                "d'agent installées portent la part du client à 23 263 : le plancher "
                "franchit la ligne et aucune conversation ne tient — la session compacte "
                "à chaque tour sans rien à compacter."
            ),
            "head": "UNE FENÊTRE DE 26 000 TOKENS, DEUX FOIS",
            "sub": "ai-bunker budget --gate · mesurées au relais, le 28/09/2026",
            "group": "\u202f",
            "trigger": "la compaction démarre à 20 000",
            "works": "Une session qui fonctionne",
            "works_note": "13 233 tokens pour travailler",
            "loops": "Une session qui boucle",
            "loops_note": "aucune place, et rien à compacter",
            "col_works": "MARCHE",
            "col_loops": "BOUCLE",
            "client": "À la charge du client",
            "client_sub": "schémas d'outils, invite système, 59 compétences installées",
            "ours": "À la charge d'ai-bunker",
            "ours_sub": "la charte et l'index de connaissances — moins de 5 % de la fenêtre",
            "room": "De quoi travailler",
            "room_sub": "ce qui atteint le seuil — la seule ligne qui compte",
            "margin": "Marge de compaction",
            "margin_sub": "réservée pour qu'il reste quelque chose à compacter",
            "over": "Au-delà du seuil",
            "over_sub": "la fenêtre où le plancher a mordu, sans conversation derrière",
            "none": "—",
            "total": "La fenêtre",
            "foot1": (
                "Un plancher au-delà de la ligne, c'est une session qui compacte dès le "
                "premier tour sans rien à compacter : construire → compacter →"
            ),
            "foot2": (
                "construire, huit tokens par tour, l'accélérateur occupé pour rien. Le "
                "harnais n'a rien dit. `ai-bunker budget --gate` en fait un code de sortie."
            ),
        },
    },
    "trade": {
        "en": {
            "title": "What one picture costs, on five machines",
            "desc": (
                "Seconds per image against memory bandwidth for five machines, all "
                "running the same text-to-image model. A MacBook Pro M2 Max at 400 "
                "gigabytes per second takes 24.8 seconds; a Mac Studio M3 Ultra at 819 "
                "takes 12.1; an RTX PRO 5000 72 GB at 1,344 takes 7.4; an RTX PRO 6000 "
                "96 GB at 1,792 takes 5.5; an H100 at 3,350 takes 3. Two of them are "
                "marked in red, where asking for pictures also costs the 80B coder."
            ),
            "head": "ONE PICTURE MODEL, FIVE MEMORY SYSTEMS",
            "sub": (
                "Stable Diffusion 3.5 Medium, 26.4 GiB, 28 denoising steps at 1024x1024, "
                "on every machine"
            ),
            "x": "memory bandwidth, GB/s",
            "y": "seconds an image (lower is better)",
            "macbook": "MacBook Pro M2 Max",
            "studio": "Mac Studio M3 Ultra",
            "pro5000": "RTX PRO 5000 72 GB",
            "pro6000": "RTX PRO 6000 96 GB",
            "h100": "H100 80 GB",
            "unit": "s",
            "decimal": ".",
            "foot": (
                "Red: the picture fits and the 45 GiB coder no longer does. Below 92 GiB the "
                "slot is not paid for in seconds — it is paid for in the coder."
            ),
        },
        "fr": {
            "title": "Ce que coûte une image, sur cinq machines",
            "desc": (
                "Secondes par image en fonction de la bande passante mémoire, pour cinq "
                "machines exécutant toutes le même modèle texte-vers-image. Un MacBook "
                "Pro M2 Max à 400 gigaoctets par seconde met 24,8 secondes ; un Mac "
                "Studio M3 Ultra à 819 met 12,1 ; une RTX PRO 5000 72 Go à 1 344 met "
                "7,4 ; une RTX PRO 6000 96 Go à 1 792 met 5,5 ; une H100 à 3 350 met 3. "
                "Deux sont marquées en rouge : demander des images y coûte aussi le "
                "codeur 80B."
            ),
            "head": "UN MODÈLE D'IMAGE, CINQ SYSTÈMES MÉMOIRE",
            "sub": (
                "Stable Diffusion 3.5 Medium, 26,4 Gio, 28 étapes de débruitage en "
                "1024x1024, sur chaque machine"
            ),
            "x": "bande passante mémoire, Go/s",
            "y": "secondes par image (moins c'est mieux)",
            "macbook": "MacBook Pro M2 Max",
            "studio": "Mac Studio M3 Ultra",
            "pro5000": "RTX PRO 5000 72 Go",
            "pro6000": "RTX PRO 6000 96 Go",
            "h100": "H100 80 Go",
            "unit": "s",
            "decimal": ",",
            "foot": (
                "En rouge : l'image tient, le codeur de 45 Gio non. Sous 92 Gio, "
                "l'emplacement ne se paie pas en secondes — il se paie en codeur."
            ),
        },
    },
}

#: The drawing for each name in :data:`STRINGS`.
DRAW = {
    "pipeline": pipeline,
    "plan": plan,
    "trade": trade,
    "budget": budget,
    "path": path,
}


def files() -> dict[Path, str]:
    """Every figure this script owns, keyed by the path it belongs at.

    English keeps the bare name because `README.md` is the English half and
    the bare name is the one a reader types; French takes the `.fr` infix,
    like the site's pages.
    """
    out: dict[Path, str] = {}
    for name, langs in STRINGS.items():
        for lang, words in langs.items():
            suffix = "" if lang == "en" else f".{lang}"
            out[OUT / f"figure-{name}{suffix}.svg"] = DRAW[name](words)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="do not write; fail if any committed figure is out of date",
    )
    args = parser.parse_args()

    stale = []
    for path, svg in files().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == svg:
            continue
        stale.append(path)
        if not args.check:
            path.write_text(svg, encoding="utf-8")

    rel = [str(p.relative_to(ROOT)) for p in stale]
    if args.check:
        if stale:
            print(f"out of date: {', '.join(rel)}", file=sys.stderr)
            print("run: python scripts/make_figures.py", file=sys.stderr)
            return 1
        print(f"{len(files())} figure(s) up to date")
        return 0
    print(f"{len(stale)} written, {len(files()) - len(stale)} unchanged")
    for name in rel:
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
