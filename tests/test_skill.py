"""The charter, published in the Agent Skills format.

The format is an open specification (agentskills.io) read natively by Claude
Code, OpenCode, Cursor, Goose, Amp, Roo, Codex, Copilot and Gemini CLI. These
tests hold the export to the parts of that specification a client will enforce,
because a skill that is almost valid is one some clients silently ignore.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import pytest

from ai_bunker.adopt import ROOT
from ai_bunker.charter import build_index, load_charter
from ai_bunker.skill import (
    CLIENT_PATHS,
    MAX_DESCRIPTION,
    NAME_PATTERN,
    RECOMMENDED_BODY_LINES,
    Skill,
    as_charter_pack,
    build_skill,
    import_skills,
    read_catalog,
    read_skill,
    split_body,
    validate,
    warnings,
    write_charter_pack,
    write_skill,
)


@pytest.fixture(scope="module")
def charter():
    return load_charter(ROOT / "charter")


@pytest.fixture(scope="module")
def skill(charter):
    return build_skill(charter)


# ---------------------------------------------------------------------------
# The specification, as a client will read it.
# ---------------------------------------------------------------------------


def test_the_charter_exports_as_a_valid_skill(skill):
    assert validate(skill) == []


@pytest.mark.parametrize(
    "name, ok",
    [
        ("team-charter", True),
        ("a", True),
        ("python3-style", True),
        ("Team-Charter", False),  # uppercase
        ("-charter", False),  # leading hyphen
        ("charter-", False),  # trailing hyphen
        ("team--charter", False),  # consecutive hyphens
        ("team charter", False),  # space
        ("", False),
        ("x" * 65, False),  # over 64 characters
    ],
)
def test_the_name_rule_matches_the_specification(name, ok):
    assert bool(NAME_PATTERN.match(name)) is ok


def test_a_description_over_the_limit_is_refused(skill):
    too_long = Skill(name="x", description="y" * (MAX_DESCRIPTION + 1), body="b")
    problems = validate(too_long)
    assert any(str(MAX_DESCRIPTION) in p for p in problems)


def test_an_empty_description_is_refused():
    assert any("description" in p for p in validate(Skill(name="x", description="  ", body="b")))


def test_the_validator_can_fail():
    """An auditor nobody has seen fail is an auditor nobody should trust."""
    broken = Skill(name="Bad--Name-", description="", body="")
    problems = validate(broken)
    assert len(problems) >= 2
    assert any("name" in p for p in problems)


def test_references_stay_one_level_deep(skill):
    """The specification asks for it, and `python/10_style.md` would not."""
    for filename in skill.references:
        assert "/" not in filename
    assert "python-10_style.md" in skill.references


def test_the_pack_survives_in_the_reference_name(skill):
    """`tests.md` alone says nothing about which language's tests it describes."""
    assert "python-tests.md" in skill.references


# ---------------------------------------------------------------------------
# Progressive disclosure: the reason the format and the charter agree.
# ---------------------------------------------------------------------------


def test_the_body_stays_within_the_recommended_budget(skill):
    """The specification recommends under 500 lines, with detail in
    references/. The charter was already built that way -- an index in the
    prompt, pages on demand -- which is why this export is a rename rather
    than a redesign."""
    assert skill.body.count("\n") + 1 < RECOMMENDED_BODY_LINES
    assert warnings(skill) == []


def test_every_page_is_reachable_from_the_body(skill, charter):
    """A page nothing links to is a page no agent will ever open."""
    for page in charter.pages:
        assert f"`{page.ref}`" in skill.body


def test_the_body_does_not_inline_the_pages(skill, charter):
    """If the pages were pasted in, the format's whole point would be lost."""
    for page in charter.pages:
        body = page.path.read_text(encoding="utf-8").strip()
        assert body not in skill.body


# ---------------------------------------------------------------------------
# Provenance: a copy on disk can drift from the charter the gateway enforces.
# ---------------------------------------------------------------------------


def test_the_fingerprint_travels_with_the_skill(skill, charter):
    assert skill.metadata["ai-bunker.charter-fingerprint"] == charter.fingerprint


def test_metadata_keys_are_namespaced(skill):
    """The specification advises it, and a bare `version` would collide."""
    assert all(k.startswith("ai-bunker.") for k in skill.metadata)


# ---------------------------------------------------------------------------
# On disk.
# ---------------------------------------------------------------------------


def test_the_directory_is_named_for_the_skill(skill, tmp_path):
    """The specification requires `name` to match its parent directory, and a
    mismatch is the kind some clients ignore in silence."""
    written = write_skill(skill, tmp_path)
    assert (tmp_path / skill.name / "SKILL.md").exists()
    assert len(written) == 1 + len(skill.references)


def test_it_refuses_to_overwrite_without_force(skill, tmp_path):
    write_skill(skill, tmp_path)
    with pytest.raises(AssertionError, match="already exist"):
        write_skill(skill, tmp_path)
    assert write_skill(skill, tmp_path, force=True)


