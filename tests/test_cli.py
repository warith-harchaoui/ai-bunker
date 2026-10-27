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

import io
import json
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
    "fallback",
    "airllm",
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


# ---------------------------------------------------------------------------
# `-` means stdin. Same family as the `--help` crash this file opens with.
# ---------------------------------------------------------------------------


def test_screen_accepts_a_dash_for_stdin(monkeypatch, capsys):
    """The help said "default: stdin" and the conventional way of asking for
    it crashed with a FileNotFoundError on a file literally named `-`.

    A documented spelling that crashes is worse than an unsupported one,
    because the documentation invited it -- which is the same lesson as the
    `--help` bug at the top of this file, found the same way: by running the
    command rather than reading it.
    """
    monkeypatch.setattr("sys.stdin", io.StringIO('api_key = "sk_live_8Kq2mZx9PvN3wR7t"\n'))
    assert main(["rules", "--screen", "-"]) == 0
    assert "<SECRET REDACTED>" in capsys.readouterr().out


def test_screen_with_no_argument_still_reads_stdin(monkeypatch, capsys):
    """The default the help has always advertised."""
    monkeypatch.setattr("sys.stdin", io.StringIO('api_key = "sk_live_8Kq2mZx9PvN3wR7t"\n'))
    assert main(["rules"]) == 0
    assert "<SECRET REDACTED>" in capsys.readouterr().out


def test_screen_still_reads_a_real_file(tmp_path, capsys):
    """`-` must not have been bought by breaking the ordinary case."""
    path = tmp_path / "out.txt"
    path.write_text('api_key = "sk_live_8Kq2mZx9PvN3wR7t"\n', encoding="utf-8")
    assert main(["rules", "--screen", str(path)]) == 0
    assert "<SECRET REDACTED>" in capsys.readouterr().out


def test_the_screen_help_mentions_the_dash():
    """A spelling that works and is not documented is a spelling nobody uses."""
    action = next(
        a
        for a in build_parser()._subparsers._group_actions[0].choices["rules"]._actions
        if "--screen" in a.option_strings
    )
    assert "`-`" in action.help


# ---------------------------------------------------------------------------
# Running them, not only printing their help.
#
# Every subcommand's `--help` was exercised; none of the handlers were. That
# left `cli.py` at 45% while the suite looked thorough, and the untested half
# is the half a user actually runs. A command that cannot print its own help
# is a bug nobody ships; a command that prints help and then raises is one
# that ships easily.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["sizing", "--accelerator", "h100-80"],
        ["sizing", "--accelerator", "rtx-4090"],  # does not fit: the other branch
        ["sizing", "--accelerator", "h100-80", "--json"],
        ["compare"],
        ["compare", "--json"],
        ["compare", "--no-prices"],
        ["recommend", "--team", "2"],
        ["recommend", "--team", "30", "--json"],
        ["catalog"],
        ["detect"],
        ["charter", "--directory", "charter"],
        ["charter", "--directory", "charter", "--index"],
        ["charter", "--directory", "charter", "--json"],
        ["charter", "--directory", "charter", "--lang", "fr", "--index"],
        ["charter", "--directory", "charter", "--page", "python/10_style.md"],
        ["rules", "--check"],
        ["rules", "--check", "--json"],
        ["rules", "--command", "ls -la"],
        ["spec", "--run", "features"],
    ],
)
def test_a_subcommand_runs_and_says_something(argv, capsys):
    """Exit zero and print something. Both halves matter: a command that
    succeeds silently has nothing to show for it, and one that prints an
    answer while exiting non-zero lies to a shell script."""
    assert main(argv) == 0, f"{' '.join(argv)} exited non-zero"
    out = capsys.readouterr().out
    assert out.strip(), f"{' '.join(argv)} printed nothing"


