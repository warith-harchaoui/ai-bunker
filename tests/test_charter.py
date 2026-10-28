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
    # Created rather than assumed, so a caller can build several charters in
    # subdirectories of one `tmp_path` -- which is what a test covering more
    # than one shape of charter has to do.
    tmp_path.mkdir(parents=True, exist_ok=True)
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


@pytest.mark.parametrize("locale", i18n.available())
def test_the_index_is_capped_by_collapsing_the_biggest_pack_first(tmp_path, locale):
    """An index that costs what the pages cost has reinvented concatenation.

    So the listing is capped -- but *how* it degrades is the feature, and the
    first version got it wrong. It degraded the body as a whole, so importing
    one 77-page pack turned `python: 10_style.md, tests.md` into
    `python (2 pages)`: it spent the agent's knowledge of two page names to
    save the forty-five characters that named them. The degradation is per
    pack now, biggest first, and it has to say how to list what it collapsed
    or the collapsed pack is simply gone.

    Run per locale because the collapsed form is prose -- including a plural
    that exists only once a pack collapses, and that a translator can get
    wrong in a language English never exercises.
    """
    mixed = _charter(
        tmp_path / "mixed",
        {
            "python": {"10_style.md": "x", "tests.md": "x"},
            "solo": {"only.md": "x"},
            "big": {f"a_rather_long_page_name_{i}.md": "x" for i in range(200)},
        },
        locale=locale,
    )
    index = build_index(mixed)

    assert "big (200 page" in index, "the pack that overflowed must collapse"
    for kept in ("10_style.md", "tests.md", "only.md"):
        assert kept in index, f"{kept}: a small pack must keep its names"
    assert f"ls {PACKS_DIR}/" in index, "and it must say how to list the collapsed one"
    assert "(1 pages)" not in index and "(200 page)" not in index, "the plural is wrong"
    if "solo (" in index:
        assert "solo (1 page)" in index

    # And the cap holds when *every* pack is large, which is the case that
    # proves it is a cap rather than a preference.
    huge = _charter(
        tmp_path / "huge",
        {
            f"pack{p}": {f"a_rather_long_page_name_{i}.md": "x" for i in range(40)}
            for p in range(10)
        },
        locale=locale,
    )
    assert len(huge.pages) == 400
    assert len(build_index(huge)) < MAX_INDEX_CHARS * 2, "the cap did not engage"


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


def test_the_index_is_served_in_the_charters_language(shipped):
    """`locale` circulated as far as refusals and stopped there, so the block
    paid on *every* request went out in English whatever `language:` said.

    English stays the default, like every other agent-facing string here: a
    deployment opts into another language rather than out of this one.
    """
    french = build_index(load_charter(SHIPPED, locale="fr"))
    assert "Les pages vivent sous" in french
    assert "Une seule page à la fois" in french
    assert "Pages live under" not in french

    english = build_index(load_charter(SHIPPED, locale="en"))
    assert "Pages live under" in english
    assert "Les pages vivent sous" not in english

    assert build_index(load_charter(SHIPPED)) == english, "no locale means English"


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


@pytest.mark.parametrize(
    "spelling,resolved",
    [
        # Every spelling that resolves to English: the default, the tag, the
        # case, the region, and a locale with no catalogue at all.
        ("", "en"),
        ("en", "en"),
        ("EN", "en"),
        ("en-US", "en"),
        ("en_GB", "en"),
        ("zz", "en"),
        # And the same in the other direction, so this cannot pass by
        # everything collapsing to English.
        ("fr", "fr"),
        ("FR", "fr"),
        ("fr-CA", "fr"),
        ("fr_FR", "fr"),
    ],
)
def test_one_prompt_reports_one_fingerprint_however_the_locale_is_spelled(spelling, resolved):
    """The locale is stored resolved, and this is why.

    The fingerprint is a cache key and it is provenance, and the lie is worse
    in the second role: a decision record naming charter `9f2c` has to mean
    one prompt. So the rule runs in both directions. Two locales that render
    different bytes must report different digests -- that half is what putting
    the locale in the digest was for. And every spelling that renders the
    *same* bytes must report the same digest: `language:` defaults to an empty
    string, an unknown locale falls back, and a region tag is stripped, so
    `""`, `"zz"` and `"en-US"` all serve the byte-identical English index.
    Keeping the raw string gave that one prompt three different fingerprints,
    which is precisely the lie the digest was meant to prevent.

    """
    reference = load_charter(SHIPPED, locale=resolved)
    other = load_charter(SHIPPED, locale="fr" if resolved == "en" else "en")
    assert build_index(reference) != build_index(other), "the premise of this test"

    charter = load_charter(SHIPPED, locale=spelling)
    assert charter.locale == resolved
    assert build_index(charter) == build_index(reference)
    assert charter.fingerprint == reference.fingerprint
    assert charter.fingerprint != other.fingerprint


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


