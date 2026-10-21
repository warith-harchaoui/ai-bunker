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

from ai_bunker import i18n
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
    tmp_path,
    packs: dict[str, dict[str, str]],
    rules: str = "# How to work\nRead in slices.\n",
    locale: str = i18n.DEFAULT_LOCALE,
):
    """Build a charter on disk from a {pack: {page: text}} description."""
    (tmp_path / "AGENTS.md").write_text(rules, encoding="utf-8")
    for pack, pages in packs.items():
        d = tmp_path / PACKS_DIR / pack
        d.mkdir(parents=True, exist_ok=True)
        for name, text in pages.items():
            (d / name).write_text(text, encoding="utf-8")
    return load_charter(tmp_path, locale=locale)


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


def test_one_large_pack_costs_its_own_names_not_everyone_elses(tmp_path):
    """Found by importing a 77-page pack into the shipped charter.

    The cap used to degrade the body as a whole, so one big pack turned
    `python: 10_style.md, tests.md` into `python (2 pages)` -- spending the
    agent's knowledge of two page names to save the forty-five characters
    that named them. The degradation is per pack now, biggest first.
    """
    packs = {
        "python": {"10_style.md": "x", "tests.md": "x"},
        "default": {"00_principles.md": "x"},
        "big": {f"a_rather_long_page_name_{i}.md": "x" for i in range(80)},
    }
    index = build_index(_charter(tmp_path, packs))

    assert "- big (80 pages)" in index, "the pack that overflowed must collapse"
    assert "10_style.md" in index, "a two-page pack must keep its names"
    assert "tests.md" in index
    assert "00_principles.md" in index
    assert f"ls {PACKS_DIR}/" in index, "and it must say how to list the collapsed one"


@pytest.mark.parametrize("locale", i18n.available())
def test_a_single_page_pack_is_not_described_as_1_pages(tmp_path, locale):
    """A plural that only shows up once a pack collapses -- and it has to
    survive translation, so every catalogue is measured, not just English."""
    packs = {
        "solo": {"only.md": "x"},
        "big": {f"a_rather_long_page_name_{i}.md": "x" for i in range(200)},
    }
    index = build_index(_charter(tmp_path, packs, locale=locale))
    assert "(1 pages)" not in index
    assert "(200 page)" not in index
    if "solo (" in index:
        assert "solo (1 page)" in index


@pytest.mark.parametrize("locale", i18n.available())
def test_the_shipped_index_stays_within_its_budget(locale):
    """Measured in every locale, not only the one the constant was tuned in.

    `MAX_INDEX_CHARS` bounds `render()`, which is the pack listing -- file
    names, which no translation touches. The prose scaffolding sits *outside*
    that bound, which is why the assertion below carries a `+ 600` and why it
    has to run per locale: translating the scaffolding is the one change that
    can grow the part nothing caps. French is ~16% longer than English here,
    and this block is paid on every single request.
    """
    index = build_index(load_charter(SHIPPED, locale=locale))
    assert 0 < len(index) <= MAX_INDEX_CHARS + 600  # prose header plus the listing
    counter = Counter(allow_ratio=True)
    assert counter.count(index) < 400, "the index is paid on every single request"


# ---------------------------------------------------------------------------
# The index is agent-facing text, so it is translated like the rest of it.
# ---------------------------------------------------------------------------


def test_the_index_is_rendered_in_the_charters_locale():
    """`locale` circulated as far as refusals and stopped there, so the block
    paid on *every* request went out in English whatever `language:` said."""
    french = build_index(load_charter(SHIPPED, locale="fr"))
    assert "Les pages vivent sous" in french
    assert "Une seule page à la fois" in french
    assert "Pages live under" not in french

    english = build_index(load_charter(SHIPPED, locale="en"))
    assert "Pages live under" in english
    assert "Les pages vivent sous" not in english


