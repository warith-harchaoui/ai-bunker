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
import pathlib

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


def _repo(path):
    """A fresh empty repository directory.

    The `repo` fixture gives a test one; several tests need two or three,
    because each precedence case has to be the only reason the check fires.
    """
    path.mkdir(parents=True)
    return path


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


def test_the_precedence_trap_is_detected_the_way_claude_code_resolves_it(tmp_path, monkeypatch):
    """One feature, and it only works if every half of it is right: the shadow
    is detected by somebody else's rule, and then reported usefully.

    **Detected.** Which file shadows which is Claude Code's rule, so the check
    follows it rather than approximating it, in both directions. It walks
    **upward**, because a `CLAUDE.md` in a parent shadows just as effectively.
    It counts **`.claude/AGENTS.md`**, which is read too. It does not count
    **`~/.claude/CLAUDE.md`**, which keeps loading alongside `AGENTS.md` --
    warning about it would fire for every user with personal instructions,
    which is most of them. It does not count **`charter/AGENTS.md`**, the
    operating rules the gateway injects, or every adopt would warn about the
    file it just wrote. And it fires on nothing when no `CLAUDE.md` is being
    written at all (`--client opencode`), which is also the escape hatch.

    **Reported.** Nothing errors when a file goes dark -- it simply stops
    being read -- so the note is the whole feature. It names both files, says
    what happens, offers the way out, and reaches the printed summary, or it
    is a note nobody sees. When both files were already there the note says
    so instead of blaming the adopt, because that sends somebody looking at
    the wrong change. And the real run reports the same notes as the dry run,
    because a preview that disagrees with the run is worse than no preview.
    """
    repo = _repo(tmp_path / "plain")
    assert plan_adopt(repo).notes == [], "most repositories; a check that fires on all is noise"

    (repo / "AGENTS.md").write_text("our rules", encoding="utf-8")
    plan = plan_adopt(repo)
    assert plan.notes, "writing CLAUDE.md over a repo with AGENTS.md said nothing"
    note = " ".join(plan.notes)
    assert "AGENTS.md" in note and "CLAUDE.md" in note
    assert "stops being read" in note
    assert "--client opencode" in note, "it should offer the way out"
    assert "~" in plan.summary(), "the note must reach the printed summary"
    assert _adopt(repo).notes == plan.notes, "the dry run and the run must agree"

    # The escape hatch works: no CLAUDE.md written, so nothing is shadowed.
    opencode_only = plan_adopt(repo, clients=("opencode",))
    assert "CLAUDE.md" not in [relative for relative, _ in opencode_only.writes]
    assert opencode_only.notes == []

    # Both files already present: a real conflict, and not this tool's doing.
    both = _repo(tmp_path / "both")
    (both / "AGENTS.md").write_text("our rules", encoding="utf-8")
    (both / "CLAUDE.md").write_text("theirs", encoding="utf-8")
    conflict = plan_adopt(both)
    assert "CLAUDE.md" in conflict.kept
    assert "did not cause it" in " ".join(conflict.notes)

    # Separate directories below, because each case has to be the only reason
    # the check fires -- a leftover `.claude/AGENTS.md` would answer the next.
    above = tmp_path / "above"
    (above / "project").mkdir(parents=True)
    (above / "CLAUDE.md").write_text("from above", encoding="utf-8")
    (above / "project" / "AGENTS.md").write_text("our rules", encoding="utf-8")
    upward = " ".join(plan_adopt(above / "project").notes)
    assert "from above" in upward or "shadowed from above" in upward
    assert str(above / "CLAUDE.md") in upward

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


