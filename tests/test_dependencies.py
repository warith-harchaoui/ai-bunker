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

from ai_bunker import dependencies as deps
from ai_bunker.adopt import ROOT
from ai_bunker.dependencies import check, declared, packages_in

# ---------------------------------------------------------------------------
# Reading what a project declares.
# ---------------------------------------------------------------------------


def test_what_a_project_declares_is_read_from_its_manifests(tmp_path):
    """Everything a name has to survive before it can be compared to one.

    This repository's own `pyproject.toml` is the live specimen: the real
    dependencies are harvested, and the **configuration keys are not**. A
    false positive here does not merely add noise, it *weakens* the check --
    a name counts as approved that nobody approved, and `addopts` and `all`
    were both harvested before the reader became section-aware.

    Names are **normalised the way the index does**: PyPI treats `-`, `_` and
    `.` as the same character and ignores case, so a manifest saying
    `typing_extensions` answers for `typing-extensions`, and an extra in
    square brackets is not part of the name. A **lock file** counts, because a
    transitive dependency is still one the project resolved and committed.
    And a project with **no manifest** declares nothing, which is a different
    answer from "declares none of these" and is handled as such below.
    """
    names = declared(ROOT)
    for required in ("fastapi", "httpx", "pytest", "os-helper", "ruff"):
        assert required in names, f"{required} is in pyproject.toml but was not harvested"
    for junk in ("addopts", "all", "testpaths", "line-length", "version"):
        assert junk not in names

    python = tmp_path / "python"
    python.mkdir()
    (python / "pyproject.toml").write_text(
        '[project]\ndependencies = ["Typing_Extensions>=4", "Flask[async]>=2.0"]\n',
        encoding="utf-8",
    )
    normalised = declared(python)
    assert "typing-extensions" in normalised
    assert "flask" in normalised

    node = tmp_path / "node"
    node.mkdir()
    (node / "package-lock.json").write_text(
        json.dumps({"packages": {"node_modules/left-pad": {"version": "1.3.0"}}}),
        encoding="utf-8",
    )
    assert "left-pad" in declared(node)

    bare = tmp_path / "bare"
    bare.mkdir()
    assert declared(bare) == set()


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
def test_a_command_that_names_no_package_to_second_guess_names_none(command):
    """`-r requirements.txt` installs the declared set by definition, and `.`
    installs the project itself -- neither is a package to second-guess. Nor
    is a command that is not an install at all, including one whose message
    happens to contain the word.
    """
    _tool, packages = packages_in(command)
    assert packages == []

    assert packages_in("ls -la src/") == ("", [])
    assert packages_in("git commit -m 'install the thing'") == ("", [])


# ---------------------------------------------------------------------------
# The check itself.
# ---------------------------------------------------------------------------


def test_an_undeclared_package_is_refused_and_a_declared_one_is_not(tmp_path):
    """`reqeusts` is the shape of the attack: one transposition away from a
    real package, and registrable by anyone. A package the manifest already
    carries is allowed, through whichever installer asks for it.

    A **genuine** new dependency is refused too, and that is intended rather
    than a side effect: choosing a dependency has a licence, a maintainer and
    a supply chain attached, and is not an agent's decision to take mid-task.
    The refusal **names** every package it refused, in the plural when there
    is more than one, because an agent told only that something was refused
    retries.
    """
    from ai_bunker.dependencies import refusal_message

    result = check("pip install reqeusts", ROOT)
    assert not result.ok
    assert result.undeclared == ["reqeusts"]

    assert check("pip install httpx", ROOT).ok
    assert check("uv add pytest", ROOT).ok

    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["httpx"]\n', encoding="utf-8"
    )
    assert not check("pip install numpy", tmp_path).ok

    message = refusal_message(check("pip install reqeusts notarealpkg", ROOT))
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


def test_stage_four_refuses_an_install_the_way_every_other_rule_refuses():
    """The check only matters where it runs, and it has to look like the rest
    of the system when it does.

    It **fires** in `screen_outbound`, naming `deps.undeclared_package` and
    the command it judged. It is **off unless a project root is configured**,
    because a gateway serving several repositories cannot know which manifest
    applies and guessing would refuse half of them. And the finding is a
    **rule** like any other: downstream speaks in rules -- the audit log, the
    refusal tool result, the dashboard -- and a parallel path is how two
    mechanisms end up disagreeing about what was refused. Its pattern never
    matches on its own, because the decision is made in code and a pattern
    that could fire alone would be a second, weaker copy of it.
    """
    from ai_bunker.dependencies import as_rule
    from ai_bunker.pipeline import screen_outbound
    from ai_bunker.rules import load_rules
    from ai_bunker.rules import refusal_message as rule_message

    rules = load_rules(ROOT / "charter" / "rules")
    refusal, command, _notes = screen_outbound(
        _call("pip install reqeusts"), rules, project_root=str(ROOT)
    )
    assert refusal is not None and refusal.id == "deps.undeclared_package"
    assert command == "pip install reqeusts"

    unconfigured, _c, _n = screen_outbound(_call("pip install reqeusts"), rules)
    assert unconfigured is None

    rule = as_rule(check("pip install reqeusts", ROOT))
    assert rule.scope == "command" and rule.severity == "BLOCKER"
    assert "reqeusts" in rule_message(rule)
    assert not rule.pattern.search("pip install reqeusts")


