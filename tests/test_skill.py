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
from ai_bunker.charter import load_charter
from ai_bunker.skill import (
    CLIENT_PATHS,
    MAX_DESCRIPTION,
    NAME_PATTERN,
    RECOMMENDED_BODY_LINES,
    Skill,
    build_skill,
    read_skill,
    validate,
    warnings,
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
