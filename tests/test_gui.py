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

import re
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

    This used to ban browser storage outright, which was the right shape while
    the page stored nothing. The theme toggle has to remember a choice, so the
    blanket ban would now have to be deleted to let it through -- and a gate
    deleted to unblock a feature stops guarding the thing it was written for.
    So it is narrowed instead of dropped: storage is allowed, but only under a
    named key, and the credential may never reach it. That is the property the
    original test was reaching for, and it is strictly harder to violate by
    accident than the substring ban was.

    Matches a *call*, not a mention: the page explains in prose why the key is
    kept out of storage, and a naive substring search flags that explanation
    as the very thing it rules out.
    """
    import re

    source = GUI.read_text(encoding="utf-8")

    for api in ("sessionStorage", "document.cookie"):
        assert not re.search(rf"\b{api}\s*[.\[]", source), f"{api} is used"

    calls = re.findall(r"localStorage\.(getItem|setItem|removeItem)\(([^)]*)\)", source)
    assert calls, "the theme preference is no longer persisted"
    for method, args in calls:
        assert "KEY" not in args.replace("THEME_STORE", ""), (
            f"localStorage.{method}({args}) may be reached by the API key"
        )
        named = re.match(r'\s*(?:"ai-bunker-theme"|THEME_STORE)\s*(?:,|$)', args)
        assert named, f"storage under an unexpected key: localStorage.{method}({args})"

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
# The theme toggle.
#
# Same rule as the language (D132) and for the same reason: the reader of this
# page is the operator looking at their own screen, so their browser wins --
# the inverse of what an agent is told, where the deployment decides.
# ---------------------------------------------------------------------------


def test_the_toggle_exists_and_names_where_it_goes():
    page = GUI.read_text(encoding="utf-8")
    assert 'id="theme-toggle"' in page
    assert "\U0001f31e" in page and "\\u{1F31B}" in page, "both glyphs must appear"
    # A button labelled "light" is ambiguous about whether that is the current
    # scheme or the one it switches to; the label names the destination.
    assert "theme.to_dark" in page and "theme.to_light" in page


def test_the_system_preference_is_the_default():
    """Nothing stored means nothing stamped, so the CSS media query decides --
    and the page keeps following the system if it flips mid-session. Stamping
    unconditionally, the obvious version, would freeze it at load."""
    page = GUI.read_text(encoding="utf-8")
    head = page[: page.index("</head>")]
    assert "localStorage.getItem" in head, "the stored choice must win before first paint"
    guard = re.search(r'if\s*\(\s*stored === "dark" \|\| stored === "light"\s*\)', head)
    assert guard, "the attribute is stamped unconditionally, freezing the system preference"
    assert 'matchMedia("(prefers-color-scheme: dark)").addEventListener' in page


def test_the_toggle_is_reachable_without_a_mouse():
    """It is a real button, not a clickable div: focusable and Enter-activated
    for free, which is the whole reason to spend an element on it."""
    page = GUI.read_text(encoding="utf-8")
    button = re.search(r"<button[^>]*id=\"theme-toggle\"[^>]*>", page, re.S)
    assert button, "the toggle is not a <button>"
    assert 'type="button"' in button.group(0), (
        "an untyped button in no form still submits nothing, but say so"
    )
    assert "aria-label=" in button.group(0), "an emoji alone is not an accessible name"
    assert "aria-pressed=" in button.group(0), "a toggle must report its state"


def test_the_toggle_reads_the_same_catalogue_as_the_rest():
    """Not a second copy of two strings, which is how a page ends up half
    translated."""
    for locale in ("en", "fr"):
        catalogue = _catalogue(locale)
        assert "theme.to_dark" in catalogue
        assert "theme.to_light" in catalogue
    assert _catalogue("fr")["theme.to_dark"] != _catalogue("en")["theme.to_dark"]


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


# ---------------------------------------------------------------------------
# The dashboard's words come from the same catalogue as everything else.
# ---------------------------------------------------------------------------


def _page() -> str:
    return GUI.read_text(encoding="utf-8")


def _marked_keys() -> set[str]:
    """Every `data-i18n` on the page."""
    return set(re.findall(r'data-i18n="([^"]+)"', _page()))


def _called_keys() -> set[str]:
    """Every key the script asks `t()` for.

    Scans the argument list of each `t(` call rather than matching the first
    literal after it, because two shapes in this page defeat the simpler
    pattern: a computed key, `t(cond ? "a" : "b")`, hides both literals behind
    a ternary, and a plain substring match for `t(` also finds the tail of
    `createElement(` and reports `div` as a missing translation.
    """
    page = _page()
    keys: set[str] = set()
    for match in re.finditer(r"(?<![\w.$])t\(", page):
        depth, i = 0, match.end() - 1
        while i < len(page):
            if page[i] == "(":
                depth += 1
            elif page[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        keys |= set(re.findall(r'"([a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+)"', page[match.end() : i]))
    return keys


def _catalogue(locale: str) -> dict[str, str]:
    from ai_bunker.i18n import _load

    return {
        key.removeprefix("gui."): value
        for key, value in _load(locale).items()
        if key.startswith("gui.")
    }


@pytest.mark.parametrize("locale", ["en", "fr"])
def test_every_key_the_page_uses_exists(locale):
    """A missing key renders as `stat.floor` on somebody's screen."""
    known = set(_catalogue(locale))
    unknown = (_marked_keys() | _called_keys()) - known
    assert unknown == set(), f"{locale} catalogue has no: {sorted(unknown)}"