def test_nothing_a_repository_already_had_is_destroyed(repo):
    """The property an adopt lives or dies by, over the three shapes it takes.

    A file the repository already has is **kept**, byte for byte -- a project
    with an `opencode.json` has one for a reason, and the same goes for a
    charter it wrote itself. `--force` is the one thing that replaces, which
    is what makes it worth typing. And a target that must not be adopted into
    is refused rather than half-written: this installation, because it would
    overwrite the templates with their own rendered output, and a path that
    is not a directory at all.
    """
    (repo / "opencode.json").write_text('{"mine": true}', encoding="utf-8")
    (repo / "charter").mkdir()
    (repo / "charter" / "AGENTS.md").write_text("# ours\n", encoding="utf-8")

    plan = _adopt(repo)
    assert "opencode.json" in plan.kept
    assert json.loads((repo / "opencode.json").read_text(encoding="utf-8")) == {"mine": True}
    assert "charter/AGENTS.md" in plan.kept
    assert (repo / "charter" / "AGENTS.md").read_text(encoding="utf-8") == "# ours\n"

    _adopt(repo, force=True)
    replaced = json.loads((repo / "opencode.json").read_text(encoding="utf-8"))
    assert "ai-bunker" in replaced["provider"]

    with pytest.raises(AssertionError, match="installation itself"):
        adopt(ROOT)
    with pytest.raises(AssertionError, match="not a directory"):
        adopt(repo / "nope")


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


def test_a_framework_kit_is_opt_in_and_lands_exactly_one_module(repo):
    """Writing Python into a repository is not the same act as writing a
    config file into one, so no framework is ever in the default set: a
    default that dropped three modules on every adopt would be authoring
    application code on the user's behalf. Each is selectable by name --
    `--client` is built from `ALL_CLIENTS`, and a kit missing from it is a kit
    nobody can ask for -- and each lands one module and only its own. The
    obvious design, one `ai_bunker_client.py`, would make the second adopt
    silently replace the first, so the filenames are distinct on purpose.
    """
    written = {relative for relative, _ in plan_adopt(repo).writes}
    for module in FRAMEWORK_KITS.values():
        assert module not in written, f"{module} landed without being asked for"
    assert set(FRAMEWORKS) & set(CLIENTS) == set(), "a framework is in the default set"

    for name in list(FRAMEWORKS) + list(CLIENTS):
        assert name in ALL_CLIENTS, f"{name} cannot be asked for on the command line"

    for name, module in FRAMEWORK_KITS.items():
        plan = plan_adopt(repo, clients=(name,), charter=False)
        assert plan.ok, plan.missing
        assert [relative for relative, _ in plan.writes] == [module]

    assert len(set(FRAMEWORK_KITS.values())) == len(FRAMEWORK_KITS), "two kits share a filename"
    adopt(repo, clients=tuple(FRAMEWORK_KITS), charter=False, url="http://h:1/v1")
    for module in FRAMEWORK_KITS.values():
        assert (repo / module).exists(), f"{module} was not written"


@pytest.mark.parametrize("name", sorted(FRAMEWORK_KITS))
def test_a_rendered_framework_kit_parses_and_carries_no_credential(repo, name):
    """What gets written has to load, and has to be committable.

    The template is neither: it carries `{{PLACEHOLDER}}`, and `render` is
    documented to leave an unresolved one in place so the file fails loudly at
    load rather than quietly at run. The URL and the model name are deployment
    facts and are rendered in; a key is a credential, and a credential
    rendered into a committable module is a credential in a git history, so it
    comes from the environment or not at all.
    """
    import ast

    adopt(
        repo,
        clients=(name,),
        charter=False,
        url="http://127.0.0.1:9/v1",
        model="m",
        api_key="sk-secret-value",
    )
    text = (repo / FRAMEWORK_KITS[name]).read_text(encoding="utf-8")
    ast.parse(text)
    assert "{{" not in text, "a placeholder survived into the rendered module"
    assert "sk-secret-value" not in text, "the API key was written into the module"
    assert 'os.environ.get("AI_BUNKER_API_KEY"' in text


