"""
The client kits, held to the claims they make.

Why this exists
---------------
`test_adopt.py` asserts that the kit files are written. That is worth having
and it is not the same as asserting they *work*: a kit is this project's
distribution channel, and the whole suite could be green while every adopted
repository pointed at an endpoint the gateway does not serve.

Three kinds of claim are checkable here without a client installed, and each
one is a sentence the kits themselves put in front of a reader:

* **"The gateway refuses these and that refusal cannot be bypassed."** Both
  denylists name specific commands. If the gateway does not in fact refuse one
  of them, "two mechanisms beat one" is half false and the weaker half is the
  one being advertised. Checked against the real engine.
* **"Declared BELOW what the engine serves […] raising this past it means
  being refused eventually."** The kit writes a context figure; the gateway
  publishes one. The kit's must not exceed it.
* **The placeholders.** A kit rendered with an unresolved `{{...}}` is a config
  that fails at load, and one using a name `adopt` does not substitute fails
  the same way with nobody to blame.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import json
import re

import pytest

from ai_bunker.adopt import PLACEHOLDERS, ROOT, render
from ai_bunker.rules import load_rules, screen_command

CLIENTS = ROOT / "clients"

#: Values `adopt` substitutes, matching what it computes for a local gateway.
VALUES = {
    "AI_BUNKER_URL": "http://127.0.0.1:8000/v1",
    "AI_BUNKER_URL_ROOT": "http://127.0.0.1:8000",
    "AI_BUNKER_API_KEY": "test-key",
    "AI_BUNKER_MODEL": "devstral",
    "AI_BUNKER_DECLARED_CONTEXT": "104000",
    "AI_BUNKER_COMPACTION_RESERVE": "16000",
    "AI_BUNKER_TEMPERATURE": "0.15",
}


@pytest.fixture(scope="module")
def rules():
    return load_rules(ROOT / "charter" / "rules")


def _rendered(relative: str) -> str:
    return render((CLIENTS / relative).read_text(encoding="utf-8"), VALUES)


# ---------------------------------------------------------------------------
# The claim that matters: what the kits promise the gateway refuses.
# ---------------------------------------------------------------------------


def _denied_commands() -> list[tuple[str, str]]:
    """(kit, command) for every command a kit's denylist refuses outright."""
    out: list[tuple[str, str]] = []

    opencode = json.loads(_rendered("opencode/opencode.json"))
    for pattern, verdict in (opencode.get("permission", {}).get("bash") or {}).items():
        if verdict == "deny":
            out.append(("opencode", pattern.rstrip("*").strip()))

    claude = json.loads(_rendered("claude-code/settings.json"))
    for entry in claude.get("permissions", {}).get("deny") or []:
        inner = re.match(r"Bash\((.*?)(?::\*)?\)$", entry)
        if inner:
            out.append(("claude-code", inner.group(1).strip()))
    return out


def test_every_command_a_kit_denies_is_refused_by_the_gateway(rules):
    """Both kits print "The gateway refuses these and that refusal cannot be
    bypassed." This holds them to it against the real engine.

    A kit that denies something the gateway allows is advertising a belt it
    does not have: the client-side block is the weaker of the two barriers --
    it is a config file anyone can edit -- so if the stronger one is absent,
    the sentence is backwards.
    """
    denied = _denied_commands()
    assert denied, "no denylist was parsed; the kits changed shape"

    for kit, command in denied:
        refusal, _notes = screen_command(command, rules)
        assert refusal is not None, (
            f"{kit} denies {command!r} and the gateway does not refuse it, "
            "so the kit's claim about two barriers is half false"
        )


def test_the_kits_do_not_claim_more_than_the_rules_cover(rules):
    """The other direction, as a sanity check on the test above: at least one
    denied command must be refused by a BLOCKER rather than merely noted, or
    the assertion would pass on warnings alone."""
    severities = set()
    for _kit, command in _denied_commands():
        refusal, _ = screen_command(command, rules)
        if refusal is not None:
            severities.add(refusal.severity)
    assert "BLOCKER" in severities


# ---------------------------------------------------------------------------
# The context figure, which is the founding failure in configuration form.
# ---------------------------------------------------------------------------


def test_the_declared_context_a_kit_writes_is_below_what_is_served():
    """The kit's own comment: "Declared BELOW what the engine serves […]
    raising this past it means being refused eventually."

    `adopt` defaults to 104,000 against a 131,072-token engine, which is the
    margin the whole project is about: a client estimates its own tokens and
    under-counts, and the gap is the only protection while a turn grows.
    """
    from ai_bunker.config import Settings, Upstream

    served = Upstream(name="local", base_url="http://x/v1").served_context
    declared = int(VALUES["AI_BUNKER_DECLARED_CONTEXT"])
    assert declared < served, f"the kit declares {declared} against {served} served"

    # And the gateway's own declaration must agree with the kit's.
    settings = Settings()
    assert declared <= int(served * settings.declared_fraction) + 1


