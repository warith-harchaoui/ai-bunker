"""Rewrite every quoted figure from the repository that produced it.

Why
---
The site and both READMEs quote counts -- tests, rules, assertions -- and
`tests/test_site.py` refuses to pass when any of them has drifted. That guard
is the point: hand-written pages are worth having only if they cannot lie.
But it turns every added test into a hunt through four page modules and two
READMEs, and a chore done by hand is a chore eventually done wrong.

This does it from the source, so the guard has nothing to catch. It is the
make-side of the same rule.

    python scripts/sync_counts.py            # rewrite, then rebuild the site
    python scripts/sync_counts.py --check    # report drift, change nothing

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

#: Every file that quotes a figure, and is not generated from another.
SOURCES = [
    WEB / "pages" / "index.en.py",
    WEB / "pages" / "index.fr.py",
    WEB / "pages" / "start.en.py",
    WEB / "pages" / "start.fr.py",
    ROOT / "README.md",
    ROOT / "LISEZMOI.md",
    ROOT / "EXAMPLES.md",
    ROOT / "EXEMPLES.md",
    WEB / "DEPLOY.md",
]


def collected_tests() -> int:
    """What `pytest` actually collects. Not an estimate: see test_site.py."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=300,
        check=False,
    )
    counts = [int(n) for n in re.findall(r"^\S+\.py: (\d+)$", result.stdout, re.M)]
    if not counts:
        raise SystemExit(f"could not read collected counts from pytest:\n{result.stdout[-2000:]}")
    return sum(counts)


def rule_figures() -> tuple[int, int]:
    sys.path.insert(0, str(ROOT))
    from ai_bunker.rules import load_rules
    from ai_bunker.rules import test_rules as check_rules

    rules = load_rules(ROOT / "charter" / "rules")
    return len(rules), check_rules(rules).passed


def substitutions() -> list[tuple[re.Pattern[str], str, str]]:
    """(pattern, replacement, label). Every pattern keeps its own context, so
    a number that means something else is never touched: `327 tests` inside a
    sentence about a past moment stays, because none of these match it."""
    tests = collected_tests()
    rules, assertions = rule_figures()
    return [
        (re.compile(r"\b\d+ tests · "), f"{tests} tests · ", f"{tests} tests (site footer)"),
        (
            re.compile(r"with \d+ tests and a green"),
            f"with {tests} tests and a green",
            "tests (FAQ)",
        ),
        (re.compile(r"\b\d+ tests (and|et) a green CI"), rf"{tests} tests \1 a green CI", "tests"),
        (
            re.compile(r"\b\d+ tests et une porte CI"),
            f"{tests} tests et une porte CI",
            "tests (fr)",
        ),
        (re.compile(r"\|\s*\d+ tests, `ruff`"), f"| {tests} tests, `ruff`", "tests (checklist)"),
        (re.compile(r"^(\s*rules loaded\s+)\d+$", re.M), rf"\g<1>{rules}", "rules loaded"),
        (re.compile(r"^(\s*assertions passed\s+)\d+$", re.M), rf"\g<1>{assertions}", "assertions"),
        (
            re.compile(r"\[ok\s*\]\s*\d+ rules loaded"),
            f"[ok  ] {rules} rules loaded",
            "rules (doctor)",
        ),
        (
            re.compile(r"\[ok\s*\]\s*\d+ rule assertions pass"),
            f"[ok  ] {assertions} rule assertions pass",
            "assertions (doctor)",
        ),
        (
            re.compile(r"\b\d+ rules, \d+ assertions"),
            f"{rules} rules, {assertions} assertions",
            "both",
        ),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Report drift, change nothing.")
    args = parser.parse_args(argv)

    subs = substitutions()
    changed: list[str] = []
    for path in SOURCES:
        if not path.exists():
            continue
        before = path.read_text(encoding="utf-8")
        after = before
        for pattern, replacement, _label in subs:
            after = pattern.sub(replacement, after)
        if after != before:
            changed.append(str(path.relative_to(ROOT)))
            if not args.check:
                path.write_text(after, encoding="utf-8")

    if args.check:
        if changed:
            print(f"{len(changed)} file(s) quote a stale figure:")
            for name in changed:
                print(f"  {name}")
            return 1
        print("every quoted figure matches the repository")
        return 0

    if changed:
        for name in changed:
            print(f"  updated {name}")
        subprocess.run(
            [sys.executable, str(WEB / "build.py")], cwd=WEB, check=True, capture_output=True
        )
        print(f"{len(changed)} file(s) updated, site rebuilt")
    else:
        print("every quoted figure already matches the repository")
    return 0


if __name__ == "__main__":
    sys.exit(main())