#: Each phrase the index has to carry, and the failure it prevents. The index
#: is the only thing the model reads about the charter, so every one of these
#: is load-bearing prose rather than decoration -- which is why they are data
#: here and not five separate tests of the same string.
INDEX_MUST_SAY = [
    ("not loaded into this prompt", "or a model answers about naming from habit, not the page"),
    ("before writing or reviewing code", "'available if needed' is not an instruction"),
    ("wins over your habits", "the charter has to outrank the training data"),
    ("one page at a time", "an agent told to consult the charter reads the whole pack"),
    ("never a whole pack", "the same, said the other way, because one spelling was ignored"),
]


def test_the_index_tells_the_model_how_to_use_it(shipped):
    """The index's wording is the feature, not an implementation detail.

    It is the entire contract between the charter and the model: the pages are
    not in the prompt, so what the model does with them is decided by these
    sentences and nothing else. It also has to show the catalogue it is an
    index *of* -- a concrete example and every pack and page -- or a model
    cannot name the thing it wants to open.
    """
    index = build_index(shipped)
    lowered = index.lower()
    for phrase, why in INDEX_MUST_SAY:
        assert phrase in lowered, f"the index no longer says {phrase!r}: {why}"

    assert f"Example: read {PACKS_DIR}/" in index, "a rule with no example is a rule guessed at"
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


def test_a_page_reference_is_resolved_against_the_index_and_never_as_a_path(shipped):
    """One mechanism, and the three things it has to do.

    It **hits**: what a model sends back is the index's own string, give or
    take a prefix -- the index shows `packs/python/10_style.md` and a model
    may send either half, with or without a leading slash. All of them reach
    the same page, or the charter is navigable only by a client that
    normalises for it.

    It **misses usefully**: the realistic failure is a wrong filename, and the
    fix is seeing the right one, at whichever level the model got it wrong. A
    refusal that only says "no" costs a round trip and teaches nothing.

    And it **cannot escape**, because the reference is matched against the
    index rather than resolved as a path -- which is also why the traversal
    attempts below need no separate defence, only the absence of one.
    """
    page = shipped.pages[0]
    expected = page.path.read_text(encoding="utf-8")
    for spelling in (page.ref, f"{PACKS_DIR}/{page.ref}", f"/{PACKS_DIR}/{page.ref}"):
        assert read_page(shipped, spelling) == expected, spelling

    with pytest.raises(AssertionError) as wrong_page:
        read_page(shipped, "python/style.md")
    assert "no page" in str(wrong_page.value)
    assert "10_style.md" in str(wrong_page.value), "it must list the pack's actual pages"

    with pytest.raises(AssertionError) as wrong_pack:
        read_page(shipped, "cobol/style.md")
    assert "Known packs" in str(wrong_pack.value)

    for attempt in ("../../etc/passwd", "python/../../../etc/passwd", "/etc/passwd"):
        with pytest.raises(AssertionError):
            read_page(shipped, attempt)


# ---------------------------------------------------------------------------
# Loading, and what it refuses to do silently.
# ---------------------------------------------------------------------------


