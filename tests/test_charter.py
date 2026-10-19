"""
Tests for the charter.

The charter's whole claim is arithmetic: an index costs a fraction of what the
pages would cost, and a page costs nothing until it is opened. These tests hold
that claim to its numbers, and hold the index's wording to the four things it
has to say -- because an index that merely lists files produces a charter
nobody reads.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import os_helper as osh
import pytest

from ai_bunker.budget import Counter
from ai_bunker.charter import (
    MAX_INDEX_CHARS,
    MAX_PAGE_CHARS,
    PACKS_DIR,
    build_index,
    load_charter,
    read_page,
    system_blocks,
)

#: The charter ships with the repository, so the shipped one is under test.
SHIPPED = "charter"


@pytest.fixture(autouse=True)
def quiet():
    previous = osh.verbosity()
    osh.verbosity(-1)
    yield
    osh.verbosity(previous)


@pytest.fixture(scope="module")
def shipped():
    return load_charter(SHIPPED)


def _charter(
    tmp_path, packs: dict[str, dict[str, str]], rules: str = "# How to work\nRead in slices.\n"
):
    """Build a charter on disk from a {pack: {page: text}} description."""
    (tmp_path / "AGENTS.md").write_text(rules, encoding="utf-8")
    for pack, pages in packs.items():
        d = tmp_path / PACKS_DIR / pack
        d.mkdir(parents=True, exist_ok=True)
        for name, text in pages.items():
            (d / name).write_text(text, encoding="utf-8")
    return load_charter(tmp_path)


# ---------------------------------------------------------------------------
# The claim: index, not concatenation.
# ---------------------------------------------------------------------------


def test_the_index_costs_a_fraction_of_the_pages(tmp_path):
    """The number that justifies the whole design.

    Measured on the deployment this was built for: concatenating 37 pages would
    have cost roughly 18,000 tokens -- the entire declared window -- while the
    index came to a few hundred.
    """
    packs = {
        f"pack{p}": {f"page{i}.md": f"# Page {i}\n" + ("standard text. " * 300) for i in range(6)}
        for p in range(6)
    }
    charter = _charter(tmp_path, packs)
    assert len(charter.pages) == 36

    counter = Counter(allow_ratio=True)
    index_cost = counter.count(build_index(charter))
    concatenated = counter.count(
        "\n".join(p.path.read_text(encoding="utf-8") for p in charter.pages)
    )
    assert index_cost < concatenated / 20, (
        f"index {index_cost} vs concatenation {concatenated}: the index must be "
        "an order of magnitude cheaper or the design has no point"
    )


def test_the_index_is_capped_rather_than_allowed_to_grow(tmp_path):
    """An index that costs what the pages cost has reinvented concatenation."""
    packs = {
        f"pack{p}": {f"a_rather_long_page_name_{i}.md": "x" for i in range(40)} for p in range(10)
    }
    charter = _charter(tmp_path, packs)
    index = build_index(charter)
    assert len(charter.pages) == 400
    assert len(index) < MAX_INDEX_CHARS * 2, "the cap did not engage"
    assert "pages)" in index, "it should degrade to counts, not truncate mid-list"
    assert f"ls {PACKS_DIR}/" in index, "and say how to list one"


def test_the_shipped_index_stays_within_its_budget(shipped):
    index = build_index(shipped)
    assert 0 < len(index) <= MAX_INDEX_CHARS + 600  # prose header plus the listing
    counter = Counter(allow_ratio=True)
    assert counter.count(index) < 400, "the index is paid on every single request"


def test_a_page_costs_nothing_until_it_is_opened(shipped):
    """Nothing in the system blocks should contain a page's body."""
    blocks = "\n".join(system_blocks(shipped))
    for page in shipped.pages:
        body = page.path.read_text(encoding="utf-8")
        distinctive = body.strip().splitlines()[-1][:40]
        if len(distinctive) > 20:
            assert distinctive not in blocks, f"{page.ref} leaked into the prompt"


