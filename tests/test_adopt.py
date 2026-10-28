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
    ALL_CLIENTS,
    CLIENTS,
    FRAMEWORK_KITS,
    FRAMEWORKS,
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


def test_the_adopted_charter_is_the_charter_being_served(repo):
    """Byte-for-byte, in every language, or the copy is a different charter
    wearing the same name.

    The fingerprint is the assertion that carries this: it covers the pages
    and the operating rules, so an equal one means an equal prompt. Checked
    per locale because the two halves are copied differently -- `packs/` goes
    as a tree and brings its translations along, the operating rules are
    copied by name and so had to have theirs named too. Without that, an
    adopted copy served French pages under English operating rules, and
    `load_charter` reported a translation the adopt had simply left behind:
    the sort of warning that gets blamed on the charter rather than on the
    tool that copied it.

    And the rules keep passing their own evidence, because copied rules that
    no longer hold up are worse than no rules at all.
    """
    plan = _adopt(repo)
    assert plan.writes
    for relative, _why in plan.writes:
        assert (repo / relative).exists(), f"{relative} was planned and not written"

    for locale in ("en", "fr"):
        adopted = load_charter(repo / "charter", locale=locale)
        shipped = load_charter(ROOT / "charter", locale=locale)
        assert adopted.fingerprint == shipped.fingerprint, locale
        assert adopted.warnings == [], (locale, adopted.warnings)

    charter = load_charter(repo / "charter")
    assert charter.operating_rules
    assert len(charter.pages) >= 5

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


def test_an_agents_md_about_to_go_dark_is_reported_with_the_way_out(repo):
    """The note is the feature. Nothing errors when this happens -- the file
    simply stops being read -- so a tool that writes `CLAUDE.md` into a
    repository keeping its instructions in `AGENTS.md` has to say so, name
    both files, and offer the escape (`--client opencode`). It has to reach
    the printed summary too, or it is a note nobody sees.

    The real run reports the same notes as the dry run, because a preview that
    disagrees with the run is worse than no preview.
    """
    (repo / "AGENTS.md").write_text("our rules", encoding="utf-8")
    plan = plan_adopt(repo)
    assert plan.notes, "writing CLAUDE.md over a repo with AGENTS.md said nothing"
    note = " ".join(plan.notes)
    assert "AGENTS.md" in note and "CLAUDE.md" in note
    assert "stops being read" in note
    assert "--client opencode" in note, "it should offer the way out"
    assert "~" in plan.summary(), "the note must reach the printed summary"
    assert _adopt(repo).notes == plan.notes


def test_a_claude_md_already_there_is_reported_as_not_this_tools_doing(repo):
    """Both files present is still a real conflict, and still worth saying --
    but blaming the adopt for it sends somebody looking at the wrong change."""
    (repo / "AGENTS.md").write_text("our rules", encoding="utf-8")
    (repo / "CLAUDE.md").write_text("theirs", encoding="utf-8")
    plan = plan_adopt(repo)
    assert "CLAUDE.md" in plan.kept
    assert "did not cause it" in " ".join(plan.notes)


def test_the_check_reads_precedence_exactly_the_way_claude_code_does(tmp_path, monkeypatch):
    """Which file shadows which is somebody else's rule, so the check has to
    follow it rather than approximate it -- in both directions.

    It **walks upward**, because a `CLAUDE.md` in a parent directory shadows
    just as effectively. It counts **`.claude/AGENTS.md`**, which is read too.
    It does not count **`~/.claude/CLAUDE.md`**, which keeps loading alongside
    `AGENTS.md` -- warning about it would fire for every user with personal
    instructions, which is most of them. And it does not count
    **`charter/AGENTS.md`**, the operating rules the gateway injects: no client
    reads those as project instructions, so counting them would make every
    adopt warn about the file the adopt itself just wrote.
    """
    above = tmp_path / "above"
    (above / "project").mkdir(parents=True)
    (above / "CLAUDE.md").write_text("from above", encoding="utf-8")
    (above / "project" / "AGENTS.md").write_text("our rules", encoding="utf-8")
    note = " ".join(plan_adopt(above / "project").notes)
    assert "from above" in note or "shadowed from above" in note
    assert str(above / "CLAUDE.md") in note

    # Separate directories, because each case has to be the only reason the
    # check fires -- a leftover `.claude/AGENTS.md` would answer the next one.
    dot_claude = tmp_path / "dot-claude"
    (dot_claude / ".claude").mkdir(parents=True)
    (dot_claude / ".claude" / "AGENTS.md").write_text("our rules", encoding="utf-8")
    assert plan_adopt(dot_claude).notes, ".claude/AGENTS.md is read too and was ignored"

    ours = tmp_path / "with-charter"
    (ours / "charter").mkdir(parents=True)
    (ours / "charter" / "AGENTS.md").write_text("how to work here", encoding="utf-8")
    assert shadowing_notes(ours, writes=["CLAUDE.md"], kept=[]) == []

    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "CLAUDE.md").write_text("my preferences", encoding="utf-8")
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: home))
    personal = home / "project"
    personal.mkdir()
    assert shadowing_claude_files(personal) == []


