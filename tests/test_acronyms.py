"""
Tests for the abbreviation rule.

The documentation's rule is that no abbreviation is used before the prose has
spelled it out, in that file, in that language. A glossary does not satisfy it,
which is why the project does not ship one: a list at the bottom of the page --
or on a page of its own -- explains a term after every sentence that already
used it, and the reader who needed it has long since moved on.

A rule nobody checks is a style preference. `scripts/lint_acronyms.py` is the
check; these are the tests that it works and that the documentation passes it.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys

import pytest

from ai_bunker.adopt import ROOT, site_root

#: Interpreter-independent: the abbreviation catalogue is a parse of committed prose.
#: See `markers` in pyproject.toml — this module runs once, on the newest.
pytestmark = pytest.mark.gate

LINTER = ROOT / "scripts" / "lint_acronyms.py"


@pytest.fixture(scope="module")
def lint():
    spec = importlib.util.spec_from_file_location("lint_acronyms", LINTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_abbreviation_is_used_before_it_is_explained():
    """The whole point, run the way a contributor runs it."""
    result = subprocess.run(
        [sys.executable, str(LINTER)], capture_output=True, text=True, cwd=ROOT, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_catalogue_knows_every_abbreviation_the_prose_uses(lint):
    """The weak point of a catalogue is the term nobody thought to add, which
    is then silently allowed. The linter scans the other way too; this asserts
    that scan finds nothing, so a new abbreviation cannot arrive unnoticed."""
    strange = lint.unknown()
    assert strange == [], f"uncatalogued: {sorted({t for _, t, _ in strange})}"


def test_every_french_file_has_french_spellings(lint):
    """A term explained in English is not explained for a French reader. Every
    term used by a French file must therefore carry a French spelling."""
    missing = []
    for rel, lang in lint.FILES:
        if lang != "fr":
            continue
        path = ROOT / rel
        if not path.exists():
            continue
        prose = lint.Prose(path)
        for term, by_lang in lint.TERMS.items():
            if lint.first_use(prose, term) and not by_lang.get("fr"):
                missing.append((rel, term))
    assert missing == [], f"used in French with no French spelling: {missing}"


def test_the_check_can_fail(lint, tmp_path, monkeypatch):
    """A linter nobody has seen fail is a linter nobody should trust.

    Two probes, because the interesting part is not that a gap is caught but
    that a term explained in the same breath is *not* — the rule compares
    paragraphs, since documentation hard-wrapped at 80 columns splits
    "mixture of experts" across lines all the time, and a per-line rule would
    have had the prose rewritten to please the checker.

    Both probes go through ``monkeypatch`` so the redirection is undone: the
    fixture is module-scoped, and leaving it aimed at a temporary directory
    made the tests after this one inspect the probe rather than the repository.
    """
    bad = tmp_path / "bad.md"
    bad.write_text("An agent verifies an AP2 mandate before paying.\n", encoding="utf-8")
    good = tmp_path / "good.md"
    good.write_text(
        "An agent verifies an AP2 mandate — the Agent Payments\nProtocol — before paying.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(lint, "ROOT", tmp_path)
    monkeypatch.setattr(lint, "FILES", [("bad.md", "en")])
    assert [g[1] for g in lint.gaps()] == ["AP2"], "a plain gap went unreported"

    monkeypatch.setattr(lint, "FILES", [("good.md", "en")])
    assert lint.gaps() == [], "an expansion split across two lines was called a gap"


def test_every_assembled_page_is_checked(lint):
    """The list of checked files is hand-written, which is the hole: a page
    added later and never listed is a page exempt from the rule, and nothing
    would say so. This closes it."""
    web = site_root()
    if web is None:
        pytest.skip("the site is not on this machine (set AI_BUNKER_SITE)")
    # `FILES` names the site's pages as `web/...`, the spelling they had when
    # the site lived in this repository and the one it still uses internally.
    pages = {
        f"web/{p.relative_to(web).as_posix()}"
        for p in sorted(web.glob("*.html")) + sorted((web / "fr").glob("*.html"))
    }
    unchecked = pages - {rel for rel, _ in lint.FILES}
    assert unchecked == set(), f"pages nobody checks: {sorted(unchecked)}"


def test_both_readmes_are_checked(lint):
    """The two files a newcomer reads first, and the ones a glossary used to
    cover. There is no glossary now -- the explanations are in place, at first
    use -- so these two must be in the list or the rule means nothing."""
    checked = {rel for rel, _ in lint.FILES}
    assert "README.md" in checked and "LISEZMOI.md" in checked
