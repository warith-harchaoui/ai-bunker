"""
Tests for adopting a repository.

Two properties matter and neither is obvious. An adopt must not destroy
anything a repository already had, and what it writes must actually work --
rendered configs that parse, a charter that loads with the same fingerprint as
its source, rules that still pass their own evidence.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import json

import os_helper as osh
import pytest

from ai_bunker.adopt import (
    CLIENTS,
    ROOT,
    adopt,
    plan_adopt,
    render,
    shadowing_claude_files,
    shadowing_notes,
)
from ai_bunker.charter import load_charter
from ai_bunker.rules import load_rules
from ai_bunker.rules import test_rules as check_rules


@pytest.fixture(autouse=True)
def quiet():
    previous = osh.verbosity()
    osh.verbosity(-1)
    yield
    osh.verbosity(previous)


@pytest.fixture
def repo(tmp_path):
    d = tmp_path / "project"
    d.mkdir()
    return d


def _adopt(repo, **over):
    kwargs = {"url": "http://gw.test:8000/v1", "api_key": "k", "model": "devstral"}
    kwargs.update(over)
    return adopt(repo, **kwargs)


# ---------------------------------------------------------------------------
# What lands, and that it is self-consistent.
# ---------------------------------------------------------------------------


def test_everything_planned_is_written(repo):
    plan = _adopt(repo)
    assert plan.writes
    for relative, _why in plan.writes:
        assert (repo / relative).exists(), f"{relative} was planned and not written"


def test_the_adopted_charter_is_identical_to_its_source(repo):
    """Same fingerprint, or the adopted copy is not the charter being served."""
    _adopt(repo)
    assert load_charter(repo / "charter").fingerprint == load_charter(ROOT / "charter").fingerprint


def test_the_adopted_charter_loads_as_a_charter(repo):
    _adopt(repo)
    charter = load_charter(repo / "charter")
    assert charter.operating_rules
    assert len(charter.pages) >= 5
    assert not [w for w in charter.warnings if "missing" in w or "no pack" in w]


def test_the_adopted_rules_still_pass_their_own_evidence(repo):
    """Copied rules that no longer hold up are worse than no rules."""
    _adopt(repo)
    report = check_rules(load_rules(repo / "charter" / "rules"))
    assert report.ok
    assert report.coverage == 1.0


def test_there_is_no_second_copy_of_the_operating_rules(repo):
    """The gateway serves them; a copy on disk could only drift from it."""
    _adopt(repo)
    assert (repo / "charter" / "AGENTS.md").exists()
    assert not (repo / "AGENTS.md").exists()


# ---------------------------------------------------------------------------
# The precedence trap: this tool writes a CLAUDE.md, and Claude Code reads
# AGENTS.md only when there is no CLAUDE.md at or above the working directory.
# So adopting into a repository that keeps its instructions in AGENTS.md makes
# that file go dark, silently, with nothing erroring.
# ---------------------------------------------------------------------------


def test_an_existing_agents_md_is_reported_as_about_to_be_shadowed(repo):
    (repo / "AGENTS.md").write_text("our rules", encoding="utf-8")
    plan = plan_adopt(repo)
    assert plan.notes, "writing CLAUDE.md over a repo with AGENTS.md said nothing"
    note = " ".join(plan.notes)
    assert "AGENTS.md" in note and "CLAUDE.md" in note
    assert "stops being read" in note
    assert "--client opencode" in note, "it should offer the way out"
    assert "~" in plan.summary(), "the note must reach the printed summary"


def test_a_repo_with_no_agents_md_is_not_warned(repo):
    """Most repositories. A check that fires on all of them is noise."""
    assert plan_adopt(repo).notes == []


def test_the_opencode_only_kit_writes_no_claude_md_and_says_nothing(repo):
    (repo / "AGENTS.md").write_text("our rules", encoding="utf-8")
    plan = plan_adopt(repo, clients=("opencode",))
    assert "CLAUDE.md" not in [relative for relative, _ in plan.writes]
    assert plan.notes == [], "no CLAUDE.md is written, so nothing is shadowed"


def test_an_existing_claude_md_is_named_as_the_cause_rather_than_this_adopt(repo):
    """Both files already present: true, but not this tool's doing."""
    (repo / "AGENTS.md").write_text("our rules", encoding="utf-8")
    (repo / "CLAUDE.md").write_text("theirs", encoding="utf-8")
    plan = plan_adopt(repo)
    assert "CLAUDE.md" in plan.kept
    note = " ".join(plan.notes)
    assert "did not cause it" in note