def test_a_charter_that_is_wrong_in_some_way_says_so_and_keeps_serving(tmp_path):
    """One feature, four shapes of wrong, and the same answer to each.

    A charter is a directory a human edits, so it is routinely slightly wrong.
    The rule is that loading reports the problem and serves what it can: a
    charter that refused to load over one oversized page would take the
    gateway down for a typo, and one that loaded silently would leave the
    operator to infer the problem from a model's behaviour weeks later.

    The cases are the ones that actually happen -- no charter at all,
    forgetting `AGENTS.md`, letting a page grow past the budget, and dropping
    a page beside the packs rather than inside one -- and each has its own
    verdict about whether the content still gets served.
    """
    # No charter is a deployment choice, not a fault: nothing to serve, said
    # out loud, with every accessor answering emptily rather than raising.
    absent = load_charter(tmp_path / "absent")
    assert absent.pages == []
    assert build_index(absent) == ""
    assert system_blocks(absent) == []
    assert absent.warnings

    no_rules = tmp_path / "no-rules"
    (no_rules / PACKS_DIR / "default").mkdir(parents=True)
    (no_rules / PACKS_DIR / "default" / "a.md").write_text("# A\n", encoding="utf-8")
    charter = load_charter(no_rules)
    assert charter.operating_rules == ""
    assert any("AGENTS.md is missing" in w for w in charter.warnings), (
        "an index with no instruction to consult it is a charter nobody reads"
    )

    # Over the budget an agent reads the beginning and guesses the rest -- bad
    # enough to report, not bad enough to withhold the page.
    big = _charter(tmp_path / "big", {"default": {"huge.md": "x" * (MAX_PAGE_CHARS + 1)}})
    assert any("over the" in w and "page budget" in w for w in big.warnings)
    assert read_page(big, "default/huge.md")

    # The index groups by pack, so a page outside one has nowhere to go. Here
    # the page IS withheld, because there is no reference that would reach it.
    orphan = tmp_path / "orphan"
    (orphan / PACKS_DIR).mkdir(parents=True)
    (orphan / "AGENTS.md").write_text("# rules\n", encoding="utf-8")
    (orphan / PACKS_DIR / "orphan.md").write_text("# Orphan\n", encoding="utf-8")
    loose = load_charter(orphan)
    assert loose.pages == []
    assert any("no pack" in w for w in loose.warnings)


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


def test_the_fingerprint_identifies_the_charter_a_session_ran_under(tmp_path):
    """Two jobs, one value, and both of them need the same property.

    As **provenance**, a session records which charter it actually ran under,
    so the value has to move when any part of what was served moves -- a page
    or the operating rules alike. As a **cache key**, an unchanged charter has
    to re-serve from the engine's prefix cache, so the value must not move when
    nothing did. A digest that covered only the pages would satisfy the second
    and quietly fail the first.
    """
    charter = _charter(tmp_path, {"default": {"a.md": "original"}}, rules="# One\n")
    original = charter.fingerprint

    assert load_charter(tmp_path).fingerprint == original, "nothing changed; neither may this"

    (tmp_path / PACKS_DIR / "default" / "a.md").write_text("changed", encoding="utf-8")
    after_page = load_charter(tmp_path).fingerprint
    assert after_page != original, "a page changed"

    (tmp_path / "AGENTS.md").write_text("# Two\n", encoding="utf-8")
    assert load_charter(tmp_path).fingerprint != after_page, "the operating rules changed"


# ---------------------------------------------------------------------------
# The shipped charter is itself a deliverable.
# ---------------------------------------------------------------------------


def test_the_shipped_charter_is_complete_instructive_and_cheap(shipped):
    """This project ships a charter, so the charter is a deliverable and gets
    held to the three things that make one worth injecting.

    **Complete**: the operating rules are there, there are pages, there is a
    default pack, and nothing is missing or orphaned. **Instructive**: the
    operating rules are injected on every request, so they have to earn the
    space -- an agent must know that a cut output is not an error and that a
    refusal is a decision rather than a transient failure, or it retries both.
    **Cheap**: the published claim is that the charter's floor cost is a few
    percent of the window, and this is the figure that claim is made of.
    """
    assert shipped.operating_rules, "the shipped charter must carry its rules"
    assert len(shipped.pages) >= 5
    assert "default" in shipped.packs
    assert not [w for w in shipped.warnings if "missing" in w or "no pack" in w]

    text = shipped.operating_rules.lower()
    assert "slices" in text
    assert "truncated" in text, "an agent must know a cut output is not an error"
    assert "decision, not a transient failure" in text, "nor a refusal"

    counter = Counter(allow_ratio=True)
    cost = sum(counter.count(b) for b in system_blocks(shipped))
    assert cost < 0.05 * 26_000, f"{cost} tokens is more than 5% of a 26k window"


# ---------------------------------------------------------------------------
# The charter's own pages, per locale. A translation sits beside its original
# and is reached through it, so a page keeps ONE reference in every language.
# ---------------------------------------------------------------------------


def _bilingual(tmp_path):
    """A charter with one translated page, one untranslated, and rules in both."""
    tmp_path.mkdir(parents=True, exist_ok=True)  # usable in a subdirectory, like `_charter`
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


