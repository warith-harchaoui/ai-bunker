#!/usr/bin/env python3
"""
Static accessibility lint for the dashboard.

Written here for the same reason as the contrast auditor: the one the UI skill
advertises is not installed on this machine. Both are small and deterministic,
and a page shipped without either is a page whose accessibility nobody checked.

**Static only, and the limit is the point.** These are the rules decidable from
the source without a browser or a runtime DOM: a missing ``alt``, an input with
no label, a button with no accessible name. It is a pre-commit gate, not a
replacement for axe-core or Lighthouse, which catch what only a rendered page
reveals -- computed contrast, focus order, live-region behaviour.

    python scripts/lint_a11y.py ai_bunker/static/gui.html

Exits non-zero on any finding.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

#: Elements that must carry an accessible name, and where it can come from.
_NEEDS_NAME = {"button", "a"}
_NAME_ATTRS = ("aria-label", "aria-labelledby", "title")

#: Interactive elements, for the keyboard and hit-area rules.
_INTERACTIVE = {"button", "a", "input", "select", "textarea", "summary", "details"}


@dataclass
class Finding:
    rule: str
    line: int
    detail: str

    def __str__(self) -> str:
        return f"  {self.rule:<10} line {self.line:>4}  {self.detail}"


class Linter(HTMLParser):
    """Walk the document, holding only what a rule actually needs."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.findings: list[Finding] = []
        self.ids: set[str] = set()
        self.label_for: set[str] = set()
        self.inputs: list[tuple[int, str, dict[str, str]]] = []
        self.idrefs: list[tuple[int, str, str]] = []
        self.headings: list[tuple[int, int]] = []
        self.open_named: list[tuple[str, int, bool]] = []  # tag, line, has_text
        self.has_lang = False
        self.has_title = False
        self.in_title = False

    # -- helpers ---------------------------------------------------------

    def _add(self, rule: str, detail: str) -> None:
        self.findings.append(Finding(rule, self.getpos()[0], detail))

    # -- parsing ---------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        line = self.getpos()[0]

        if tag == "html":
            self.has_lang = bool(a.get("lang", "").strip())
        if tag == "title":
            self.in_title = True

        if "id" in a:
            self.ids.add(a["id"])
        for ref_attr in ("aria-labelledby", "aria-describedby", "aria-controls", "for"):
            for ref in a.get(ref_attr, "").split():
                self.idrefs.append((line, ref_attr, ref))
        if tag == "label" and a.get("for"):
            self.label_for.add(a["for"])

        if tag == "img" and "alt" not in a:
            self._add("A11Y001", "an <img> with no alt attribute")

        if tag in ("input", "select", "textarea"):
            self.inputs.append((line, tag, a))

        typed = a.get("type") in ("text", "email", "search", "password", "tel", "url")
        if tag == "input" and typed and "autocomplete" not in a:
            self._add("A11Y006", f'<input type="{a.get("type")}"> with no autocomplete')

        if tag in _NEEDS_NAME:
            named = any(a.get(x, "").strip() for x in _NAME_ATTRS)
            self.open_named.append((tag, line, named))

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.headings.append((line, int(tag[1])))

        clickable = "onclick" in a or a.get("role") in ("button", "link")
        if tag == "div" and clickable and "tabindex" not in a:
            self._add("A11Y004", f"a clickable <div> with no tabindex (role={a.get('role')})")

        if a.get("tabindex", "").lstrip("-").isdigit() and int(a["tabindex"]) > 0:
            self._add("A11Y005", f'tabindex="{a["tabindex"]}" overrides the natural order')

        if tag == "dialog" and "aria-label" not in a and "aria-labelledby" not in a:
            self._add("A11Y007", "a <dialog> with no accessible name")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag in _NEEDS_NAME and self.open_named:
            opened, line, named = self.open_named.pop()
            if opened == tag and not named:
                self.findings.append(
                    Finding("A11Y002", line, f"a <{tag}> with no text and no aria-label")
                )

    def handle_data(self, data: str) -> None:
        if self.in_title and data.strip():
            self.has_title = True
        if data.strip() and self.open_named:
            tag, line, _ = self.open_named[-1]
            self.open_named[-1] = (tag, line, True)


def _structural(linter: Linter, source: str) -> list[Finding]:
    """Rules that need the whole document, not one tag."""
    out: list[Finding] = []

    if not linter.has_lang:
        out.append(Finding("A11Y008", 1, "<html> has no lang attribute"))
    if not linter.has_title:
        out.append(Finding("A11Y009", 1, "the document has no non-empty <title>"))

    for line, tag, attrs in linter.inputs:
        if attrs.get("type") in ("hidden", "submit", "button", "reset"):
            continue
        has_label = (
            attrs.get("id", "") in linter.label_for
            or attrs.get("aria-label", "").strip()
            or attrs.get("aria-labelledby", "").strip()
        )
        if not has_label:
            out.append(Finding("A11Y003", line, f"a <{tag}> with no associated label"))

    for line, attr, ref in linter.idrefs:
        if attr == "for":
            continue  # a label may legitimately precede its input in source order
        if ref not in linter.ids:
            out.append(Finding("A11Y010", line, f'{attr}="{ref}" points at no element'))

    previous = 0
    for line, level in linter.headings:
        if previous and level > previous + 1:
            out.append(Finding("A11Y011", line, f"heading jumps from h{previous} to h{level}"))
        previous = level

    # A page that animates without honouring the user's setting makes some
    # people ill; it is a correctness bug, not a preference.
    if (
        re.search(r"@keyframes|transition:|animation:", source)
        and "prefers-reduced-motion" not in source
    ):
        out.append(Finding("A11Y012", 1, "the page animates with no prefers-reduced-motion guard"))

    # A focus ring removed and not replaced makes the page unusable by keyboard.
    if re.search(r"outline\s*:\s*(none|0)", source) and ":focus-visible" not in source:
        out.append(Finding("A11Y013", 1, "outline removed with no :focus-visible replacement"))

    if _INTERACTIVE and "min-height" not in source and "min-h" not in source:
        out.append(Finding("A11Y014", 1, "no minimum hit area declared for controls"))

    return out


def lint(path: Path) -> int:
    source = path.read_text(encoding="utf-8")
    linter = Linter()
    linter.feed(source)
    findings = sorted(linter.findings + _structural(linter, source), key=lambda f: (f.line, f.rule))

    print(f"{path}: {len(source.splitlines())} lines, {len(findings)} finding(s)")
    if findings:
        print()
        for f in findings:
            print(f)
        print()
        print("  Static rules only. Run a browser audit (axe-core, Lighthouse) for")
        print("  what a rendered page reveals: focus order, live regions, computed")
        print("  contrast on overlapping surfaces.")
        return 1
    print("no static accessibility findings")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("page", nargs="?", default="ai_bunker/static/gui.html")
    args = parser.parse_args(argv)
    path = Path(args.page)
    if not path.exists():
        print(f"No such file: {path}", file=sys.stderr)
        return 2
    return lint(path)


if __name__ == "__main__":
    raise SystemExit(main())