def test_what_is_written_reads_back_identically(skill, tmp_path):
    write_skill(skill, tmp_path)
    again = read_skill(tmp_path / skill.name)
    assert again.name == skill.name
    assert again.description == " ".join(skill.description.split())
    assert set(again.references) == set(skill.references)
    assert validate(again) == []


def test_an_invalid_skill_never_reaches_the_disk(tmp_path):
    with pytest.raises(AssertionError, match="specification"):
        write_skill(Skill(name="NOT VALID", description="x", body="y"), tmp_path)
    assert not list(tmp_path.iterdir())


# ---------------------------------------------------------------------------
# Where the clients look.
# ---------------------------------------------------------------------------


def test_the_default_path_serves_both_named_clients():
    """OpenCode documents reading `.claude/skills/` as Claude-compatible, so
    one copy there serves Claude Code and OpenCode without writing twice."""
    assert CLIENT_PATHS["claude"] == ".claude/skills"
    assert "opencode" in CLIENT_PATHS and "agents" in CLIENT_PATHS


# ---------------------------------------------------------------------------
# The other direction: reading in a skills tree somebody else wrote.
#
# `build_skill` exports; these cover the import. Every number asserted here
# was measured against the real probabl-ai/skore-skills tree, then reduced to
# a fixture small enough to read.
# ---------------------------------------------------------------------------


FOLDED_SKILL = """---
name: build-ml-pipeline
description: >
  Declare a skrub DataOps graph from the data source to the predictor.
  Stateless steps use `.skb.apply_func`.
metadata:
  role: helper
  modelTier: big
---

# Build ML Pipeline

Preamble prose before any heading.

## Scope

Scope text.

## Core rules

Core rules text.
"""


def _tree(root, skills):
    """A skills tree on disk: {name: (skill_md, {ref_name: text})}."""
    for name, (source, refs) in skills.items():
        directory = root / name
        directory.mkdir(parents=True)
        (directory / "SKILL.md").write_text(source, encoding="utf-8")
        for ref_name, text in refs.items():
            (directory / "references").mkdir(exist_ok=True)
            (directory / "references" / ref_name).write_text(text, encoding="utf-8")
    return root


def test_a_folded_description_is_recovered_not_returned_as_its_marker(tmp_path):
    """`description: >` is the form other projects use, and it used to win.

    Reading only the text after the colon returned the fold marker, so the
    description became ">". That passes every length check and tells an agent
    nothing about when to load the skill.
    """
    _tree(tmp_path, {"build-ml-pipeline": (FOLDED_SKILL, {})})
    skill = read_skill(tmp_path / "build-ml-pipeline")
    assert skill.description.startswith("Declare a skrub DataOps graph")
    assert "`.skb.apply_func`" in skill.description, "the fold must join its lines"
    assert ">" not in skill.description.split()[0]


def test_nested_metadata_survives_the_read(tmp_path):
    """Where another project puts the facts that are not prose.

    The parser skipped every indented line, so `role` and `modelTier` were
    dropped and an imported skill arrived stripped of everything
    machine-readable.
    """
    _tree(tmp_path, {"build-ml-pipeline": (FOLDED_SKILL, {})})
    skill = read_skill(tmp_path / "build-ml-pipeline")
    assert skill.metadata == {"role": "helper", "modelTier": "big"}


def test_a_split_body_is_distributed_never_rewritten():
    """The line this project draws about editing someone else's content.

    A gateway may decide where a page ends. It may not decide what it says.
    """
    body = "intro\n\n## One\n\nalpha\n\n## Two\n\nbeta\n"
    slices = split_body(body, limit=10)
    assert len(slices) == 3, "it should cut at every heading it needs"
    assert "".join(text for _, text in slices) == body, "the rejoin must be exact"
    assert [heading for heading, _ in slices] == ["", "One", "Two"]


def test_a_body_inside_the_budget_is_left_whole():
    """No heading is invented for a page that did not need splitting."""
    body = "# Title\n\nshort enough\n"
    assert split_body(body, limit=10_000) == [("", body)]


def test_import_reads_every_skill_and_ignores_everything_else(tmp_path):
    _tree(
        tmp_path,
        {
            "alpha": (FOLDED_SKILL.replace("build-ml-pipeline", "alpha"), {}),
            "beta": (FOLDED_SKILL.replace("build-ml-pipeline", "beta"), {"r.md": "ref"}),
        },
    )
    (tmp_path / "not-a-skill").mkdir()
    (tmp_path / "loose.md").write_text("ignored", encoding="utf-8")
    skills = import_skills(tmp_path)
    assert [s.name for s in skills] == ["alpha", "beta"]
    assert skills[1].references == {"r.md": "ref"}