def test_a_repository_with_nothing_to_shadow_is_not_warned(repo):
    """Most repositories. A check that fires on all of them is noise -- and
    so is one that fires when no `CLAUDE.md` is being written at all."""
    assert plan_adopt(repo).notes == []

    (repo / "AGENTS.md").write_text("our rules", encoding="utf-8")
    opencode_only = plan_adopt(repo, clients=("opencode",))
    assert "CLAUDE.md" not in [relative for relative, _ in opencode_only.writes]
    assert opencode_only.notes == [], "no CLAUDE.md is written, so nothing is shadowed"


# ---------------------------------------------------------------------------
# Rendered client configs must actually work.
# ---------------------------------------------------------------------------


def test_the_rendered_kits_wire_the_gateway_in_and_carry_no_placeholder(repo):
    """One adopt, and everything a client needs to actually reach the gateway.

    **OpenCode** gets a provider pointed at `/v1` with the declared context
    and the compaction reserve the gateway publishes -- a client that declares
    more is eventually refused, so these two figures are the handshake. It
    also gets the tools that inflate the floor switched off: the gateway can
    refuse a bloated session, but only the client can avoid making one, and
    `webfetch`/`websearch` are off because sovereignty has to hold at the
    client too.

    **Claude Code** gets both URL shapes derived from the one answer -- it
    wants the server root where OpenAI clients want `/v1` -- written *beside*
    `settings.json` rather than over it, because that file carries personal
    preferences this kit cannot judge.

    And no `{{placeholder}}` survives rendering, in either file: a leftover
    one is a config that fails at load.
    """
    _adopt(repo, declared_context=104_000, compaction_reserve=16_000)

    config = json.loads((repo / "opencode.json").read_text(encoding="utf-8"))
    provider = config["provider"]["ai-bunker"]
    assert provider["options"]["baseURL"] == "http://gw.test:8000/v1"
    assert provider["options"]["apiKey"] == "k"
    assert next(iter(provider["models"].values()))["limit"]["context"] == 104_000
    assert config["compaction"]["reserved"] == 16_000
    off = {k for k, v in config["tools"].items() if v is False}
    assert {"skill", "todowrite"} <= off
    assert {"webfetch", "websearch"} <= off, "sovereignty must hold at the client too"

    settings = json.loads(
        (repo / ".claude" / "settings.ai-bunker.json").read_text(encoding="utf-8")
    )
    assert settings["env"]["OPENAI_BASE_URL"] == "http://gw.test:8000/v1"
    assert settings["env"]["ANTHROPIC_BASE_URL"] == "http://gw.test:8000"
    assert not (repo / ".claude" / "settings.json").exists()

    for name in ("opencode.json", ".claude/settings.ai-bunker.json"):
        assert "{{" not in (repo / name).read_text(encoding="utf-8")


def test_the_bounded_reads_plugin_is_the_only_plugin(repo):
    """If this grows, something was put in the wrong place."""
    _adopt(repo)
    plugins = list((repo / ".opencode" / "plugins").iterdir())
    assert [p.name for p in plugins] == ["bounded-reads.js"]
    body = plugins[0].read_text(encoding="utf-8")
    assert "tool.execute.before" in body
    assert "experimental.session.compacting" in body


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