# ---------------------------------------------------------------------------
# Versions. A downgrade needs no new package, only an older one.
# ---------------------------------------------------------------------------


@pytest.fixture
def pinned(tmp_path):
    """A project that pins two dependencies and leaves one as a range."""
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\nflask>=2.0\n", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"dependencies": {"react": "18.2.0", "lodash": "^4.17.0"}}', encoding="utf-8"
    )
    return tmp_path


@pytest.mark.parametrize(
    "spec,version",
    [
        ("==2.31.0", "2.31.0"),
        ("===2.31.0", "2.31.0"),
        ("2.31.0", "2.31.0"),
        ("v1.2.3", "1.2.3"),
        (">=2.0", ""),
        ("~=2.31", ""),
        ("^2.31.0", ""),
        (">2.0,<3", ""),
        ("*", ""),
        ("", ""),
        ("latest", ""),
    ],
)
def test_only_an_exact_pin_counts_as_a_pin(spec, version):
    """A range is a decision to accept whatever satisfies it, so a command
    landing inside the range has not departed from the manifest."""
    assert deps._pinned(spec) == version


def test_a_version_that_departs_from_the_pin_is_refused_in_either_direction(pinned):
    """The attack that needs no new package: an older release of an approved
    one, with a known hole in it. Every name-based check passes it.

    The pins are read from **every manifest** -- `requirements.txt` and
    `package.json` here -- and a **downgrade** is refused with both versions
    named, because "wrong version" without the two numbers is not something
    anyone can act on. An **upgrade** is refused on the same grounds and not
    as an afterthought: the manifest says what is installed, and a command
    that installs something else makes the repository wrong either way. The
    npm `name@version` form is read as well as pip's `==`, or half the
    ecosystem would walk past this.
    """
    assert deps.declared_pins(pinned) == {"requests": "2.31.0", "react": "18.2.0"}

    assert deps.check("pip install requests==2.31.0", pinned).ok

    downgrade = deps.check("pip install requests==2.6.0", pinned)
    assert not downgrade.ok
    assert [(p.package, p.asked, p.declared) for p in downgrade.mismatched] == [
        ("requests", "2.6.0", "2.31.0")
    ]
    message = deps.refusal_message(downgrade)
    assert "2.6.0" in message and "2.31.0" in message
    assert deps.as_rule(downgrade).id == "deps.version_mismatch"

    assert not deps.check("pip install requests==9.9.9", pinned).ok

    assert [(p.package, p.asked) for p in deps.check("npm i react@17.0.0", pinned).mismatched] == [
        ("react", "17.0.0")
    ]


def test_what_is_not_a_departure_from_a_pin_is_not_refused(pinned):
    """The half that keeps the half above usable, since a version check that
    fires on correct input gets switched off.

    A **trailing zero** is the same release: `2.31` and `2.31.0` are one
    version, and refusing that would be a false refusal on a manifest somebody
    wrote slightly differently. A **range** is a decision to accept whatever
    satisfies it, so `flask>=2.0` is not departed from by installing 3.0. An
    **unpinned install** of a pinned package is noted rather than refused --
    it may well resolve to the pin, and stopping the command over a maybe is
    the wrong trade. And a package **nobody declared** has no declared version
    to differ from, so the finding is about the package rather than about a
    pin, or the message sends the reader to the wrong manifest line.
    """
    assert deps._same_version("2.31", "2.31.0")
    assert not deps._same_version("2.31.1", "2.31.0")

    assert deps.check("pip install flask==3.0", pinned).ok
    assert deps.check("npm i lodash@4.18.0", pinned).ok

    unpinned = deps.check("pip install requests", pinned)
    assert unpinned.ok, "it must not stop the command"
    assert unpinned.unpinned == ["requests"]
    assert deps.as_note(unpinned).severity == "WARNING"
    assert "no version" in deps.unpinned_message(unpinned)

    undeclared = deps.check("pip install nonexistent-helper", pinned)
    assert undeclared.undeclared == ["nonexistent-helper"]
    assert undeclared.mismatched == []
    assert deps.as_rule(undeclared).id == "deps.undeclared_package"


# ---------------------------------------------------------------------------
# A hole found while adding the above: the shorthand nobody matched.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "command,allowed",
    [
        # `npm i lodash` -- the form people actually type -- went past the
        # undeclared-package refusal entirely, and so did `pnpm i`. Found by
        # probing while the version check was being written.
        ("npm install nonexistent-helper", False),
        ("npm i nonexistent-helper", False),
        ("npm in nonexistent-helper", False),
        ("pnpm i nonexistent-helper", False),
        ("bun a nonexistent-helper", False),
        ("yarn add nonexistent-helper", False),
        # Beside them, the commands a one-letter verb must not drag in. A
        # verb allowed to float near a tool name would refuse a file copy for
        # installing undeclared packages.
        ("npm run build && cp -i a b", True),
        ("git commit -m 'add i'", True),
        ("echo install", True),
    ],
)
def test_every_installer_shorthand_is_screened_and_nothing_else_is(command, allowed, pinned):
    """The safe spellings are listed beside the unsafe ones on purpose: that
    is where a reader checks that the shorthand matcher rejects the right
    half, and a table that only lists what must be refused cannot show it."""
    assert deps.check(command, pinned).ok is allowed, command
