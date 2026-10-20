"""
Tests for the abbreviation rule.

The documentation's rule is that no abbreviation is used before the prose has
spelled it out, in that file, in that language. A glossary does not satisfy it:
a list at the bottom of the page explains a term after every sentence that
already used it, and the reader who needed it has long since moved on.

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

from ai_bunker.adopt import ROOT

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


def test_the_check_can_fail(lint, tmp_path):
    """A linter nobody has seen fail is a linter nobody should trust.

    Two probes, because the interesting part is not that a gap is caught but
    that a term explained in the same breath is *not* — the rule compares
    paragraphs, since documentation hard-wrapped at 80 columns splits
    "mixture of experts" across lines all the time, and a per-line rule would
    have had the prose rewritten to please the checker.
    """
    bad = tmp_path / "bad.md"
    bad.write_text("An agent verifies an AP2 mandate before paying.\n", encoding="utf-8")
    good = tmp_path / "good.md"
    good.write_text(
        "An agent verifies an AP2 mandate — the Agent Payments\nProtocol — before paying.\n",
        encoding="utf-8",
    )

    lint.ROOT = tmp_path
    lint.FILES = [("bad.md", "en")]
    assert [g[1] for g in lint.gaps()] == ["AP2"], "a plain gap went unreported"

    lint.FILES = [("good.md", "en")]
    assert lint.gaps() == [], "an expansion split across two lines was called a gap"


def test_the_glossary_page_is_not_the_mechanism():
    """The site keeps a glossary page, which is fine as a destination. What it
    must not become is the answer to this rule: if the only place a term is
    spelled out is that page, every other page is unexplained. The linter
    treats it as one more file, and this says so out loud."""
    spec = importlib.util.spec_from_file_location("lint_acronyms", LINTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checked = {rel for rel, _ in module.FILES}
    assert "web/glossary.html" in checked
    assert "web/fr/glossary.html" in checked
    # And the pages that do not link to it are held to the same rule.
    assert "README.md" in checked and "LISEZMOI.md" in checked