def test_the_dry_run_is_the_same_code_path_as_the_run(repo):
    """Which is the only way a preview can be trusted. A dry run that takes a
    different route is free to disagree with the run it previews, and the
    disagreement shows up as a file somebody did not expect in their own
    repository.

    So it writes nothing, it plans exactly what the run writes, it reports
    what it would keep rather than silently skipping it, and every write
    carries a reason -- a tool that puts files in somebody's repository
    explains each one.
    """
    plan = plan_adopt(repo)
    assert plan.writes
    assert list(repo.iterdir()) == [], "a dry run touched the directory"
    for _relative, why in plan.writes:
        assert why and len(why) > 10

    planned = {relative for relative, _ in plan.writes}
    assert planned == {relative for relative, _ in _adopt(repo).writes}

    (repo / "CLAUDE.md").write_text("mine", encoding="utf-8")
    second = plan_adopt(repo)
    assert "CLAUDE.md" in second.kept
    assert "CLAUDE.md" not in {relative for relative, _ in second.writes}


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


# ---------------------------------------------------------------------------
# Agent frameworks.
#
# The kits above configure *code agents* -- somebody else's loop, which a kit
# has to reach into. These three are frameworks: the developer writes the loop,
# so the kit is a module they import, and the only things it can usefully carry
# are the endpoint and the context window to believe.
# ---------------------------------------------------------------------------


def test_a_framework_is_never_written_by_default(repo):
    """Writing Python into a repository is not the same act as writing a config
    file into one. A default that dropped three modules on every adopt would be
    authoring application code on the user's behalf."""
    written = {relative for relative, _ in plan_adopt(repo).writes}
    for module in FRAMEWORK_KITS.values():
        assert module not in written, f"{module} landed without being asked for"
    assert set(FRAMEWORKS) & set(CLIENTS) == set(), "a framework is in the default set"


def test_every_framework_is_selectable_and_lands_one_module(repo):
    for name, module in FRAMEWORK_KITS.items():
        plan = plan_adopt(repo, clients=(name,), charter=False)
        assert plan.ok, plan.missing
        assert [relative for relative, _ in plan.writes] == [module]


def test_two_frameworks_do_not_overwrite_each_other(repo):
    """The obvious design -- one `ai_bunker_client.py` -- makes the second
    adopt silently replace the first. The filenames are distinct on purpose."""
    assert len(set(FRAMEWORK_KITS.values())) == len(FRAMEWORK_KITS)
    adopt(repo, clients=tuple(FRAMEWORK_KITS), charter=False, url="http://h:1/v1")
    for module in FRAMEWORK_KITS.values():
        assert (repo / module).exists(), f"{module} was not written"


def test_the_cli_accepts_every_framework():
    """`--client` is built from ALL_CLIENTS; a kit missing from it is a kit
    nobody can ask for."""
    for name in FRAMEWORKS:
        assert name in ALL_CLIENTS
    for name in CLIENTS:
        assert name in ALL_CLIENTS


@pytest.mark.parametrize("name", sorted(FRAMEWORK_KITS))
def test_a_rendered_framework_kit_is_valid_python(repo, name):
    """The template is not: it carries `{{PLACEHOLDER}}`, and `render` is
    documented to leave an unresolved one in place so the file fails at load.
    What gets written has to parse."""
    import ast

    adopt(repo, clients=(name,), charter=False, url="http://127.0.0.1:9/v1", model="m")
    text = (repo / FRAMEWORK_KITS[name]).read_text(encoding="utf-8")
    ast.parse(text)
    assert "{{" not in text, "a placeholder survived into the rendered module"


@pytest.mark.parametrize("name", sorted(FRAMEWORK_KITS))
def test_a_framework_kit_never_carries_the_key(repo, name):
    """The URL and the model name are deployment facts and are rendered in. A
    key is a credential, and a credential rendered into a committable module is
    a credential in a git history. It comes from the environment or not at all.
    """
    adopt(
        repo,
        clients=(name,),
        charter=False,
        url="http://127.0.0.1:9/v1",
        api_key="sk-secret-value",
    )
    text = (repo / FRAMEWORK_KITS[name]).read_text(encoding="utf-8")
    assert "sk-secret-value" not in text, "the API key was written into the module"
    assert 'os.environ.get("AI_BUNKER_API_KEY"' in text