def test_one_reference_names_one_page_in_every_language(tmp_path):
    """The hard point of this feature, and the reason translations are
    siblings rather than a parallel tree.

    Three things follow from "one reference", and they are the same property
    seen from three sides. `read_page` answers the same reference in either
    locale with the right file. A translation is never a page of its own --
    an index naming `10_style.fr.md` would teach an agent a path that resolves
    in one language only, and an index naming both would cost double on the
    one block paid for on every request. And the page *list* is identical
    across locales: what the agent is told exists cannot change with the
    language, or the charter is two charters wearing one name.
    """
    root = _bilingual(tmp_path)
    english = load_charter(root, locale="en")
    french = load_charter(root, locale="fr")

    assert read_page(english, "python/10_style.md").startswith("# Python style")
    assert read_page(french, "python/10_style.md").startswith("# Style Python")

    for charter, locale in ((english, "en"), (french, "fr")):
        refs = sorted(p.ref for p in charter.pages)
        assert refs == ["python/10_style.md", "python/tests.md"], locale
        assert ".fr.md" not in build_index(charter), locale

    assert [p.ref for p in english.pages] == [p.ref for p in french.pages]


def test_a_partial_translation_stays_usable_and_says_what_is_behind(tmp_path):
    """Falling behind is the normal state of any translation, so it is a case
    to serve rather than an error to raise.

    An untranslated page falls back to its original -- refusing to serve it
    would turn an incomplete translation into a charter with holes. The
    operator is told which pages are behind, once with the list rather than
    once per page, and the translated ones are not named in that warning. The
    operating rules get their own line, because they are the block injected
    into every request and being in a different language than the rest of the
    prompt is a bigger problem than one page being so.
    """
    charter = load_charter(_bilingual(tmp_path), locale="fr")
    served = {p.ref: p for p in charter.pages}

    assert served["python/10_style.md"].translated
    assert read_page(charter, "python/10_style.md").startswith("# Style Python")
    assert not served["python/tests.md"].translated
    assert read_page(charter, "python/tests.md").startswith("# Python tests")

    behind = [w for w in charter.warnings if "no fr translation" in w]
    assert len(behind) == 1
    assert "python/tests.md" in behind[0]
    assert "10_style" not in behind[0], "the translated page must not be named"

    # The rules follow the locale when they have a sibling...
    assert charter.operating_rules.startswith("# Comment travailler")
    assert load_charter(_bilingual(tmp_path / "en"), locale="en").operating_rules.startswith(
        "# How to work"
    )

    # ...and are reported by name when they do not.
    bare = tmp_path / "bare"
    (bare / PACKS_DIR / "python").mkdir(parents=True)
    (bare / "AGENTS.md").write_text("# How to work\n", encoding="utf-8")
    (bare / PACKS_DIR / "python" / "10_style.md").write_text("# Python style\n", encoding="utf-8")
    assert any(
        "AGENTS.md has no fr translation" in w for w in load_charter(bare, locale="fr").warnings
    )
    assert not any("AGENTS" in w for w in load_charter(bare, locale="en").warnings)


def test_a_file_that_merely_looks_like_a_translation_is_not_treated_as_one(tmp_path):
    """Two ways to misread a filename, and both cost a page out of the index.

    `10_style.fr.md` with no `10_style.md` is reached by nobody, because a
    translation is served through the page it translates -- so it is reported
    rather than silently dropped, which would leave somebody's written
    standards on disk and out of the charter. And only locales that have a
    catalogue count as locales: reading any dotted segment as a language would
    turn `api.v2.md` into a translation of `api.md` for a language called
    `v2`, and the page would vanish to pay for the cleverness.
    """
    orphan = tmp_path / "orphan"
    (orphan / PACKS_DIR / "python").mkdir(parents=True)
    (orphan / "AGENTS.md").write_text("# How to work\n", encoding="utf-8")
    (orphan / PACKS_DIR / "python" / "orphan.fr.md").write_text("# Orpheline\n", encoding="utf-8")
    (orphan / PACKS_DIR / "python" / "10_style.md").write_text("# Python style\n", encoding="utf-8")
    charter = load_charter(orphan, locale="fr")
    assert [p.ref for p in charter.pages] == ["python/10_style.md"]
    assert any("orphan.md" in w and "does not exist" in w for w in charter.warnings)

    dotted = tmp_path / "dotted"
    (dotted / PACKS_DIR / "api").mkdir(parents=True)
    (dotted / "AGENTS.md").write_text("# How to work\n", encoding="utf-8")
    (dotted / PACKS_DIR / "api" / "api.v2.md").write_text("# Version 2\n", encoding="utf-8")
    (dotted / PACKS_DIR / "api" / "schema.v10.md").write_text("# Schema\n", encoding="utf-8")
    refs = sorted(p.ref for p in load_charter(dotted, locale="fr").pages)
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