def test_a_claude_md_above_the_repository_shadows_it_too(tmp_path):
    """The rule walks upward, so the check has to as well."""
    (tmp_path / "CLAUDE.md").write_text("from above", encoding="utf-8")
    inner = tmp_path / "project"
    inner.mkdir()
    (inner / "AGENTS.md").write_text("our rules", encoding="utf-8")
    note = " ".join(plan_adopt(inner).notes)
    assert "from above" in note or "shadowed from above" in note
    assert str(tmp_path / "CLAUDE.md") in note


def test_the_users_own_claude_md_is_not_counted(tmp_path, monkeypatch):
    """`~/.claude/CLAUDE.md` is in the list that does NOT count.

    It keeps loading alongside AGENTS.md, so counting it would warn every user
    who has personal instructions -- which is most of them -- about a conflict
    that does not exist.
    """
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_text("my preferences", encoding="utf-8")
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: home))

    project = home / "project"
    project.mkdir()
    assert shadowing_claude_files(project) == []


def test_a_dot_claude_agents_md_counts_as_one_to_protect(repo):
    (repo / ".claude").mkdir()
    (repo / ".claude" / "AGENTS.md").write_text("our rules", encoding="utf-8")
    assert plan_adopt(repo).notes, ".claude/AGENTS.md is read too and was ignored"


def test_the_charters_own_agents_md_is_not_mistaken_for_the_repositorys(repo):
    """`charter/AGENTS.md` is the operating rules the gateway injects.

    No client reads it as project instructions, so its presence must not
    trigger a warning about shadowing -- otherwise every adopt warns about the
    file the adopt itself just wrote.
    """
    (repo / "charter").mkdir()
    (repo / "charter" / "AGENTS.md").write_text("how to work here", encoding="utf-8")
    assert shadowing_notes(repo, writes=["CLAUDE.md"], kept=[]) == []


def test_the_real_run_reports_the_same_notes_as_the_dry_run(repo):
    """A dry run that disagrees with the run is worse than no dry run."""
    (repo / "AGENTS.md").write_text("our rules", encoding="utf-8")
    predicted = plan_adopt(repo).notes
    assert _adopt(repo).notes == predicted


# ---------------------------------------------------------------------------
# Rendered client configs must actually work.
# ---------------------------------------------------------------------------


def test_the_opencode_config_is_valid_json_with_the_gateway_wired_in(repo):
    _adopt(repo, declared_context=104_000, compaction_reserve=16_000)
    config = json.loads((repo / "opencode.json").read_text(encoding="utf-8"))
    provider = config["provider"]["ai-bunker"]
    assert provider["options"]["baseURL"] == "http://gw.test:8000/v1"
    assert provider["options"]["apiKey"] == "k"
    model = next(iter(provider["models"].values()))
    assert model["limit"]["context"] == 104_000
    assert config["model"] == "ai-bunker/devstral"
    assert config["compaction"]["reserved"] == 16_000


def test_the_opencode_config_turns_off_what_inflates_the_floor(repo):
    """The gateway can refuse a bloated session; only the client can avoid one."""
    _adopt(repo)
    config = json.loads((repo / "opencode.json").read_text(encoding="utf-8"))
    off = {k for k, v in config["tools"].items() if v is False}
    assert {"skill", "todowrite"} <= off
    assert {"webfetch", "websearch"} <= off, "sovereignty must hold at the client too"