def test_the_english_index_is_byte_identical_to_before_translation():
    """Moving these lines into a catalogue must not reword them.

    A serving engine's prefix cache only helps while the head of the prompt is
    byte-identical between requests, and this block sits in that head. A
    well-meant copy-edit during the move would have invalidated the cache of
    every existing deployment, silently and for nothing.
    """
    index = build_index(load_charter(SHIPPED, locale="en"))
    assert index.splitlines()[0] == "## House standards (the charter)"
    assert index.splitlines()[1] == (
        f"Pages live under `{PACKS_DIR}/`. They are NOT loaded into this prompt: "
        "read the one you need, when you need it, in slices."
    )
    assert index.splitlines()[2] == (
        "Before writing or reviewing code in one of these domains, read the matching "
        "page. The page wins over your habits and over a library's defaults."
    )
    assert index.splitlines()[3] == (
        "One page at a time, for the domain actually in play: never a whole pack, and "
        "no page at all for a question that writes no code."
    )
    assert index.splitlines()[-1].startswith(f"Example: read {PACKS_DIR}/")


def test_the_default_index_is_still_english():
    """A charter loaded without a locale is English, like every other
    agent-facing string: a deployment opts in."""
    assert build_index(load_charter(SHIPPED)) == build_index(load_charter(SHIPPED, locale="en"))


def test_the_fingerprint_covers_the_locale():
    """Two deployments of the same files that serve prompts differing in bytes
    must not report the same fingerprint.

    It is a cache key and it is provenance, and the lie is worse in the second
    role: a decision record naming charter `9f2c` has to mean one prompt. The
    English digest is the one that must stay put relative to its own locale --
    see `test_the_english_index_is_byte_identical_to_before_translation` for
    the bytes it keys.
    """
    english = load_charter(SHIPPED, locale="en")
    french = load_charter(SHIPPED, locale="fr")
    assert build_index(english) != build_index(french), "the premise of this test"
    assert english.fingerprint != french.fingerprint
    assert load_charter(SHIPPED).fingerprint == english.fingerprint


@pytest.mark.parametrize("spelling", ["", "en", "EN", "en-US", "en_GB", "zz"])
def test_every_spelling_that_renders_english_reports_one_fingerprint(spelling):
    """The locale is stored resolved, and this is why.

    Found in this change rather than reasoned about: `language:` defaults to
    an empty string, an unknown locale falls back, and a region tag is
    stripped -- so `""`, `"zz"` and `"en-US"` all serve the byte-identical
    English index. Keeping the raw string gave that one prompt three different
    fingerprints, which is precisely the lie that putting the locale in the
    digest was added to prevent. Same prompt, same fingerprint; the rule has
    to hold in both directions or the digest means nothing.
    """
    english = load_charter(SHIPPED, locale="en")
    charter = load_charter(SHIPPED, locale=spelling)
    assert charter.locale == "en"
    assert build_index(charter) == build_index(english)
    assert charter.fingerprint == english.fingerprint


@pytest.mark.parametrize("spelling", ["fr", "FR", "fr-CA", "fr_FR"])
def test_every_spelling_of_french_reports_one_fingerprint(spelling):
    """And the same in the other direction, so the test above is not just
    asserting that everything collapses to English."""
    french = load_charter(SHIPPED, locale="fr")
    charter = load_charter(SHIPPED, locale=spelling)
    assert charter.locale == "fr"
    assert charter.fingerprint == french.fingerprint
    assert charter.fingerprint != load_charter(SHIPPED, locale="en").fingerprint


def test_a_request_cannot_choose_the_language_an_agent_is_instructed_in():
    """The locale is a property of the loaded charter, and that is the whole
    guarantee: there is no per-request seam to pass one through.

    `negotiate()` reads `Accept-Language` for refusals and notes, and a client
    may legitimately influence those. It must not reach the charter, because
    instruction-following is not uniformly strong across languages and which
    language an agent is instructed in is the operator's call, not a caller's.
    If a later change adds a `locale` parameter to either of these, this test
    is the place that argument gets made.
    """
    import inspect

    for fn in (build_index, system_blocks):
        assert list(inspect.signature(fn).parameters) == ["charter"], (
            f"{fn.__name__} grew a parameter; if it is a locale, see this test's docstring"
        )


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


