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


def test_the_page_is_hand_written_and_its_colour_lives_in_tokens():
    """No framework, no raw hex, and both colour schemes defined.

    The first is the same argument as the external request above: a page with
    no build step that imports a framework imports it from a CDN. The second
    is maintenance -- colour in tokens means a palette change is one edit and
    not forty, and it is what makes the contrast audit below able to check the
    palette rather than the markup. The third is that an explicit choice has
    to win over the system preference, so both selectors must exist.
    """
    source = GUI.read_text(encoding="utf-8")

    lowered = source.lower()
    for framework in ("react", "vue.js", "svelte", "angular", "solid-js"):
        assert framework not in lowered

    body = source[source.index("</style>") :]
    leaked = re.findall(r"#[0-9A-Fa-f]{6}\b", body)
    assert not leaked, f"raw hex outside the token block: {leaked}"

    assert "prefers-color-scheme: dark" in source
    assert '[data-color-scheme="dark"]' in source, "an explicit choice must win too"


def test_the_api_key_is_never_persisted():
    """A dashboard is not a place to store a credential.

    This used to ban browser storage outright, which was the right shape while
    the page stored nothing. The theme and language toggles each have to
    remember a choice, so the blanket ban would have to be deleted to let them
    through -- and a gate
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
        assert "KEY" not in args.replace("THEME_STORE", "").replace("LANG_STORE", ""), (
            f"localStorage.{method}({args}) may be reached by the API key"
        )
        named = re.match(
            r'\s*(?:"ai-bunker-(?:theme|lang)"|THEME_STORE|LANG_STORE)\s*(?:,|$)', args
        )
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


def test_the_theme_toggle_follows_the_system_until_the_reader_says_otherwise():
    """Same rule as the language toggle and for the same reason: the reader of
    this page is the operator looking at their own screen, so their browser
    wins -- the inverse of what an agent is told, where the deployment
    decides.

    Nothing stored means nothing stamped, so the CSS media query decides and
    the page keeps following the system if it flips mid-session. Stamping
    unconditionally -- the obvious version -- would freeze it at load.

    The control is a real `<button>`, which is the whole reason to spend an
    element on it: focusable and Enter-activated for free. Its label names the
    *destination*, because "light" is ambiguous about whether that is the
    current scheme or the one it switches to, and it comes from the same
    catalogue as everything else rather than a second copy of two strings --
    which is how a page ends up half translated.
    """
    page = GUI.read_text(encoding="utf-8")

    assert 'id="theme-toggle"' in page
    assert "\U0001f31e" in page and "\\u{1F31B}" in page, "both glyphs must appear"
    assert "theme.to_dark" in page and "theme.to_light" in page

    head = page[: page.index("</head>")]
    assert "localStorage.getItem" in head, "the stored choice must win before first paint"
    assert re.search(r'if\s*\(\s*stored === "dark" \|\| stored === "light"\s*\)', head), (
        "the attribute is stamped unconditionally, freezing the system preference"
    )
    assert 'matchMedia("(prefers-color-scheme: dark)").addEventListener' in page

    button = re.search(r"<button[^>]*id=\"theme-toggle\"[^>]*>", page, re.S)
    assert button, "the toggle is not a <button>"
    assert 'type="button"' in button.group(0)
    assert "aria-label=" in button.group(0), "an emoji alone is not an accessible name"
    assert "aria-pressed=" in button.group(0), "a toggle must report its state"

    for locale in ("en", "fr"):
        assert "theme.to_dark" in _catalogue(locale)
    assert _catalogue("fr")["theme.to_dark"] != _catalogue("en")["theme.to_dark"]


# ---------------------------------------------------------------------------
# The language toggle.
# ---------------------------------------------------------------------------


def test_the_language_toggle_exists_with_both_flags():
    page = _page()
    assert 'id="lang-toggle"' in page
    assert "\\u{1F1EC}\\u{1F1E7}" in page and "\\u{1F1EB}\\u{1F1F7}" in page


def test_the_switcher_is_labelled_in_the_language_it_offers():
    """The one entry that is deliberately not a translation of its twin. A
    button reading "Switch to French" is useless to the only person who needs
    it: someone who does not read English. So each catalogue carries the
    *other* language's invitation."""
    assert _catalogue("en")["lang.switch"] == "Passer au français"
    assert _catalogue("fr")["lang.switch"] == "Switch to English"


def test_the_switcher_declares_the_language_of_its_own_label():
    """Since the label is in the other language, `lang` on the button has to be
    the other language too, or a screen reader pronounces French with an
    English voice."""
    page = _page()
    assert 'const other = LOCALE === "fr" ? "en" : "fr"' in page
    assert 'button.setAttribute("lang", other)' in page


def test_the_reader_outranks_the_deployment_on_this_page():
    """D132, inverted here and on purpose. For an agent the deployment decides
    the language, because instruction-following is not uniformly strong across
    languages and that is not a per-request choice. For this page the reader is
    the operator looking at their own screen, so the order runs the other way:
    an explicit `?lang=`, then a stored click, then the browser."""
    page = _page()
    line = next(ln for ln in page.splitlines() if "const wanted = asked ||" in ln)
    assert "storedLang()" in line
    assert line.index("storedLang()") < line.index("navigator.language")
    explicit = next(ln for ln in page.splitlines() if "const asked = explicit" in ln)
    assert "explicit ||" in explicit


def test_switching_language_redraws_the_same_tiles_as_the_first_paint():
    """A toggle that refreshed a different set of tiles than boot would leave
    two languages on screen at once, so both go through one `redraw()`."""
    page = _page()
    assert "async function redraw()" in page
    assert page.count("await redraw()") >= 1
    start = page.index("async function redraw()")
    # To the closing brace in column zero, not the first `}` -- that one is the
    # end of an arrow function inside the call.
    body = page[start : page.index("\n}", start)]
    for loader in ("loadHealth", "loadBudget", "loadCharter", "loadLog"):
        assert loader in body, f"{loader} is not redrawn"


def test_the_click_keeps_the_address_bar_honest():
    """`?lang=` outranks a stored choice, so a page opened with one would
    appear to ignore the click unless it is rewritten too."""
    page = _page()
    assert 'url.searchParams.has("lang")' in page
    assert "history.replaceState" in page


# ---------------------------------------------------------------------------
# The gates, and that they can fail.
# ---------------------------------------------------------------------------


def test_the_contrast_auditor_passes_on_the_shipped_page_and_audits_both_schemes():
    """The pass is only worth something if the audit is real, so the same run
    has to show it covered both colour schemes and enough pairs to mean
    anything -- a gate that checks three pairs in one scheme would go green on
    a page nobody can read in the other."""
    assert _run(CONTRAST, str(GUI)).returncode == 0

    report = _run(CONTRAST, str(GUI), "--report").stdout
    assert "light" in report and "dark" in report
    assert report.count(":1") >= 20, "too few pairs to be a real audit"


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