def test_the_claude_code_settings_derive_both_url_shapes(repo):
    """Claude Code wants the root; OpenAI clients want /v1. Ask once."""
    _adopt(repo)
    settings = json.loads(
        (repo / ".claude" / "settings.ai-bunker.json").read_text(encoding="utf-8")
    )
    assert settings["env"]["OPENAI_BASE_URL"] == "http://gw.test:8000/v1"
    assert settings["env"]["ANTHROPIC_BASE_URL"] == "http://gw.test:8000"


def test_the_claude_code_settings_are_written_beside_not_over(repo):
    """.claude/settings.json carries personal preferences this kit cannot judge."""
    _adopt(repo)
    assert (repo / ".claude" / "settings.ai-bunker.json").exists()
    assert not (repo / ".claude" / "settings.json").exists()


def test_the_bounded_reads_plugin_is_the_only_plugin(repo):
    """If this grows, something was put in the wrong place."""
    _adopt(repo)
    plugins = list((repo / ".opencode" / "plugins").iterdir())
    assert [p.name for p in plugins] == ["bounded-reads.js"]
    body = plugins[0].read_text(encoding="utf-8")
    assert "tool.execute.before" in body
    assert "experimental.session.compacting" in body


def test_no_placeholder_survives_rendering(repo):
    """A leftover {{...}} is a config that fails at load, which is the point."""
    _adopt(repo)
    for name in ("opencode.json", ".claude/settings.ai-bunker.json"):
        assert "{{" not in (repo / name).read_text(encoding="utf-8")


def test_an_unresolved_placeholder_is_left_visible_not_blanked():
    """Failing at load beats failing at the first request with an empty URL."""
    out = render("url={{AI_BUNKER_URL}} key={{AI_BUNKER_API_KEY}}", {"AI_BUNKER_URL": "u"})
    assert out == "url=u key={{AI_BUNKER_API_KEY}}"


def test_charter_pages_are_copied_byte_for_byte(repo):
    """A rendered charter page would be a silently rewritten standard."""
    _adopt(repo)
    for page in (ROOT / "charter" / "packs").rglob("*.md"):
        relative = page.relative_to(ROOT / "charter")
        assert (repo / "charter" / relative).read_bytes() == page.read_bytes()


# ---------------------------------------------------------------------------
# Nothing is destroyed.
# ---------------------------------------------------------------------------


def test_an_existing_file_is_kept(repo):
    """A repository with an opencode.json has one for a reason."""
    (repo / "opencode.json").write_text('{"mine": true}', encoding="utf-8")
    plan = _adopt(repo)
    assert "opencode.json" in plan.kept
    assert json.loads((repo / "opencode.json").read_text(encoding="utf-8")) == {"mine": True}


def test_force_replaces_it(repo):
    (repo / "opencode.json").write_text('{"mine": true}', encoding="utf-8")
    _adopt(repo, force=True)
    assert (
        "ai-bunker" in json.loads((repo / "opencode.json").read_text(encoding="utf-8"))["provider"]
    )


def test_an_existing_charter_is_kept_in_full(repo):
    (repo / "charter").mkdir()
    (repo / "charter" / "AGENTS.md").write_text("# ours\n", encoding="utf-8")
    plan = _adopt(repo)
    assert "charter/AGENTS.md" in plan.kept
    assert (repo / "charter" / "AGENTS.md").read_text(encoding="utf-8") == "# ours\n"


def test_adopting_into_this_installation_is_refused(tmp_path):
    """It would overwrite the templates with their own rendered output."""
    with pytest.raises(AssertionError, match="installation itself"):
        adopt(ROOT)


def test_a_missing_target_is_a_clear_error(tmp_path):
    with pytest.raises(AssertionError, match="not a directory"):
        adopt(tmp_path / "nope")


# ---------------------------------------------------------------------------
# The plan is the same code path as the run.
# ---------------------------------------------------------------------------


