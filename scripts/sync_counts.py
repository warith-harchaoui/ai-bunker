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
    ROOT / "docs" / "RULES.md",
    ROOT / "docs" / "REGLES.md",
    ROOT / "EXAMPLES.md",
    ROOT / "EXEMPLES.md",
    WEB / "DEPLOY.md",
    WEB / "llms.txt",
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


def scenario_count() -> int:
    """The scenarios `spec --run` executes, from the parser that runs them.

    Not a `grep` for `Scenario:`. The count quoted in the prose is a claim
    about what the specification *runs*, and the parser is the only thing that
    knows -- it is also what would raise on a step nobody supports, which a
    line count would read as a scenario.
    """
    sys.path.insert(0, str(ROOT))
    from ai_bunker.spec import load as load_scenarios

    return len(load_scenarios(ROOT / "features"))


def charter_floor() -> int:
    """Tokens the charter costs on every request, from the charter itself.

    Deterministic -- it is a token count over files in this repository -- and
    it moved by 60% when `CHARS_PER_TOKEN` was corrected from 4.0 to 2.5.
    Eight documents quoted the old 607 as real command output and nothing
    noticed: `sync_counts` did not own this figure and `lint_claims` guards
    sentences rather than numbers, so it fell between the two guards that
    exist to prevent exactly this.
    """
    sys.path.insert(0, str(ROOT))
    from ai_bunker.budget import Counter
    from ai_bunker.charter import load_charter, system_blocks

    counter = Counter(allow_ratio=True)
    return sum(counter.count(block) for block in system_blocks(load_charter(ROOT / "charter")))


def charter_ratio() -> tuple[float, int, int]:
    """Index tokens against every page concatenated, for the shipped charter.

    The thesis, measured on the charter a reader actually has. `charter.py`
    quotes a real 37-page measurement from a deployment that is not in this
    repository, and a number nobody can reach is the weakest kind this project
    allows itself -- so the command prints this instead, and the figure is
    owned here for the same reason the floor is.
    """
    sys.path.insert(0, str(ROOT))
    from ai_bunker.budget import Counter
    from ai_bunker.charter import build_index, load_charter

    charter = load_charter(ROOT / "charter")
    counter = Counter(allow_ratio=True)
    concatenated = sum(
        counter.count(page.path.read_text(encoding="utf-8")) for page in charter.pages
    )
    index_only = counter.count(build_index(charter)) or 1
    return concatenated / index_only, concatenated, index_only


def substitutions() -> list[tuple[re.Pattern[str], str, str]]:
    """(pattern, replacement, label). Every pattern keeps its own context, so
    a number that means something else is never touched: `327 tests` inside a
    sentence about a past moment stays, because none of these match it."""
    tests = collected_tests()
    rules, assertions = rule_figures()
    scenarios = scenario_count()
    floor = charter_floor()
    ratio, concatenated, index_only = charter_ratio()
    return [
        (
            re.compile(r"index vs all\s+[\d.]+x\s+\([\d,]+ tokens[^)]*\)"),
            f"index vs all {ratio:>5.1f}x  ({concatenated:,} tokens if every page "
            f"were pasted in, {index_only:,} as an index)",
            "charter index ratio",
        ),
        (
            re.compile(r"floor cost\s+[\d,]+ tokens"),
            f"floor cost   {floor:,} tokens",
            "charter floor (command output)",
        ),
        (
            re.compile(r"\*\*[\d,]+ tokens paid on every request"),
            f"**{floor:,} tokens paid on every request",
            "charter floor (prose)",
        ),
        # And the French twin. Writing this substitution English-only was the
        # same mistake this script already carries a comment about, made again
        # in the same file: `LISEZMOI.md` quoted 25 rules for three sessions
        # because every pattern was English. A figure in a translated document
        # is still a figure, and apparently that has to be checked each time
        # rather than remembered.
        (
            re.compile(r"\*\*[\d,]+ tokens payés à chaque"),
            f"**{floor:,} tokens payés à chaque",
            "charter floor (prose, fr)",
        ),
        # The site deliberately quotes NO test count: it moved on every commit
        # that added a test, which made the deployed site stale after every
        # commit and bought nothing a green CI gate does not already say. Only
        # the READMEs carry the number, where correcting it costs no upload.
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
        # The three-figure summary comes first, and the pair below it is left
        # in place rather than folded into one optional group. Run the pair
        # first and it rewrites the two numbers it knows and leaves the third
        # standing, which is exactly how `224 scenarios` survived next to a
        # corrected `27 rules, 218 assertions`: a sentence half-updated by its
        # own generator reads more trustworthy than one left alone.
        (
            re.compile(r"\b\d+ rules, \d+ assertions, \d+ scenarios"),
            f"{rules} rules, {assertions} assertions, {scenarios} scenarios",
            "all three",
        ),
        # And the French twin, which none of the English patterns could ever
        # match. `LISEZMOI.md` quoted 25 rules and 198 assertions for three
        # sessions while `README.md` was corrected on every run -- the guard
        # was bilingual in the files it read and monolingual in what it looked
        # for. A figure in a translated document is still a figure.
        (
            re.compile(r"\b\d+ règles, \d+ assertions, \d+ scénarios"),
            f"{rules} règles, {assertions} assertions, {scenarios} scénarios",
            "all three (fr)",
        ),
        (
            re.compile(r"\b\d+ rules, \d+ assertions"),
            f"{rules} rules, {assertions} assertions",
            "both",
        ),
        (
            re.compile(r"\b\d+ règles, \d+ assertions"),
            f"{rules} règles, {assertions} assertions",
            "both (fr)",
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