def test_every_key_in_the_catalogue_is_used():
    """The other direction, which is how a catalogue starts describing a page
    that no longer exists: a string nobody shows and a label nobody translated
    are the same bug seen from two sides."""
    unused = set(_catalogue("en")) - _marked_keys() - _called_keys()
    assert unused == set(), f"nothing on the page uses: {sorted(unused)}"


def test_the_english_is_still_written_into_the_markup():
    """The fallback, and the reason it is a fallback: if the catalogue fetch
    fails the page is still readable, rather than a grid of empty boxes."""
    page = _page()
    for key, fragment in (
        ("budget.heading", "How much room does a session actually have?"),
        ("column.owner", ">Owner<"),
        ("log.caption", "Decision log"),
    ):
        assert f'data-i18n="{key}"' in page
        assert fragment in page


def test_numbers_are_formatted_in_the_chosen_locale():
    """`toLocaleString("en-US")` shows a French operator "24,521" and means
    twenty-four thousand. That reads as a decimal, and it is the oldest
    mistake in the trade."""
    page = _page()
    assert 'toLocaleString("en-US")' not in page
    assert "toLocaleString(LOCALE)" in page


def test_the_page_fetches_its_words_from_the_gateway():
    """Rather than carrying a second copy of them. One catalogue backs both the
    dashboard and what an agent is told."""
    page = _page()
    assert "/gui/i18n" in page
    assert "loadMessages" in page


def test_the_catalogue_endpoint_serves_only_the_dashboard_keys():
    """The rest of the catalogue is what the gateway says to agents, and a
    browser has no business being shipped it."""
    from fastapi.testclient import TestClient

    from ai_bunker.config import Settings
    from ai_bunker.gateway import create_app

    client = TestClient(create_app(Settings(charter_dir="charter", rules_dir="charter/rules")))
    body = client.get("/gui/i18n").json()
    assert body["locale"] == "en"
    assert body["messages"], "no messages served"
    assert not any(k.startswith(("rules.", "deps.", "breaker.")) for k in body["messages"])


def test_the_dashboard_locale_can_be_overridden_per_reader():
    """The opposite of the agent-facing rule, deliberately: the reader here is
    the operator in their own browser, so their choice wins."""
    from fastapi.testclient import TestClient

    from ai_bunker.config import Settings
    from ai_bunker.gateway import create_app

    client = TestClient(
        create_app(Settings(charter_dir="charter", rules_dir="charter/rules", language="en"))
    )
    assert client.get("/gui/i18n?locale=fr").json()["locale"] == "fr"
    assert "lang" in _page(), "the page never reads a ?lang= override"


def test_the_catalogue_endpoint_needs_no_key():
    """Like the page that fetches it: gating a list of column headings would
    leave an operator staring at `gui.stat.floor` until they pasted a key."""
    from fastapi.testclient import TestClient

    from ai_bunker.config import Settings
    from ai_bunker.gateway import create_app

    client = TestClient(
        create_app(Settings(api_key="secret", charter_dir="charter", rules_dir="charter/rules"))
    )
    assert client.get("/gui/i18n").status_code == 200