# ---------------------------------------------------------------------------
# The index's wording is load-bearing.
# ---------------------------------------------------------------------------


def test_the_index_says_the_pages_are_not_in_the_prompt(shipped):
    """Otherwise a model asked about naming answers from habit, not the page."""
    index = build_index(shipped).lower()
    assert "not loaded into this prompt" in index


def test_the_index_says_when_to_open_a_page(shipped):
    """ "Available if needed" is not an instruction a model acts on."""
    index = build_index(shipped).lower()
    assert "before writing or reviewing code" in index
    assert "wins over your habits" in index


def test_the_index_says_one_page_at_a_time(shipped):
    """An agent told to consult the charter will otherwise read the whole pack."""
    index = build_index(shipped).lower()
    assert "one page at a time" in index
    assert "never a whole pack" in index


def test_the_index_shows_a_concrete_example(shipped):
    index = build_index(shipped)
    assert f"Example: read {PACKS_DIR}/" in index


def test_the_index_lists_every_pack_and_page(shipped):
    index = build_index(shipped)
    for pack, pages in shipped.packs.items():
        assert pack in index
        for page in pages:
            assert page.name in index


def test_nested_packs_keep_their_path(tmp_path):
    """A charter stays navigable past a handful of pages only if packs nest."""
    charter = _charter(tmp_path, {"javascript": {}})
    deep = tmp_path / PACKS_DIR / "javascript" / "react"
    deep.mkdir(parents=True)
    (deep / "20_patterns.md").write_text("# React\n", encoding="utf-8")
    charter = load_charter(tmp_path)
    assert [p.ref for p in charter.pages] == ["javascript/react/20_patterns.md"]
    assert "react/20_patterns.md" in build_index(charter)


# ---------------------------------------------------------------------------
# Serving a page.
# ---------------------------------------------------------------------------


def test_a_page_is_served_by_its_index_reference(shipped):
    ref = shipped.pages[0].ref
    assert read_page(shipped, ref) == shipped.pages[0].path.read_text(encoding="utf-8")


def test_a_reference_works_with_or_without_the_packs_prefix(shipped):
    """The index shows `packs/python/tests.md`; a model may send either half."""
    ref = shipped.pages[0].ref
    assert read_page(shipped, f"{PACKS_DIR}/{ref}") == read_page(shipped, ref)
    assert read_page(shipped, f"/{PACKS_DIR}/{ref}") == read_page(shipped, ref)


def test_a_near_miss_is_answered_with_the_real_names(shipped):
    """The realistic failure is a wrong filename; the fix is seeing the right one."""
    with pytest.raises(AssertionError) as caught:
        read_page(shipped, "python/style.md")
    message = str(caught.value)
    assert "no page" in message
    assert "10_style.md" in message, "it must list the pack's actual pages"


def test_an_unknown_pack_is_answered_with_the_pack_list(shipped):
    with pytest.raises(AssertionError) as caught:
        read_page(shipped, "cobol/style.md")
    assert "Known packs" in str(caught.value)


def test_reading_a_page_cannot_escape_the_charter(shipped):
    """A reference is matched against the index, never resolved as a path."""
    for attempt in ("../../etc/passwd", "python/../../../etc/passwd", "/etc/passwd"):
        with pytest.raises(AssertionError):
            read_page(shipped, attempt)


# ---------------------------------------------------------------------------
# Loading, and what it refuses to do silently.
# ---------------------------------------------------------------------------


def test_a_missing_charter_is_a_choice_not_an_error(tmp_path):
    charter = load_charter(tmp_path / "absent")
    assert charter.pages == []
    assert build_index(charter) == ""
    assert system_blocks(charter) == []
    assert charter.warnings


