"""Refusing to install what the project never declared.

Models invent package names, and an attacker who registers an invented one
owns every machine whose agent installs it. Asking a registry whether a
package exists is the wrong answer twice: it puts a network call on the
enforcement path of a tool whose claim is that nothing leaves the network, and
the malicious package *is* registered, precisely so the check passes.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import json

import pytest

from ai_bunker.adopt import ROOT
from ai_bunker.dependencies import check, declared, packages_in

# ---------------------------------------------------------------------------
# Reading what a project declares.
# ---------------------------------------------------------------------------


def test_this_repository_declares_its_own_dependencies():
    names = declared(ROOT)
    for required in ("fastapi", "httpx", "pytest", "os-helper", "ruff"):
        assert required in names, f"{required} is in pyproject.toml but was not harvested"


def test_configuration_is_not_mistaken_for_a_dependency():
    """A false positive here does not merely add noise, it *weakens* the
    check: a name counts as approved that nobody approved. `addopts` and
    `all` were both harvested before the reader became section-aware."""
    names = declared(ROOT)
    for junk in ("addopts", "all", "testpaths", "line-length", "version"):
        assert junk not in names


def test_names_are_normalised_the_way_the_index_does(tmp_path):
    """PyPI treats `-`, `_` and `.` as the same character and ignores case, so
    a manifest saying `typing_extensions` must answer for `typing-extensions`."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["Typing_Extensions>=4", "Flask[async]>=2.0"]\n',
        encoding="utf-8",
    )
    names = declared(tmp_path)
    assert "typing-extensions" in names
    assert "flask" in names


def test_a_lock_file_counts_as_declared(tmp_path):
    """A transitive dependency is still one the project resolved and committed."""
    (tmp_path / "package-lock.json").write_text(
        json.dumps({"packages": {"node_modules/left-pad": {"version": "1.3.0"}}}),
        encoding="utf-8",
    )
    assert "left-pad" in declared(tmp_path)


def test_a_project_with_no_manifest_declares_nothing(tmp_path):
    assert declared(tmp_path) == set()


# ---------------------------------------------------------------------------
# Reading what a command would install.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command, tool, packages",
    [
        ("pip install requests", "pip", ["requests"]),
        ("pip3 install -U httpx rich", "pip3", ["httpx", "rich"]),
        ("uv add fastapi", "uv", ["fastapi"]),
        ("npm install --save left-pad", "npm", ["left-pad"]),
        ("npm i @scope/pkg", "npm", []),
        ("cargo add serde", "cargo", ["serde"]),
    ],
)
def test_the_packages_a_command_names_are_read(command, tool, packages):
    found_tool, found = packages_in(command)
    if packages:
        assert found_tool == tool
    assert found == packages


@pytest.mark.parametrize(
    "command",
    [
        "pip install -r requirements.txt",
        "pip install .",
        "pip install -e .",
        "pip install ./local/wheel.whl",
        "pip install https://example.com/pkg.tar.gz",
    ],
)
def test_installing_what_the_project_already_declares_names_nothing(command):
    """`-r requirements.txt` installs the declared set by definition, and `.`
    installs the project itself. Neither is a package to second-guess."""
    _tool, packages = packages_in(command)
    assert packages == []


def test_a_command_that_is_not_an_install_is_ignored():
    assert packages_in("ls -la src/") == ("", [])
    assert packages_in("git commit -m 'install the thing'") == ("", [])


# ---------------------------------------------------------------------------
# The check itself.
# ---------------------------------------------------------------------------


def test_a_hallucinated_package_is_refused():
    """`reqeusts` is the shape of the attack: one transposition away from a
    real package, and registrable by anyone."""
    result = check("pip install reqeusts", ROOT)
    assert not result.ok
    assert result.undeclared == ["reqeusts"]


def test_a_declared_package_is_allowed():
    assert check("pip install httpx", ROOT).ok
    assert check("uv add pytest", ROOT).ok


def test_a_genuine_new_dependency_is_refused_too(tmp_path):
    """Intended, not a side effect. Choosing a dependency has a licence, a
    maintainer and a supply chain attached, and is not an agent's decision to
    take mid-task."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["httpx"]\n', encoding="utf-8"
    )
    assert not check("pip install numpy", tmp_path).ok


def test_the_refusal_names_the_packages():
    from ai_bunker.dependencies import refusal_message

    result = check("pip install reqeusts notarealpkg", ROOT)
    message = refusal_message(result)
    assert "reqeusts" in message and "notarealpkg" in message
    assert "packages are" in message  # plural, because there are two


def test_a_project_with_no_manifest_warns_rather_than_refusing_everything(tmp_path, caplog):
    """An empty declared set would refuse every install and look like the
    check working. It is the check having nothing to compare against."""
    from ai_bunker.dependencies import warn_if_unreadable

    with caplog.at_level("WARNING"):
        warn_if_unreadable(tmp_path)
    assert "no dependency manifest" in caplog.text


# ---------------------------------------------------------------------------
# Through the pipeline, where it actually runs.
# ---------------------------------------------------------------------------


def _call(command: str) -> list[dict]:
    return [
        {
            "id": "c1",
            "type": "function",
            "function": {"name": "bash", "arguments": json.dumps({"command": command})},
        }
    ]


def test_stage_four_refuses_an_undeclared_install():
    from ai_bunker.pipeline import screen_outbound
    from ai_bunker.rules import load_rules

    rules = load_rules(ROOT / "charter" / "rules")
    refusal, command, _notes = screen_outbound(
        _call("pip install reqeusts"), rules, project_root=str(ROOT)
    )
    assert refusal is not None and refusal.id == "deps.undeclared_package"
    assert command == "pip install reqeusts"


def test_the_check_is_off_unless_a_project_root_is_configured():
    """A gateway serving several repositories cannot know which manifest
    applies, so this stays opt-in rather than guessing."""
    from ai_bunker.pipeline import screen_outbound
    from ai_bunker.rules import load_rules

    rules = load_rules(ROOT / "charter" / "rules")
    refusal, _c, _n = screen_outbound(_call("pip install reqeusts"), rules)
    assert refusal is None


def test_the_synthesised_rule_behaves_like_any_other():
    """Downstream speaks in rules -- the audit log, the refusal tool result,
    the dashboard. A parallel path is how two mechanisms end up disagreeing
    about what was refused."""
    from ai_bunker.dependencies import as_rule
    from ai_bunker.rules import refusal_message as rule_message

    rule = as_rule(check("pip install reqeusts", ROOT))
    assert rule.scope == "command" and rule.severity == "BLOCKER"
    assert "reqeusts" in rule_message(rule)
    # The pattern must never match on its own: the decision is made in code.
    assert not rule.pattern.search("pip install reqeusts")
