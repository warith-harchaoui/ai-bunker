#!/usr/bin/env python3
"""
WCAG contrast audit over the dashboard's design tokens.

Written here rather than borrowed because the auditor the UI skill advertises
is not installed on this machine (``sprezzature-colors/scripts/`` is empty).
It is small, deterministic, needs no model and no browser, so writing it beats
shipping a page whose contrast nobody checked.

What it does: parse the ``--token: #hex`` declarations out of a single-file
page, resolve them for **both** colour schemes, and check every pair the page
actually puts together against the WCAG 2.1 thresholds.

The pairs are declared rather than discovered. Discovering them would mean a
CSS cascade engine; declaring them means someone has to say what the page
really renders, which is the part a tool cannot know.

    python scripts/audit_contrast.py ai_bunker/static/gui.html

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

#: WCAG 2.1 minimums.
AA_TEXT = 4.5  # body text
AA_LARGE = 3.0  # >=18.66px bold or >=24px, and non-text UI components

#: Pairs the page genuinely renders, as (foreground, background, label, floor).
#: A token pair that never appears together is not worth a finding, and one
#: that appears and is absent here is a gap in this list, not in the page --
#: which is why the list is reviewed rather than generated.
PAIRS: tuple[tuple[str, str, str, float], ...] = (
    ("label", "bg", "body text on the page ground", AA_TEXT),
    ("label", "surface", "body text on a card", AA_TEXT),
    ("label", "raised", "body text on a raised surface", AA_TEXT),
    ("label-2", "surface", "secondary text on a card", AA_TEXT),
    ("label-2", "bg", "secondary text on the page ground", AA_TEXT),
    ("label-3", "surface", "table headers and hints", AA_LARGE),
    ("blue", "surface", "the accent on a card", AA_LARGE),
    ("green", "surface", "the sovereign chip", AA_LARGE),
    ("orange", "surface", "the warning chip", AA_LARGE),
    ("red", "surface", "the refused outcome", AA_LARGE),
    ("separator", "surface", "a hairline border against its card", 1.2),
)

#: Foreground/background pairs where the background is itself an accent.
ON_ACCENT: tuple[tuple[str, str, float], ...] = (
    # A button label is text, so it needs the text floor, not the UI one.
    ("#FFFFFF", "blue", AA_TEXT),
)

#: Tokens whose dark-scheme value is a lighter variant: checking white-on-accent
#: there would audit a combination the page never renders (the dark scheme puts
#: the light label on a dark fill, not white on a bright accent).
LIGHT_ONLY_ON_ACCENT = frozenset({"dark"})

_TOKEN = re.compile(r"--([a-z0-9-]+)\s*:\s*(#[0-9A-Fa-f]{3,8})\s*;")


def _srgb(channel: int) -> float:
    c = channel / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    """Relative luminance per WCAG 2.1."""
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _srgb(r) + 0.7152 * _srgb(g) + 0.0722 * _srgb(b)


def ratio(a: str, b: str) -> float:
    """Contrast ratio between two hex colours, 1.0 to 21.0."""
    la, lb = luminance(a), luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def schemes(css: str) -> dict[str, dict[str, str]]:
    """Resolve the token table for each colour scheme.

    Light is whatever bare ``:root`` declares. Dark is light with the
    overrides applied, because that is how the cascade actually resolves it --
    a dark block that only redefines six tokens inherits the rest, and
    auditing it as if it were a complete palette would audit a page nobody
    sees.
    """
    light: dict[str, str] = {}
    dark: dict[str, str] = {}

    # Split on the blocks that redefine tokens for dark. Everything before the
    # first such block is the light palette.
    marker = re.search(r"@media\s*\(prefers-color-scheme:\s*dark\)", css)
    head = css[: marker.start()] if marker else css
    tail = css[marker.start() :] if marker else ""

    for name, value in _TOKEN.findall(head):
        light[name] = value
    dark.update(light)
    for name, value in _TOKEN.findall(tail):
        dark[name] = value
    return {"light": light, "dark": dark}


def audit(path: Path) -> int:
    css = path.read_text(encoding="utf-8")
    table = schemes(css)

    findings: list[str] = []
    checks = 0

    for scheme, tokens in table.items():
        for fg, bg, label, floor in PAIRS:
            if fg not in tokens or bg not in tokens:
                findings.append(f"  {scheme}: token --{fg} or --{bg} is not declared")
                continue
            checks += 1
            r = ratio(tokens[fg], tokens[bg])
            if r < floor:
                findings.append(
                    f"  {scheme}: {label} — {tokens[fg]} on {tokens[bg]} is "
                    f"{r:.2f}:1, under {floor}:1"
                )
        for literal, bg, floor in ON_ACCENT:
            if bg not in tokens or scheme in LIGHT_ONLY_ON_ACCENT:
                continue
            checks += 1
            r = ratio(literal, tokens[bg])
            if r < floor:
                findings.append(
                    f"  {scheme}: {literal} on --{bg} ({tokens[bg]}) is {r:.2f}:1, under {floor}:1"
                )

    print(f"{path}: {checks} pairs checked across {len(table)} colour schemes")
    if findings:
        print("\nFAILURES")
        print("\n".join(findings))
        return 1
    print("all pairs meet their WCAG floor")
    return 0


def report(path: Path) -> None:
    """Print every ratio, for tuning rather than gating."""
    table = schemes(path.read_text(encoding="utf-8"))
    for scheme, tokens in table.items():
        print(f"\n{scheme}")
        for fg, bg, label, floor in PAIRS:
            if fg in tokens and bg in tokens:
                r = ratio(tokens[fg], tokens[bg])
                mark = "ok " if r >= floor else "LOW"
                print(f"  [{mark}] {r:>5.2f}:1  (>= {floor})  {label}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", nargs="?", default="ai_bunker/static/gui.html")
    parser.add_argument("--report", action="store_true", help="Print every ratio.")
    args = parser.parse_args(argv)

    path = Path(args.page)
    if not path.exists():
        print(f"No such file: {path}", file=sys.stderr)
        return 2
    if args.report:
        report(path)
        return 0
    return audit(path)


if __name__ == "__main__":
    raise SystemExit(main())