def test_missing_operating_rules_are_reported(tmp_path):
    """An index with no instruction to consult it is a charter nobody reads."""
    (tmp_path / PACKS_DIR / "default").mkdir(parents=True)
    (tmp_path / PACKS_DIR / "default" / "a.md").write_text("# A\n", encoding="utf-8")
    charter = load_charter(tmp_path)
    assert charter.operating_rules == ""
    assert any("AGENTS.md is missing" in w for w in charter.warnings)


def test_an_oversized_page_is_reported_but_still_served(tmp_path):
    """Past the budget an agent reads the beginning and guesses the rest."""
    charter = _charter(tmp_path, {"default": {"huge.md": "x" * (MAX_PAGE_CHARS + 1)}})
    assert any("over the" in w and "page budget" in w for w in charter.warnings)
    assert read_page(charter, "default/huge.md")


def test_a_page_with_no_pack_is_reported_and_skipped(tmp_path):
    """The index groups by pack, so a page outside one has nowhere to go."""
    (tmp_path / "AGENTS.md").write_text("# rules\n", encoding="utf-8")
    (tmp_path / PACKS_DIR).mkdir(parents=True)
    (tmp_path / PACKS_DIR / "orphan.md").write_text("# Orphan\n", encoding="utf-8")
    charter = load_charter(tmp_path)
    assert charter.pages == []
    assert any("no pack" in w for w in charter.warnings)


def test_packs_and_pages_are_ordered_deterministically(tmp_path):
    """Two deployments reading the same directory must build the same index."""
    packs = {"zebra": {"b.md": "x", "a.md": "x"}, "alpha": {"c.md": "x"}}
    charter = _charter(tmp_path, packs)
    assert list(charter.packs) == ["alpha", "zebra"]
    assert [p.name for p in charter.packs["zebra"]] == ["a.md", "b.md"]
    assert build_index(charter) == build_index(load_charter(tmp_path))


# ---------------------------------------------------------------------------
# Provenance.
# ---------------------------------------------------------------------------


def test_the_fingerprint_changes_with_content(tmp_path):
    """Provenance: a session can record which charter it actually ran under."""
    charter = _charter(tmp_path, {"default": {"a.md": "original"}})
    before = charter.fingerprint
    (tmp_path / PACKS_DIR / "default" / "a.md").write_text("changed", encoding="utf-8")
    assert load_charter(tmp_path).fingerprint != before


def test_the_fingerprint_is_stable_for_unchanged_content(tmp_path):
    """Also a cache key: an unchanged prompt re-serves from the prefix cache."""
    charter = _charter(tmp_path, {"default": {"a.md": "text", "b.md": "more"}})
    assert charter.fingerprint == load_charter(tmp_path).fingerprint


def test_the_fingerprint_covers_the_operating_rules(tmp_path):
    charter = _charter(tmp_path, {"default": {"a.md": "x"}}, rules="# One\n")
    before = charter.fingerprint
    (tmp_path / "AGENTS.md").write_text("# Two\n", encoding="utf-8")
    assert load_charter(tmp_path).fingerprint != before


# ---------------------------------------------------------------------------
# The shipped charter is itself a deliverable.
# ---------------------------------------------------------------------------


def test_the_shipped_charter_is_complete(shipped):
    assert shipped.operating_rules, "the shipped charter must carry its rules"
    assert len(shipped.pages) >= 5
    assert "default" in shipped.packs
    assert not [w for w in shipped.warnings if "missing" in w or "no pack" in w]


def test_the_shipped_operating_rules_say_how_to_read(shipped):
    """They are injected on every request, so they must earn the space."""
    text = shipped.operating_rules.lower()
    assert "slices" in text
    assert "truncated" in text, "an agent must know a cut output is not an error"
    assert "decision, not a transient failure" in text, "nor a refusal"


def test_our_own_contribution_is_small(shipped):
    """The published claim: the charter's floor cost is a few percent."""
    counter = Counter(allow_ratio=True)
    cost = sum(counter.count(b) for b in system_blocks(shipped))
    assert cost < 0.05 * 26_000, f"{cost} tokens is more than 5% of a 26k window"