@pytest.mark.parametrize(
    "name,needle",
    [
        # Verified against each project's own documentation rather than
        # remembered. The parameter names differ between all three, which is
        # exactly why this is pinned: `base_url` for LangChain, `api_base` for
        # the other two, and `model` versus `model_id`.
        ("langgraph", "ChatOpenAI("),
        ("langgraph", "base_url=AI_BUNKER_URL"),
        ("llamaindex", "OpenAILike("),
        ("llamaindex", "api_base=AI_BUNKER_URL"),
        ("llamaindex", "context_window=AI_BUNKER_DECLARED_CONTEXT"),
        ("smolagents", "OpenAIModel("),
        ("smolagents", "api_base=AI_BUNKER_URL"),
        ("smolagents", "model_id=AI_BUNKER_MODEL"),
    ],
)
def test_the_kit_calls_the_constructor_each_project_documents(name, needle):
    text = (ROOT / "clients" / name / FRAMEWORK_KITS[name]).read_text(encoding="utf-8")
    assert needle in text, f"{name} kit no longer matches the documented API"


def test_the_smolagents_kit_warns_about_local_code_execution():
    """`CodeAgent` runs the model's Python in-process by default. The gateway
    refuses dangerous shell commands because it sees them as tool calls; it
    cannot see an `exec` inside the harness at all. That is the one risk a
    gateway genuinely does not cover, so the kit has to say so."""
    text = (ROOT / "clients" / "smolagents" / FRAMEWORK_KITS["smolagents"]).read_text(
        encoding="utf-8"
    )
    assert "executor_type" in text
    assert "docker" in text


@pytest.mark.parametrize("name", sorted(FRAMEWORK_KITS))
def test_a_framework_kit_says_what_it_does_not_carry(name):
    """A thin kit read as a complete one is a kit someone adds rules to. Each
    says outright that the charter, the screening and the budget are enforced
    server-side and cannot be switched off from here."""
    text = (ROOT / "clients" / name / FRAMEWORK_KITS[name]).read_text(encoding="utf-8")
    collapsed = " ".join(text.split())
    assert "enforced server-side and cannot be switched off here" in collapsed


# ---------------------------------------------------------------------------
# The temperature a kit is written with.
# ---------------------------------------------------------------------------


def test_the_temperature_follows_the_model_the_gateway_serves():
    """It used to be a constant, and the constant was one family's figure.

    `--temperature 0.15` is what the catalogue records for the Mistral
    generation, which is sensitive to it. The Qwen coder's authors ask for
    1.0, and that is the model the helper picks on every card from 80 GiB up --
    so the fixed default was wrong for the common deployment and silently so,
    since a temperature does not fail, it just degrades.
    """
    from ai_bunker.adopt import temperature_for
    from ai_bunker.sizing import load_catalog

    catalog = load_catalog()
    for model in catalog["models"]:
        declared = model.get("temperature")
        if declared is None:
            continue
        assert temperature_for(str(model["id"]), catalog) == float(declared)
        # The Hugging Face reference resolves too: that is what an upstream
        # config names, and a gateway in front of vLLM has no catalogue id.
        assert temperature_for(str(model["hf"]), catalog) == float(declared)

    assert len({temperature_for(str(m["id"]), catalog) for m in catalog["models"]}) > 1, (
        "if every model wanted the same temperature this lookup would be pointless"
    )


def test_an_unknown_upstream_gets_a_neutral_temperature_rather_than_a_guess():
    """A gateway in front of somebody else's endpoint is the common case, and
    it is not an error. What would be an error is inheriting a figure tuned for
    a model that is not being served."""
    from ai_bunker.adopt import NEUTRAL_TEMPERATURE, temperature_for

    assert temperature_for("some-model-we-have-never-heard-of") == NEUTRAL_TEMPERATURE
    assert temperature_for("") == NEUTRAL_TEMPERATURE


def test_a_kit_asks_for_a_need_rather_than_naming_a_model(repo):
    """The gateway matches needs before model names so the deployment can swap
    the model without regenerating a single client config. A kit that names a
    model is a kit that has to be regenerated when the helper picks better."""
    from ai_bunker.sizing import load_catalog

    adopt(repo, clients=("opencode",))
    rendered = (repo / "opencode.json").read_text(encoding="utf-8")
    for model in load_catalog()["models"]:
        assert str(model["id"]) not in rendered
        assert str(model["id"]).split("-", 1)[0] not in rendered
