"""
Tests for the command line itself.

These exist because of a bug that shipped: `ai-bunker budget --help` crashed.
A help string carried a literal "80%", argparse runs every help string through
%-formatting, and the whole command raised instead of printing. No test touched
`--help` until one did, and writing the examples by actually running the
commands is what found it.

So: every subcommand's help is exercised here, and every documented example is
checked against the real surface.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import re

import pytest

from ai_bunker.adopt import ROOT
from ai_bunker.cli import build_parser, main

SUBCOMMANDS = (
    "sizing",
    "compare",
    "recommend",
    "budget",
    "rules",
    "charter",
    "skill",
    "spec",
    "adopt",
    "serve",
    "doctor",
    "breaker",
    "tools",
    "detect",
    "catalog",
)


# ---------------------------------------------------------------------------
# Help must print, for every command.
# ---------------------------------------------------------------------------


def test_the_top_level_help_prints(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0
    assert "ai-bunker" in capsys.readouterr().out


@pytest.mark.parametrize("command", SUBCOMMANDS)
def test_every_subcommand_help_prints(command, capsys):
    """The regression test for the bug above, one per command.

    argparse expands `%` in a help string, so a literal percent sign has to be
    doubled. The failure is invisible until someone asks for help.
    """
    with pytest.raises(SystemExit) as caught:
        main([command, "--help"])
    assert caught.value.code == 0
    assert capsys.readouterr().out.strip()


def test_no_help_string_carries_an_unescaped_percent():
    """Catch the whole class, not just the one that bit.

    Walks every action in every subparser rather than relying on the
    per-command tests above to have been written for a new command.
    """
    parser = build_parser()
    offenders: list[str] = []

    def walk(p, path: str) -> None:
        for action in p._actions:
            text = action.help or ""
            # A bare % that is not part of %% or a %(name)s placeholder.
            if re.search(r"(?<!%)%(?!%|\(\w+\)[sdr])", text):
                offenders.append(f"{path} {action.dest}: {text!r}")
            # `choices` is a dict only on a subparsers action; on an ordinary
            # argument it is a list of allowed values. Treating both the same
            # is how this test failed on its second run.
            choices = getattr(action, "choices", None)
            if isinstance(choices, dict):
                for name, sub in choices.items():
                    if hasattr(sub, "_actions"):
                        walk(sub, f"{path} {name}".strip())

    walk(parser, "")
    assert not offenders, "unescaped % in help: " + "; ".join(offenders)


# ---------------------------------------------------------------------------
# The documented surface is the real surface.
# ---------------------------------------------------------------------------


def test_every_documented_subcommand_exists():
    parser = build_parser()
    sub = next(a for a in parser._actions if getattr(a, "choices", None))
    assert set(SUBCOMMANDS) == set(sub.choices)


@pytest.mark.parametrize("page", ["EXAMPLES.md", "EXEMPLES.md"])
def test_the_examples_only_use_commands_that_exist(page):
    """A worked example naming a command that was renamed is worse than none."""
    text = (ROOT / page).read_text(encoding="utf-8")
    for used in set(re.findall(r"^\s*(?:\$ )?ai-bunker (\w[\w-]*)", text, re.M)):
        assert used in SUBCOMMANDS, f"{page} uses `ai-bunker {used}`, which does not exist"


@pytest.mark.parametrize("page", ["EXAMPLES.md", "EXEMPLES.md"])
def test_the_examples_only_use_flags_that_exist(page):
    """The commonest way documentation rots: a flag renamed, the doc untouched."""
    parser = build_parser()
    sub = next(a for a in parser._actions if getattr(a, "choices", None))
    text = (ROOT / page).read_text(encoding="utf-8")

    unknown: list[str] = []
    for command, rest in re.findall(r"ai-bunker (\w[\w-]*)([^\n]*)", text):
        if command not in sub.choices:
            continue
        # Strip quoted arguments first: `rules --command "git push --force"`
        # carries flags that belong to git, not to this CLI. Reading them as
        # ours is how this test failed on its first run.
        rest = re.sub(r"'[^']*'|\"[^\"]*\"", " ", rest)
        known = {
            option for action in sub.choices[command]._actions for option in action.option_strings
        } | {"--help", "-h"}
        for flag in re.findall(r"(?<![\w-])(--[\w-]+)", rest):
            if flag not in known:
                unknown.append(f"{command} {flag}")
    assert not unknown, f"{page} uses flags that do not exist: {sorted(set(unknown))}"


@pytest.mark.parametrize("page", ["EXAMPLES.md", "EXEMPLES.md"])
def test_both_languages_cover_the_same_commands(page):
    """The two files drift apart silently; this is what notices."""
    other = "EXEMPLES.md" if page == "EXAMPLES.md" else "EXAMPLES.md"
    here = set(re.findall(r"ai-bunker (\w[\w-]*)", (ROOT / page).read_text(encoding="utf-8")))
    there = set(re.findall(r"ai-bunker (\w[\w-]*)", (ROOT / other).read_text(encoding="utf-8")))
    assert here == there, f"{page} and {other} document different commands"


def test_the_examples_are_linked_from_both_readmes():
    for readme, target in (("README.md", "EXAMPLES.md"), ("LISEZMOI.md", "EXEMPLES.md")):
        assert target in (ROOT / readme).read_text(encoding="utf-8"), (
            f"{readme} does not link {target}"
        )


# ---------------------------------------------------------------------------
# Failure modes a user will hit.
# ---------------------------------------------------------------------------


def test_an_unknown_accelerator_exits_cleanly_with_the_known_ones(capsys):
    assert main(["sizing", "--accelerator", "no-such-card"]) == 2
    assert "dgx-spark" in capsys.readouterr().err


def test_a_missing_charter_page_names_the_real_ones(capsys):
    assert main(["charter", "--page", "python/style.md"]) == 2
    assert "10_style.md" in capsys.readouterr().err


def test_a_refused_command_exits_non_zero(capsys):
    assert main(["rules", "--command", "git push --force origin main"]) == 1
    assert "shell.force_push" in capsys.readouterr().out


def test_an_allowed_command_exits_zero(capsys):
    assert main(["rules", "--command", "git diff --stat"]) == 0
    assert "no rule matched" in capsys.readouterr().out


def test_rules_check_gates(capsys):
    assert main(["rules", "--check"]) == 0
    assert "rules carrying evidence" in capsys.readouterr().out


def test_an_unreadable_config_does_not_leak_a_library_message(capsys, tmp_path, monkeypatch):
    """os-helper prints before raising on an unresolved key.

    An unauthenticated gateway is a legitimate choice, so "this key is not set"
    is a state `doctor` reports -- not a line every unrelated command prints.
    """
    monkeypatch.delenv("AI_BUNKER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "project").mkdir()
    main(["adopt", str(tmp_path / "project"), "--list", "--config", str(tmp_path / "none.yaml")])
    assert "Missing required keys" not in capsys.readouterr().err