def test_the_compaction_reserve_leaves_room_to_work():
    """A reserve that eats the declared context compacts in a loop, which is
    the shape of the incident this project was built around."""
    declared = int(VALUES["AI_BUNKER_DECLARED_CONTEXT"])
    reserve = int(VALUES["AI_BUNKER_COMPACTION_RESERVE"])
    from ai_bunker.budget import MIN_WORKING_TOKENS

    assert declared - reserve > MIN_WORKING_TOKENS * 3


# ---------------------------------------------------------------------------
# Placeholders: a kit that renders to `{{...}}` fails at load.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "relative",
    [
        "opencode/opencode.json",
        "claude-code/settings.json",
        "claude-code/CLAUDE.md",
        "opencode/.opencode/plugins/bounded-reads.js",
        "langgraph/ai_bunker_langgraph.py",
        "llamaindex/ai_bunker_llamaindex.py",
        "smolagents/ai_bunker_smolagents.py",
    ],
)
def test_a_kit_renders_with_nothing_left_unresolved(relative):
    """`render` leaves an unknown placeholder in place and reports it, rather
    than substituting an empty string -- a config holding `{{...}}` fails
    loudly at load, where a silently empty URL fails at the first request with
    a message about nothing in particular. So nothing must be left."""
    assert "{{" not in _rendered(relative), f"{relative} has an unresolved placeholder"


def test_every_placeholder_a_kit_uses_is_one_adopt_substitutes():
    """The other half: a kit naming `{{AI_BUNKER_PORT}}` would render with that
    text intact and fail at load, with nobody obviously to blame."""
    used: set[str] = set()
    # Only the files a kit is made of. `rglob("*")` reached into `__pycache__`
    # and tried to read a compiled `.pyc` as text -- a test that fails because
    # of its own side effects.
    kinds = {".json", ".md", ".js", ".py", ".txt", ".yaml", ".yml"}
    for path in CLIENTS.rglob("*"):
        if path.is_file() and path.suffix in kinds and "__pycache__" not in path.parts:
            used |= set(re.findall(r"\{\{([A-Z_]+)\}\}", path.read_text(encoding="utf-8")))
    unknown = used - set(PLACEHOLDERS)
    assert not unknown, f"kits use placeholders adopt does not substitute: {sorted(unknown)}"


# ---------------------------------------------------------------------------
# The configs have to be what their clients expect.
# ---------------------------------------------------------------------------


def test_the_rendered_configs_are_valid_json():
    """A kit that does not parse is a kit that does nothing, and the comment
    keys the files carry are the obvious way to break that."""
    for relative in ("opencode/opencode.json", "claude-code/settings.json"):
        json.loads(_rendered(relative))


def test_the_openai_surface_is_the_v1_root_and_anthropic_is_not():
    """Claude Code reads both, and they are different roots: the
    OpenAI-compatible surface lives under `/v1` and the Anthropic one does
    not. Swapping them produces 404s that look like a broken gateway."""
    settings = json.loads(_rendered("claude-code/settings.json"))["env"]
    assert settings["OPENAI_BASE_URL"].endswith("/v1")
    assert not settings["ANTHROPIC_BASE_URL"].endswith("/v1")
    assert settings["OPENAI_BASE_URL"].startswith(settings["ANTHROPIC_BASE_URL"])


def test_the_opencode_plugin_is_syntactically_valid_javascript():
    """It runs in the client, not here, so nothing else would notice a typo
    until somebody adopted the kit."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    path = CLIENTS / "opencode/.opencode/plugins/bounded-reads.js"
    result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "relative",
    [
        "langgraph/ai_bunker_langgraph.py",
        "llamaindex/ai_bunker_llamaindex.py",
        "smolagents/ai_bunker_smolagents.py",
    ],
)
def test_a_framework_kit_compiles_and_reads_the_documented_environment(relative):
    """These are modules a user imports, so a syntax error ships silently --
    nothing in this repository imports them. And they must read the same
    environment variables the other kits are rendered with, or a user who
    configured one kit has not configured the others."""
    import py_compile

    source = (CLIENTS / relative).read_text(encoding="utf-8")
    py_compile.compile(str(CLIENTS / relative), doraise=True)

    used = set(re.findall(r"AI_BUNKER_[A-Z_]+", source))
    assert used, f"{relative} reads no ai-bunker environment at all"
    assert used <= set(PLACEHOLDERS), f"{relative} invents {sorted(used - set(PLACEHOLDERS))}"