def test_a_declared_model_tier_is_recorded_and_never_acted_on(tmp_path):
    """The decision, asserted so it cannot be quietly reversed.

    skore-skills declares `modelTier: small | medium | big`, which lines up
    with this project's routing by need rather than by model name. Wiring the
    two would let a third-party directory decide what the team pays for
    inference, and that is an operator's call.
    """
    _tree(tmp_path, {"build-ml-pipeline": (FOLDED_SKILL, {})})
    skills = import_skills(tmp_path)
    pages = as_charter_pack(skills, pack="ml", source="probabl-ai/skore-skills", limit=60)
    page = next(text for key, text in pages.items() if key.endswith("01_overview.md"))
    assert "modelTier: big" in page, "the declaration must survive for a human to read"
    assert "not acted on" in page, "and the page must say it is not a routing decision"


def test_every_imported_page_carries_its_provenance(tmp_path):
    _tree(tmp_path, {"build-ml-pipeline": (FOLDED_SKILL, {"guide.md": "detail"})})
    pages = as_charter_pack(
        import_skills(tmp_path), pack="ml", source="probabl-ai/skore-skills", limit=60
    )
    assert pages, "the import produced nothing"
    for key, text in pages.items():
        assert "probabl-ai/skore-skills" in text, f"{key} does not say where it came from"


def test_the_description_is_paid_once_not_on_every_part(tmp_path):
    """It runs to 2,400 characters upstream; sixteen copies is the page budget."""
    _tree(tmp_path, {"build-ml-pipeline": (FOLDED_SKILL, {})})
    pages = as_charter_pack(import_skills(tmp_path), pack="ml", limit=60)
    carrying = [k for k, v in pages.items() if "Declare a skrub DataOps graph" in v]
    assert len(carrying) == 1, f"the description appears on {len(carrying)} pages"
    assert carrying[0].endswith("01_overview.md")


def test_a_published_digest_is_preferred_over_one_we_invent(tmp_path):
    """A digest this project computed only proves the import is self-consistent."""
    _tree(tmp_path, {"build-ml-pipeline": (FOLDED_SKILL, {})})
    catalog = {"skill:build-ml-pipeline": "abc123def456789000", "catalog_hash": "top"}
    pages = as_charter_pack(import_skills(tmp_path), pack="ml", catalog=catalog)
    page = next(iter(pages.values()))
    assert "abc123def4567890" in page
    assert "(published)" in page

    without = as_charter_pack(import_skills(tmp_path), pack="ml")
    assert "(computed here)" in next(iter(without.values()))


def test_a_catalogue_is_read_when_present_and_absent_otherwise(tmp_path):
    tree = _tree(tmp_path / "skills", {"alpha": (FOLDED_SKILL, {})})
    assert read_catalog(tree) == {}
    (tmp_path / ".catalog.json").write_text(
        '{"repository": "probabl-ai/skore-skills", "catalog_hash": "deadbeef", '
        '"skills": [{"id": "alpha", "hash": "aaa"}]}',
        encoding="utf-8",
    )
    found = read_catalog(tree)
    assert found["repository"] == "probabl-ai/skore-skills"
    assert found["catalog_hash"] == "deadbeef"
    assert found["skill:alpha"] == "aaa"


def test_a_broken_catalogue_is_ignored_rather_than_fatal(tmp_path):
    tree = _tree(tmp_path / "skills", {"alpha": (FOLDED_SKILL, {})})
    (tmp_path / ".catalog.json").write_text("{not json", encoding="utf-8")
    assert read_catalog(tree) == {}


def test_an_imported_page_is_not_overwritten_without_force(tmp_path):
    pages = {"ml/alpha.md": "new text"}
    target = tmp_path / "packs" / "ml" / "alpha.md"
    target.parent.mkdir(parents=True)
    target.write_text("written by a person", encoding="utf-8")

    assert write_charter_pack(pages, tmp_path) == []
    assert target.read_text(encoding="utf-8") == "written by a person"

    assert write_charter_pack(pages, tmp_path, force=True) == [target]
    assert target.read_text(encoding="utf-8") == "new text"


def test_the_import_round_trips_through_the_charter(tmp_path):
    """The point of the whole exercise, asserted end to end.

    A skills tree becomes pages the charter loads, groups into a pack and
    serves as an index -- which is what makes it cheap: the pages are on disk
    and the prompt carries a reference to them.
    """
    source = tmp_path / "source"
    _tree(source, {"build-ml-pipeline": (FOLDED_SKILL, {"guide.md": "detail"})})
    root = tmp_path / "charter"
    root.mkdir()
    (root / "AGENTS.md").write_text("Read one page at a time.", encoding="utf-8")

    pages = as_charter_pack(import_skills(source), pack="ml", source="probabl-ai/skore-skills")
    written = write_charter_pack(pages, root)
    assert written, "nothing was written"

    charter = load_charter(root)
    assert {p.pack for p in charter.pages} == {"ml"}
    assert len(charter.pages) == len(pages)
    assert charter.warnings == [], f"the charter complained: {charter.warnings}"

    on_disk = sum(p.chars for p in charter.pages)
    index = build_index(charter)
    assert len(index) < on_disk, "an index that costs what the pages cost is concatenation"
    assert "ml" in index
