"""
What a shell will actually run, as opposed to what was typed.

`ai_bunker/shell.py` was 203 lines inside a 1,416-line `rules.py`. It is where
four separate bypasses lived, each found by probing and each the same mistake:
a pattern matching the *text* rather than the *command*.

The tests here are the four bypasses and the near misses that must stay
allowed. They are written against `shell_readings` directly rather than
through the engine, because that is the function a future rule author will
rely on without ever reading it.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import pytest

from ai_bunker.shell import shell_readings, without_env_prefix


def _reaches(line: str, command: str) -> bool:
    """Whether any reading of ``line`` reduces to ``command``."""
    return any(reading.strip() == command for reading in shell_readings(line))


# ---------------------------------------------------------------------------
# The four bypasses, as the commands that carried them.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "rm -rf /",
        "sudo rm -rf /",
        "sudo -u root rm -rf /",
        "sudo -n -u deploy rm -rf /",
        "sudo --user=root rm -rf /",
        "doas -u root rm -rf /",
        "timeout 5 rm -rf /",
        "FOO=bar rm -rf /",
        "A=1 B=2 rm -rf /",
        "echo ok && rm -rf /",
        "rm -rf / && echo done",
        "rm -rf / ; echo done",
        "rm -rf / | cat",
        "rm -rf / #cleanup",
        "(rm -rf /)",
        "nohup rm -rf /",
        "/bin/rm -rf /",
        "\\rm -rf /",
        "sh -c 'rm -rf /'",
        "bash -lc 'rm -rf /'",
        "env FOO=bar rm -rf /",
    ],
)
def test_every_way_of_writing_one_destructive_command_reduces_to_it(line):
    """Seventeen spellings, one command. A rule anchored on `^rm` saw one of
    them; the other sixteen are what `shell_readings` exists for, and a rule
    that watches commands inherits all of this by doing nothing."""
    assert _reaches(line, "rm -rf /"), f"{line!r} did not reduce to the command"


def test_a_valueless_option_does_not_swallow_the_command():
    """The failure mode of the fix above, and the reason its option list is
    short and closed.

    `-u` takes a user name, so the name must be consumed or it is left
    standing in the command position. `-i` takes nothing, so consuming the
    next token would reduce `sudo -i rm -rf /` to `-rf /` and stop it matching
    anything at all -- a worse bug than the one being fixed, introduced by
    being more thorough.
    """
    assert _reaches("sudo -i rm -rf /", "rm -rf /")
    assert _reaches("sudo -E rm -rf /", "rm -rf /")
    assert _reaches("sudo -u root rm -rf /", "rm -rf /")


def test_the_typed_string_is_always_the_first_reading():
    """So no detection that worked before the reductions can be weakened by
    them. A reading is added, never substituted."""
    for line in ("rm -rf /", "sudo rm -rf /", "echo a && echo b", ""):
        readings = shell_readings(line)
        if line:
            assert readings[0] == line


# ---------------------------------------------------------------------------
# What must stay allowed. A splitter that is too eager refuses ordinary work.
# ---------------------------------------------------------------------------


def test_a_separator_inside_quotes_is_not_a_separator():
    """A shell's splitter is quote-aware, so this one is. The semicolon in a
    commit message is not a command boundary, and refusing the commit would be
    the rule being clever about the wrong string."""
    line = 'git commit -m "fix; rm -rf / was the bug"'
    assert not _reaches(line, "rm -rf /")
    assert line in shell_readings(line)


@pytest.mark.parametrize(
    "line",
    [
        "make BUILD=release",
        "NODE_ENV=production npm run build",
        "VAR=value echo hello",
        "git log --oneline -5",
        "echo 'a && b'",
    ],
)
def test_ordinary_work_is_not_rewritten_into_something_else(line):
    """The near misses. Each of these resembles a bypass and is somebody's
    normal Tuesday, and `shell_readings` producing a surprising reduction here
    would make every command rule fire on it."""
    assert line in shell_readings(line)


def test_an_environment_assignment_is_stripped_only_from_the_head():
    """`FOO=bar cmd` is "set FOO, then run cmd". `make BUILD=release` is one
    command with an argument that happens to contain `=`."""
    assert without_env_prefix("A=1 B=2 rm -rf /") == "rm -rf /"
    assert without_env_prefix("rm -rf /") == "rm -rf /"
    assert without_env_prefix("make BUILD=release") == "make BUILD=release"


# ---------------------------------------------------------------------------
# Robustness: this runs on every outbound tool call.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("line", ["", "   ", None, "'", '"', "|||", "&&&", "$(", "`", "\\", ";;;;"])
def test_nothing_malformed_raises(line):
    """It screens whatever a model emitted, which is not guaranteed to be a
    shell command at all. A parser that raises here stops the gateway on the
    enforcement path."""
    readings = shell_readings(line)  # type: ignore[arg-type]
    assert isinstance(readings, list)


def test_a_very_long_line_is_handled_in_reasonable_time():
    """An adversarial line of fifty thousand `env` prefixes once turned the
    reductions from milliseconds into minutes, which is why the transformations
    are anchored. This holds that fix to a number."""
    import time

    line = "env " * 20_000 + "rm -rf /"
    started = time.perf_counter()
    shell_readings(line)
    assert time.perf_counter() - started < 2.0
