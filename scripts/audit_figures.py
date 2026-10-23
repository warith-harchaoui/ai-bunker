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


def audit(scheme: str) -> list[str]:
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
        verdict = "ok " if ratio >= FLOOR else "FAIL"
        line = f"  {verdict} {ratio:5.2f}  {ink:6} on {surface or 'page'!s:11}  {what}"
        print(line)
        if ratio < FLOOR:
            failures.append(f"{scheme}: {ink} on {surface or 'page'} is {ratio:.2f}:1 ({what})")
    return failures


def main() -> int:
    if CSS is None:
        print("the site is not on this machine; no figures to audit")
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quiet", action="store_true", help="only report failures")
    args = parser.parse_args()

    failures = []
    for scheme in ("light", "dark"):
        if not args.quiet:
            print(f"{scheme}:")
        failures += audit(scheme)

    print()
    if failures:
        print(f"{len(failures)} pair(s) below the {FLOOR}:1 floor:")
        for f in failures:
            print(f"  {f}")
        return 1
    print(f"{len(PAIRS) * 2} pairs checked across 2 colour schemes")
    print(f"all pairs meet the {FLOOR}:1 floor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