# ---------------------------------------------------------------------------
# The charter's own pages, per locale. A translation sits beside its original
# and is reached through it, so a page keeps ONE reference in every language.
# ---------------------------------------------------------------------------


def _bilingual(tmp_path):
    """A charter with one translated page, one untranslated, and rules in both."""
    (tmp_path / "AGENTS.md").write_text("# How to work\nRead in slices.\n", encoding="utf-8")
    (tmp_path / "AGENTS.fr.md").write_text(
        "# Comment travailler\nLisez par tranches.\n", encoding="utf-8"
    )
    d = tmp_path / PACKS_DIR / "python"
    d.mkdir(parents=True)
    (d / "10_style.md").write_text("# Python style\nruff decides.\n", encoding="utf-8")
    (d / "10_style.fr.md").write_text("# Style Python\nruff décide.\n", encoding="utf-8")
    (d / "tests.md").write_text("# Python tests\npytest only.\n", encoding="utf-8")
    return tmp_path


def test_one_reference_resolves_in_either_language(tmp_path):
    """The hard point of this feature, and the reason translations are
    siblings rather than a parallel tree.

    `read_page` must answer the same question whatever the charter's locale.
    An index that named `10_style.fr.md` would teach an agent a path that
    resolves in one language only; an index that named both would cost double,
    on the one block paid for on every request.
    """
    root = _bilingual(tmp_path)
    english = read_page(load_charter(root, locale="en"), "python/10_style.md")
    french = read_page(load_charter(root, locale="fr"), "python/10_style.md")

    assert english.startswith("# Python style")
    assert french.startswith("# Style Python")


def test_a_translation_is_not_a_page_of_its_own(tmp_path):
    """Otherwise every translated charter pays twice for the same index."""
    root = _bilingual(tmp_path)
    for locale in ("en", "fr"):
        charter = load_charter(root, locale=locale)
        refs = sorted(p.ref for p in charter.pages)
        assert refs == ["python/10_style.md", "python/tests.md"], locale
        assert ".fr.md" not in build_index(charter)


def test_the_page_list_does_not_change_with_the_locale(tmp_path):
    """What the agent is told *exists* is the same in every language; only the
    file served changes. A charter whose index gained and lost pages with the
    locale would be two different charters wearing one name."""
    root = _bilingual(tmp_path)
    english = load_charter(root, locale="en")
    french = load_charter(root, locale="fr")
    assert [p.ref for p in english.pages] == [p.ref for p in french.pages]


def test_a_page_with_no_translation_falls_back_to_its_original(tmp_path):
    """A partial translation has to stay usable. The alternative -- refusing to
    serve a page that has not been translated yet -- turns an incomplete
    translation into a charter with holes in it."""
    charter = load_charter(_bilingual(tmp_path), locale="fr")
    served = {p.ref: p for p in charter.pages}

    assert served["python/10_style.md"].translated
    assert read_page(charter, "python/10_style.md").startswith("# Style Python")
    assert not served["python/tests.md"].translated
    assert read_page(charter, "python/tests.md").startswith("# Python tests")


def test_a_page_served_in_the_wrong_language_is_reported(tmp_path):
    """The normal failure mode of any translation is falling behind, so the
    operator is told which pages have -- once, with the list, not once per
    page."""
    charter = load_charter(_bilingual(tmp_path), locale="fr")
    behind = [w for w in charter.warnings if "no fr translation" in w]
    assert len(behind) == 1
    assert "python/tests.md" in behind[0]
    assert "10_style" not in behind[0], "the translated page must not be named"


def test_untranslated_operating_rules_are_reported(tmp_path):
    """The rules are the block injected into every request, so them being in
    another language than the rest of the prompt is worth its own warning."""
    (tmp_path / "AGENTS.md").write_text("# How to work\n", encoding="utf-8")
    d = tmp_path / PACKS_DIR / "python"
    d.mkdir(parents=True)
    (d / "10_style.md").write_text("# Python style\n", encoding="utf-8")

    charter = load_charter(tmp_path, locale="fr")
    assert any("AGENTS.md has no fr translation" in w for w in charter.warnings)
    assert not any("AGENTS" in w for w in load_charter(tmp_path, locale="en").warnings)