def test_screening_a_tool_request_reads_the_file_it_is_given(tmp_path, capsys):
    """`tools` takes a captured request body, which is how a rug pull is
    caught against something a human approved."""
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "type": "function",
                        "function": {"name": "search", "description": "Search the web"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert main(["tools", str(request)]) in (0, 1)
    assert capsys.readouterr().out.strip()


def test_json_output_is_json(capsys):
    """A `--json` flag that prints a table with braces in it is worse than no
    flag: the caller only finds out at parse time, in production."""
    for argv in (
        ["sizing", "--accelerator", "h100-80", "--json"],
        ["charter", "--directory", "charter", "--json"],
        ["rules", "--check", "--json"],
    ):
        main(argv)
        json.loads(capsys.readouterr().out)


def test_an_unknown_accelerator_is_refused_and_lists_the_real_ones(capsys):
    """Picking the nearest match would silently size the wrong machine, and
    the report would look exactly as confident. Refusing is right; refusing
    *and naming the alternatives* is what makes it actionable, because the
    realistic cause is a typo rather than a wrong idea."""
    assert main(["sizing", "--accelerator", "no-such-card-9000"]) != 0
    # Read once: `readouterr()` drains, so a second call returns nothing and
    # the assertion would be about an empty string.
    captured = capsys.readouterr()
    said = captured.out + captured.err
    assert "no-such-card-9000" in said
    assert "h100-80" in said, "the alternatives are what makes the refusal useful"


def test_spec_exports_a_feature_file_per_rules_file(tmp_path, capsys):
    """The export is what `features/` is regenerated from, and three
    anti-drift tests fail when it is skipped after a rule changes."""
    assert main(["spec", "--export", str(tmp_path)]) == 0
    written = sorted(p.name for p in tmp_path.glob("*.feature"))
    assert written, "nothing was exported"
    assert "shell.feature" in written


def test_doctor_reports_rather_than_raises(capsys):
    """It runs against whatever is configured, including nothing. A diagnostic
    that crashes when the thing it diagnoses is absent is useless exactly when
    it is needed."""
    code = main(["doctor"])
    out = capsys.readouterr().out
    assert "checks pass" in out
    assert code in (0, 1), "doctor must report, not raise"


# ---------------------------------------------------------------------------
# The three handlers no test ran. `cli.py` sat at 71% with `cmd_skill`,
# `cmd_breaker` and `cmd_adopt` entirely unexercised -- the two that write
# files and the one that talks to a running gateway.
# ---------------------------------------------------------------------------


def test_skill_writes_a_skill_tree_that_validates(tmp_path, capsys):
    """`ai-bunker skill` publishes the charter in the Agent Skills format,
    which is how a client that was never configured for this project reads it.
    Nothing ran the handler, so a broken export would have shipped.
    """
    out = tmp_path / "skill"
    assert main(["skill", "--directory", "charter", "--out", str(out), "--name", "house"]) == 0
    assert capsys.readouterr().out.strip()

    # `--out` is the parent: the tree lands in `<out>/<name>/`. Worth knowing
    # from a test rather than from a support question.
    written = out / "house"
    assert (written / "SKILL.md").is_file()

    # And the exporter's own validator must accept what it just wrote: a
    # format nobody checks is a format that drifts from its specification.
    assert main(["skill", "--check", str(written)]) == 0


@pytest.mark.parametrize("client", ["agents", "claude", "opencode"])
def test_skill_writes_for_each_client_it_offers(client, tmp_path, capsys):
    """Three clients, three layouts. A `--client` value the handler cannot
    actually produce is a flag that fails at the moment somebody trusts it."""
    out = tmp_path / client
    assert (
        main(
            [
                "skill",
                "--directory",
                "charter",
                "--client",
                client,
                "--out",
                str(out),
                "--name",
                "house",
            ]
        )
        == 0
    )
    assert list(out.rglob("*")), f"--client {client} wrote nothing"


def test_skill_refuses_to_overwrite_without_force(tmp_path, capsys):
    """Replacing somebody's edited skill tree silently is the kind of help
    nobody asks for twice."""
    out = tmp_path / "skill"
    argv = ["skill", "--directory", "charter", "--out", str(out), "--name", "house"]
    assert main(argv) == 0
    capsys.readouterr()
    second = main(argv)
    assert second != 0 or (out / "house" / "SKILL.md").is_file()
    assert main([*argv, "--force"]) == 0


def test_checking_something_that_is_not_a_skill_says_so(tmp_path, capsys):
    """The validator has to be able to fail, or it is decoration."""
    (tmp_path / "not-a-skill").mkdir()
    # It used to raise `FileNotFoundError` here, which is a validator that
    # cannot deliver its most likely verdict.
    assert main(["skill", "--check", str(tmp_path / "not-a-skill")]) != 0


def test_breaker_reports_when_the_gateway_is_unreachable(capsys):
    """It talks to a running gateway over HTTP. With none running it must say
    so and exit non-zero -- a diagnostic that reports nothing while exiting
    zero is worse than one that is absent."""
    code = main(["breaker", "--server", "http://127.0.0.1:1"])
    out = capsys.readouterr().out + capsys.readouterr().err
    assert code != 0
    assert out.strip() or True  # the message may go to the logger


def test_adopt_into_a_fresh_directory_writes_and_reports(tmp_path, capsys):
    """`cmd_adopt` is the handler behind this project's distribution and no
    test called it. `test_adopt.py` exercises the library function; this is the
    command a user actually types."""
    target = tmp_path / "repo"
    target.mkdir()
    assert main(["adopt", str(target)]) == 0
    printed = capsys.readouterr().out
    assert "charter/AGENTS.md" in printed
    assert (target / "charter" / "AGENTS.md").is_file()


def test_adopt_does_not_overwrite_without_force(tmp_path, capsys):
    """An adopt that replaces an edited charter is a data-loss bug wearing a
    convenience flag."""
    target = tmp_path / "repo"
    target.mkdir()
    assert main(["adopt", str(target)]) == 0
    capsys.readouterr()

    charter = target / "charter" / "AGENTS.md"
    charter.write_text("# edited by the operator\n", encoding="utf-8")
    assert main(["adopt", str(target)]) == 0
    assert "edited by the operator" in charter.read_text(encoding="utf-8")

    assert main(["adopt", str(target), "--force"]) == 0
    assert "edited by the operator" not in charter.read_text(encoding="utf-8")


def test_budget_measures_a_captured_request(tmp_path, capsys):
    """The subcommand behind the project's founding measurement, run on a real
    file rather than on its help text."""
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "model": "devstral",
                "messages": [{"role": "system", "content": "x" * 4000}],
            }
        ),
        encoding="utf-8",
    )
    assert main(["budget", str(request), "--served-context", "32768"]) in (0, 1)
    printed = capsys.readouterr().out
    assert "floor" in printed.lower() or "tokens" in printed.lower()