#: What each shipped kit has to say, verified against that project's own
#: documentation rather than remembered. The constructor parameters differ
#: between all three, which is exactly why they are pinned: `base_url` for
#: LangChain, `api_base` for the other two, `model` versus `model_id`.
KIT_NEEDLES = {
    "langgraph": ["ChatOpenAI(", "base_url=AI_BUNKER_URL"],
    "llamaindex": [
        "OpenAILike(",
        "api_base=AI_BUNKER_URL",
        "context_window=AI_BUNKER_DECLARED_CONTEXT",
    ],
    # `CodeAgent` runs the model's Python in-process by default. The gateway
    # refuses dangerous shell commands because it sees them as tool calls; it
    # cannot see an `exec` inside the harness at all. That is the one risk a
    # gateway genuinely does not cover, so this kit has to say so.
    "smolagents": [
        "OpenAIModel(",
        "api_base=AI_BUNKER_URL",
        "model_id=AI_BUNKER_MODEL",
        "executor_type",
        "docker",
    ],
}


@pytest.mark.parametrize("name", sorted(FRAMEWORK_KITS))
def test_a_shipped_kit_matches_the_documented_api_and_states_its_limits(name):
    """A kit is read as a specification of how to talk to this gateway, so
    both halves have to hold. It calls the constructor its project documents,
    with that project's parameter names. And it says outright what it does not
    carry: a thin kit read as a complete one is a kit someone adds rules to,
    when the charter, the screening and the budget are enforced server-side
    and cannot be switched off from a client module at all.
    """
    text = (ROOT / "clients" / name / FRAMEWORK_KITS[name]).read_text(encoding="utf-8")
    for needle in KIT_NEEDLES[name]:
        assert needle in text, f"{name} kit no longer matches the documented API: {needle}"
    collapsed = " ".join(text.split())
    assert "enforced server-side and cannot be switched off here" in collapsed


# ---------------------------------------------------------------------------
# The temperature a kit is written with.
# ---------------------------------------------------------------------------


def test_the_temperature_follows_the_model_the_gateway_serves():
    """It used to be a constant, and the constant was one family's figure.

    `--temperature 0.15` is what the catalogue records for the Mistral
    generation, which is sensitive to it. The Qwen coder's authors ask for
    1.0, and that is the model the helper picks on every card from 80 GiB up
    -- so the fixed default was wrong for the common deployment and silently
    so, since a temperature does not fail, it just degrades.

    The lookup resolves a Hugging Face reference as well as a catalogue id,
    because that is what an upstream config names and a gateway in front of
    vLLM has no catalogue id. And an upstream it has never heard of -- the
    common case, and not an error -- gets a neutral figure rather than one
    tuned for a model nobody is serving.
    """
    from ai_bunker.adopt import NEUTRAL_TEMPERATURE, temperature_for
    from ai_bunker.sizing import load_catalog

    catalog = load_catalog()
    for model in catalog["models"]:
        declared = model.get("temperature")
        if declared is None:
            continue
        assert temperature_for(str(model["id"]), catalog) == float(declared)
        assert temperature_for(str(model["hf"]), catalog) == float(declared)

    assert len({temperature_for(str(m["id"]), catalog) for m in catalog["models"]}) > 1, (
        "if every model wanted the same temperature this lookup would be pointless"
    )

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


def test_a_child_process_can_be_told_the_website_is_not_here(monkeypatch, tmp_path):
    """One published figure is counted by a subprocess, and it has to count
    what a clone counts.

    Twenty-one tests in this suite are parametrised over the website's pages,
    so `pytest --collect-only` returns twenty-one more on the maintainer's
    machine than anywhere else, and the number written into both READMEs was
    the maintainer's. `without_site` is what makes the two agree.

    The two halves asserted here are the two ways it could silently stop
    working: an *empty* value falls through to `SITE_CANDIDATES` and finds the
    site again on the one machine that has it, and a value naming a real
    directory would find it outright. What is set has to resolve to None.
    """
    from ai_bunker.adopt import SITE_ENV, site_root, without_site

    site = tmp_path / "site"
    site.mkdir()
    monkeypatch.setenv(SITE_ENV, str(site))
    assert site_root() == site

    monkeypatch.setenv(SITE_ENV, without_site()[SITE_ENV])
    assert site_root() is None

    # And what makes that work: the value names something real, so it cannot
    # be mistaken for "unset" and fall through to the candidate search, and it
    # is not a directory, so `site_root` refuses it.
    declared = pathlib.Path(without_site()[SITE_ENV])
    assert declared.exists() and not declared.is_dir()
