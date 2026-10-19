"""
Tests for the dashboard and its quality gates.

Two kinds of test here, and the second is the unusual one. The first checks the
page and its endpoints. The second checks the **auditors** -- because a linter
that cannot fail is worse than no linter: it produces a green tick and a false
sense that something was verified.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from ai_bunker.adopt import ROOT

GUI = ROOT / "ai_bunker" / "static" / "gui.html"
CONTRAST = ROOT / "scripts" / "audit_contrast.py"
A11Y = ROOT / "scripts" / "lint_a11y.py"


def _run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args], capture_output=True, text=True, check=False
    )


# ---------------------------------------------------------------------------
# The page itself.
# ---------------------------------------------------------------------------


def test_the_page_makes_no_external_request():
    """A sovereignty dashboard cannot start by fetching from a third party.

    This is why the page is hand-written CSS rather than the house Tailwind
    style: without a build step, Tailwind means the Play CDN, and the first
    thing the dashboard would do is contradict what it displays.
    """
    source = GUI.read_text(encoding="utf-8")
    for host in (
        "cdn.tailwindcss.com",
        "googleapis.com",
        "jsdelivr",
        "unpkg",
        "cdnjs",
        "fonts.gstatic",
    ):
        assert host not in source, f"the page reaches out to {host}"
    assert (
        "//" not in source.split("<script")[-1].split("src=")[-1][:40] or 'src="' not in source
    ), "no script may be loaded from a URL"


def test_the_page_imports_no_framework():
    source = GUI.read_text(encoding="utf-8").lower()
    for framework in ("react", "vue.js", "svelte", "angular", "solid-js"):
        assert framework not in source


def test_no_raw_hex_in_the_markup():
    """Colour lives in tokens, so a palette change is one edit and not forty."""
    source = GUI.read_text(encoding="utf-8")
    body = source[source.index("</style>") :]
    # The only literal in script is #FFFFFF-free; colours come from var(--token).
    import re

    leaked = [h for h in re.findall(r"#[0-9A-Fa-f]{6}\b", body)]
    assert not leaked, f"raw hex outside the token block: {leaked}"


def test_both_colour_schemes_are_defined():
    source = GUI.read_text(encoding="utf-8")
    assert "prefers-color-scheme: dark" in source
    assert '[data-color-scheme="dark"]' in source, "an explicit choice must win too"


def test_the_api_key_is_never_persisted():
    """A dashboard is not a place to store a credential.

    Matches a *call*, not a mention: the comment in the page explains why
    localStorage is avoided, and a naive substring search flags that comment
    as the very thing it rules out.
    """
    import re

    source = GUI.read_text(encoding="utf-8")
    for api in ("localStorage", "sessionStorage", "document.cookie"):
        assert not re.search(rf"\b{api}\s*[.\[]", source), f"{api} is used"
    assert "URLSearchParams" in source, "the key comes from the URL, per request"


def test_every_tile_asks_a_question():
    """Dashboard ergonomics: a tile title states the question it answers."""
    source = GUI.read_text(encoding="utf-8")
    import re

    headings = re.findall(r"<h2[^>]*>(.*?)</h2>", source, re.S)
    assert len(headings) >= 4
    for h in headings:
        assert h.strip().endswith("?"), f"tile title is not a question: {h.strip()!r}"


def test_measurable_tiles_declare_their_polarity():
    """ "Is 607 good or bad?" is not answerable without saying which way is up."""
    source = GUI.read_text(encoding="utf-8")
    assert source.count('class="polarity"') >= 2
    assert "↑ more conversation space is better" in source
    assert "↓ a smaller index is better" in source


# ---------------------------------------------------------------------------
# The gates, and that they can fail.
# ---------------------------------------------------------------------------


def test_the_contrast_auditor_passes_on_the_shipped_page():
    result = _run(CONTRAST, str(GUI))
    assert result.returncode == 0, result.stdout


def test_the_contrast_auditor_checks_both_schemes():
    result = _run(CONTRAST, str(GUI), "--report")
    assert "light" in result.stdout and "dark" in result.stdout
    assert result.stdout.count(":1") >= 20, "too few pairs to be a real audit"


def test_the_contrast_auditor_can_fail(tmp_path):
    """It found four real failures on first run; it must still be able to."""
    page = tmp_path / "bad.html"
    page.write_text(
        ":root { --blue: #AAD4FF; --green: #CFF5D6; --orange: #FFE0B2;\n"
        "--red: #FFC9C6; --purple: #E6CCF5; --gray: #DDD;\n"
        "--bg: #FFFFFF; --surface: #FFFFFF; --raised: #FFFFFF;\n"
        "--label: #BBBBBB; --label-2: #CCCCCC; --label-3: #DDDDDD;\n"
        "--separator: #FEFEFE; }\n",
        encoding="utf-8",
    )
    result = _run(CONTRAST, str(page))
    assert result.returncode == 1
    assert "FAILURES" in result.stdout


@pytest.mark.parametrize(
    "ratio_case",
    [("#000000", "#FFFFFF", 21.0), ("#FFFFFF", "#FFFFFF", 1.0), ("#777777", "#FFFFFF", 4.48)],
)
def test_the_contrast_maths_is_right(ratio_case):
    """Against known WCAG values, so a refactor cannot quietly change them."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from audit_contrast import ratio

    fg, bg, expected = ratio_case
    assert ratio(fg, bg) == pytest.approx(expected, abs=0.02)


def test_the_a11y_linter_passes_on_the_shipped_page():
    result = _run(A11Y, str(GUI))
    assert result.returncode == 0, result.stdout


def test_the_a11y_linter_can_fail(tmp_path):
    """A linter that cannot fail produces a green tick and a false sense."""
    page = tmp_path / "bad.html"
    page.write_text(
        "<!doctype html><html><head><title></title>"
        "<style>.x{outline:none}@keyframes s{to{opacity:0}}</style></head><body>"
        "<h1>A</h1><h4>B</h4><img src=x><input type=text id=o><button></button>"
        '<div onclick="g()">c</div><a href="#" tabindex="3">x</a>'
        '<p aria-describedby="nowhere">t</p><dialog><p>u</p></dialog>'
        "</body></html>",
        encoding="utf-8",
    )
    result = _run(A11Y, str(page))
    assert result.returncode == 1
    for rule in (
        "A11Y001",
        "A11Y002",
        "A11Y003",
        "A11Y005",
        "A11Y008",
        "A11Y011",
        "A11Y012",
        "A11Y013",
    ):
        assert rule in result.stdout, f"{rule} did not fire on a page that violates it"


def test_the_a11y_linter_states_its_own_limits():
    """A static gate presented as complete is a gate that stops a real audit."""
    source = A11Y.read_text(encoding="utf-8")
    assert "Static only" in source
    assert "axe-core" in source and "Lighthouse" in source