def test_the_plan_writes_nothing(repo):
    plan = plan_adopt(repo)
    assert plan.writes
    assert list(repo.iterdir()) == []


def test_the_plan_matches_what_the_run_does(repo):
    """A dry run that takes a different route can disagree with the run."""
    planned = {relative for relative, _ in plan_adopt(repo).writes}
    done = {relative for relative, _ in _adopt(repo).writes}
    assert planned == done


def test_the_plan_reports_what_it_would_keep(repo):
    (repo / "CLAUDE.md").write_text("mine", encoding="utf-8")
    plan = plan_adopt(repo)
    assert "CLAUDE.md" in plan.kept
    assert "CLAUDE.md" not in {relative for relative, _ in plan.writes}


def test_every_write_carries_a_reason(repo):
    """A tool that writes files into someone's repository explains each one."""
    for _relative, why in plan_adopt(repo).writes:
        assert why and len(why) > 10


# ---------------------------------------------------------------------------
# Selecting what to adopt.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("client", CLIENTS)
def test_one_client_can_be_adopted_alone(repo, client):
    _adopt(repo, clients=(client,))
    opencode = (repo / "opencode.json").exists()
    claude = (repo / "CLAUDE.md").exists()
    assert opencode is (client == "opencode")
    assert claude is (client == "claude-code")


def test_a_repository_can_keep_its_own_charter(repo):
    _adopt(repo, charter=False)
    assert not (repo / "charter").exists()
    assert (repo / "opencode.json").exists()


def test_an_unknown_client_is_reported_not_ignored(repo):
    plan = plan_adopt(repo, clients=("emacs",))
    assert not plan.ok
    assert any("emacs" in m for m in plan.missing)


def test_an_incomplete_installation_refuses_to_adopt(repo, tmp_path):
    """Half a kit is worse than none: it looks installed."""
    fake = tmp_path / "broken-install"
    (fake / "charter").mkdir(parents=True)
    with pytest.raises(AssertionError, match="incomplete"):
        adopt(repo, root=fake)


def test_a_rendered_kit_is_committable_without_a_key(repo):
    """An empty key is warned about, not silently baked in as something else."""
    _adopt(repo, api_key="")
    settings = json.loads(
        (repo / ".claude" / "settings.ai-bunker.json").read_text(encoding="utf-8")
    )
    assert settings["env"]["OPENAI_API_KEY"] == ""


# ---------------------------------------------------------------------------
# The kits are themselves a deliverable.
# ---------------------------------------------------------------------------


def test_the_shipped_templates_are_valid_before_rendering():
    """A template that only parses after substitution cannot be reviewed."""
    for name in ("clients/opencode/opencode.json", "clients/claude-code/settings.json"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "{{" in text, f"{name} has no placeholders; is it still a template?"
        # Substituting plausible values must yield parseable JSON.
        filled = render(
            text,
            {
                "AI_BUNKER_URL": "http://x/v1",
                "AI_BUNKER_URL_ROOT": "http://x",
                "AI_BUNKER_API_KEY": "k",
                "AI_BUNKER_MODEL": "m",
                "AI_BUNKER_DECLARED_CONTEXT": "1000",
                "AI_BUNKER_COMPACTION_RESERVE": "100",
                "AI_BUNKER_TEMPERATURE": "0.15",
            },
        )
        json.loads(filled)


def test_the_division_of_labour_is_documented():
    """A thin client kit is a claim; the table is where it is justified."""
    text = (ROOT / "clients" / "README.md").read_text(encoding="utf-8")
    assert "division of labour" in text.lower()
    for row in ("Bounded file reads", "Compaction thresholds", "Skill"):
        assert row in text
    assert "/v1/budget" in text, "verifying a client from the server must be explained"


def test_the_claude_md_tells_an_agent_what_the_gateway_does(repo):
    _adopt(repo)
    text = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    assert "ai-bunker:untrusted" in text, "an agent must know what a marked block is"
    assert "decision" in text, "and that a refusal is not a transient failure"
    assert "context_budget_exhausted" in text