def test_the_operating_rules_are_served_in_the_charters_locale(tmp_path):
    root = _bilingual(tmp_path)
    assert load_charter(root, locale="en").operating_rules.startswith("# How to work")
    assert load_charter(root, locale="fr").operating_rules.startswith("# Comment travailler")


def test_a_translation_of_nothing_is_reported_rather_than_served(tmp_path):
    """`10_style.fr.md` with no `10_style.md` is reached by nobody: a
    translation is served through the page it translates. Silently dropping it
    would leave someone's written standards on disk and out of the charter."""
    (tmp_path / "AGENTS.md").write_text("# How to work\n", encoding="utf-8")
    d = tmp_path / PACKS_DIR / "python"
    d.mkdir(parents=True)
    (d / "orphan.fr.md").write_text("# Orpheline\n", encoding="utf-8")
    (d / "10_style.md").write_text("# Python style\n", encoding="utf-8")

    charter = load_charter(tmp_path, locale="fr")
    assert [p.ref for p in charter.pages] == ["python/10_style.md"]
    assert any("orphan.md" in w and "does not exist" in w for w in charter.warnings)


def test_a_dotted_filename_is_not_mistaken_for_a_translation(tmp_path):
    """Only locales that have a catalogue count as locales. Reading any
    two-letter segment as a language would turn `api.v2.md` into a translation
    of `api.md` for a language called `v2`, and the page would vanish from the
    index to pay for the cleverness.
    """
    (tmp_path / "AGENTS.md").write_text("# How to work\n", encoding="utf-8")
    d = tmp_path / PACKS_DIR / "api"
    d.mkdir(parents=True)
    (d / "api.v2.md").write_text("# Version 2\n", encoding="utf-8")
    (d / "schema.v10.md").write_text("# Schema\n", encoding="utf-8")

    refs = sorted(p.ref for p in load_charter(tmp_path, locale="fr").pages)
    assert refs == ["api/api.v2.md", "api/schema.v10.md"]


def test_the_page_budget_measures_the_file_actually_served(tmp_path):
    """A translation is not the same length as its original, and the budget
    exists to say what an agent will have to read."""
    (tmp_path / "AGENTS.md").write_text("# How to work\n", encoding="utf-8")
    d = tmp_path / PACKS_DIR / "python"
    d.mkdir(parents=True)
    (d / "big.md").write_text("x" * 100, encoding="utf-8")
    (d / "big.fr.md").write_text("x" * (MAX_PAGE_CHARS + 50), encoding="utf-8")

    french = load_charter(tmp_path, locale="fr")
    assert french.pages[0].chars == MAX_PAGE_CHARS + 50
    assert any("page budget" in w for w in french.warnings)

    english = load_charter(tmp_path, locale="en")
    assert english.pages[0].chars == 100
    assert not any("page budget" in w for w in english.warnings)


def test_the_fingerprint_follows_the_translation_that_is_served(tmp_path):
    """The digest reads the file served, so editing a French page changes the
    French fingerprint and leaves the English one alone. Both halves matter:
    the first because provenance has to track what actually ran, the second
    because an English deployment should not get a cold prefix cache out of
    somebody else's translation work."""
    root = _bilingual(tmp_path)
    before_fr = load_charter(root, locale="fr").fingerprint
    before_en = load_charter(root, locale="en").fingerprint

    (root / PACKS_DIR / "python" / "10_style.fr.md").write_text(
        "# Style Python\nruff décide, et c'est tout.\n", encoding="utf-8"
    )

    assert load_charter(root, locale="fr").fingerprint != before_fr
    assert load_charter(root, locale="en").fingerprint == before_en


def test_the_shipped_charter_is_translated_end_to_end():
    """The charter in this repository, not a fixture: every page and the
    operating rules carry a French sibling, so a `language: fr` deployment
    serves no English at all."""
    french = load_charter(SHIPPED, locale="fr")
    assert french.warnings == [], french.warnings
    assert all(p.translated for p in french.pages)
    assert french.operating_rules.startswith("# Comment travailler ici")
    assert "## Standards de la maison" in build_index(french)
