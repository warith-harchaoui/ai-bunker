"""
Tests for the website.

The site is written by hand rather than generated from the Markdown, which was
a deliberate choice and carries one cost: the figures quoted on it can drift
from the repository. In three weeks the README says 354 tests and the site says
269, and nothing notices.

So the numbers are asserted against their sources. That keeps the advantage of
hand-written pages without the defect.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import re
import subprocess
import sys

import pytest

from ai_bunker.adopt import ROOT
from ai_bunker.charter import load_charter
from ai_bunker.rules import load_rules
from ai_bunker.rules import test_rules as check_rules

WEB = ROOT / "web"
PAGES = sorted(WEB.glob("*.html")) + sorted((WEB / "fr").glob("*.html"))


@pytest.fixture(scope="module")
def all_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in PAGES)


def test_the_site_has_both_languages():
    assert len(list(WEB.glob("*.html"))) == 4
    assert len(list((WEB / "fr").glob("*.html"))) == 4


# ---------------------------------------------------------------------------
# The numbers on the site are the repository's numbers.
# ---------------------------------------------------------------------------


def _collected_tests() -> int:
    """Count tests by reading the files, not by running pytest inside pytest.

    A `--collect-only` subprocess re-imports the whole suite from within a test
    that is itself part of it; it was slow enough to blow a two-minute timeout.
    Parsing the AST is instant, has no recursion risk, and expands the
    parametrize cases the same way the collector does.
    """
    import ast
    import contextlib

    total = 0
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
                continue
            cases = 1
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                target = ast.unparse(decorator.func)
                if "parametrize" not in target or len(decorator.args) < 2:
                    continue
                values = decorator.args[1]
                if isinstance(values, (ast.List, ast.Tuple)):
                    cases *= len(values.elts)
                elif isinstance(values, ast.ListComp):
                    # A comprehension over a module-level constant: evaluate
                    # it. One it cannot resolve counts as a single case, which
                    # under-counts rather than guessing.
                    with contextlib.suppress(Exception):
                        cases *= len(eval(ast.unparse(values), {"PAGES": PAGES, "WEB": WEB}))
            total += cases
    return total


def test_the_quoted_test_count_is_real(all_text):
    """The figure most likely to rot, since it changes on every commit."""
    quoted = {int(n) for n in re.findall(r"(\d{3}) tests", all_text)}
    assert quoted, "the site no longer quotes a test count; drop this test too"
    actual = _collected_tests()
    for n in quoted:
        assert n == actual, f"the site says {n} tests; the suite has {actual}"


def test_the_quoted_rule_counts_are_real(all_text):
    rules = load_rules(ROOT / "charter" / "rules")
    report = check_rules(rules)

    for pattern, actual, label in (
        (r"rules loaded\s+(\d+)", len(rules), "rules"),
        (r"assertions passed\s+(\d+)", report.passed, "assertions"),
    ):
        quoted = {int(n) for n in re.findall(pattern, all_text)}
        assert quoted, f"the site no longer quotes {label}"
        for n in quoted:
            assert n == actual, f"the site says {n} {label}; the repository has {actual}"


def test_the_quoted_coverage_is_real(all_text):
    report = check_rules(load_rules(ROOT / "charter" / "rules"))
    quoted = {int(n) for n in re.findall(r"rules carrying evidence\s+(\d+)%", all_text)}
    assert quoted
    for n in quoted:
        assert n == round(report.coverage * 100)


def test_the_quoted_charter_figures_are_real(all_text):
    """607 tokens of floor, 2,608 characters not loaded — both on the site."""
    charter = load_charter(ROOT / "charter")
    pages = sum(p.chars for p in charter.pages)
    for n in {int(n.replace(",", "")) for n in re.findall(r"([\d,]{3,}) characters", all_text)}:
        assert n == pages, f"the site says {n:,} characters of pages; the charter has {pages:,}"


def test_the_quoted_version_is_real(all_text):
    from ai_bunker import __version__

    quoted = set(re.findall(r"(\d+\.\d+\.\d+)-alpha", all_text))
    assert quoted
    for v in quoted:
        assert v == __version__


# ---------------------------------------------------------------------------
# What the site must not do.
# ---------------------------------------------------------------------------


def test_no_page_fetches_from_a_third_party(all_text):
    """The site makes the sovereignty claim; it cannot contradict it on load."""
    for host in (
        "cdn.tailwindcss.com",
        "googleapis.com",
        "jsdelivr",
        "unpkg",
        "cdnjs",
        "fonts.gstatic",
        "google-analytics",
        "googletagmanager",
    ):
        assert host not in all_text, f"a page reaches out to {host}"


def test_no_tracker(all_text):
    for tracker in ("gtag(", "_paq", "fbq(", "plausible", "analytics"):
        assert tracker not in all_text.lower(), f"found {tracker}"


def test_every_image_has_an_alt_that_is_not_the_caption():
    """An alt repeating the caption tells a screen-reader user nothing new."""
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        for img in re.findall(r"<img[^>]+>", text):
            if 'alt=""' in img:
                continue  # decorative, correctly marked
            alt = re.search(r'alt="([^"]*)"', img)
            assert alt and alt.group(1).strip(), f"{page.name}: <img> with no alt"
            assert len(alt.group(1)) > 40, (
                f"{page.name}: alt is too short to describe a figure: {alt.group(1)!r}"
            )


# ---------------------------------------------------------------------------
# The gates the deploy depends on.
# ---------------------------------------------------------------------------


def test_the_publish_checker_passes():
    result = subprocess.run(
        [sys.executable, str(WEB / "publish.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
        cwd=WEB,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("page", [p.relative_to(WEB).as_posix() for p in PAGES])
def test_every_page_passes_the_accessibility_lint(page):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "lint_a11y.py"), page],
        capture_output=True,
        text=True,
        check=False,
        cwd=WEB,
    )
    assert result.returncode == 0, result.stdout


def test_the_stylesheet_is_built_and_committed():
    """Deployment is a file upload; a missing stylesheet means a Node toolchain
    on the far end, which the person who owns the site should not need."""
    css = WEB / "css" / "app.css"
    assert css.exists() and css.stat().st_size > 5000
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(css)], cwd=ROOT, check=False
    ).returncode
    assert ignored != 0, "app.css is gitignored; it must ship"
