"""
What a shell will actually run, as opposed to what was typed.

Why this is its own module
--------------------------
It was 203 lines inside a 1,416-line `rules.py` that also held the engine, the
loader, the decision log and the provenance wrapper. This part is none of
those: it knows nothing about rules, matches nothing, and decides nothing. It
answers one question -- *given this line, what commands will a shell execute?*
-- and every rule in the charter that screens a command depends on the answer
being right.

That matters more than tidiness, because this is where four separate bypasses
lived, each one found by probing and each one a case of a pattern matching the
text rather than the command:

* ``sudo rm -rf /`` -- a prefix in front of the command word;
* ``FOO=bar rm -rf /`` -- an environment assignment, which no rule author had
  in mind and which defeated every anchored pattern at once;
* ``echo ok && rm -rf /`` -- a line is not one command, and the anchors were
  right about one while the shell ran two;
* ``git -C . push --force`` -- a program that takes options of its own takes
  them whether or not the author of the tenth rule remembered.

The fix for all four is here rather than in the patterns, and that is the
argument for the file: a rule should say what it refuses, not re-derive what a
shell does. A new rule that watches a command inherits every one of these
corrections by doing nothing.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import re

#: A leading ``VAR=value`` assignment, which a shell applies to the environment
#: and then runs whatever follows. Every one of these is a prefix that any
#: ``^``-anchored command pattern stops seeing past.
ENV_PREFIX = re.compile(r"""^\s*[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|'[^']*'|\S*)\s+""")


def without_env_prefix(command: str) -> str:
    """``command`` with any leading environment assignments removed.

    A shell reads ``FOO=bar rm -rf /`` as *set FOO, then run* ``rm -rf /``.
    A regular expression anchored at ``^`` reads it as something that does not
    start with ``rm`` and lets it through -- which made ``FOO=bar rm -rf /``
    walk past ``shell.destructive_rm`` for as long as that rule has existed.
    The rule was not wrong about what it wanted; it was matching a string the
    shell does not agree with.

    Found by building the purpose gate, which asks an agent to write exactly
    such a prefix: a feature that documented the bypass would have turned a
    latent hole into a signposted one.
    """
    if not isinstance(command, str):
        return ""
    previous = None
    out = command
    # Repeatedly, because `A=1 B=2 rm -rf /` is as valid as one assignment.
    while previous != out:
        previous = out
        out = ENV_PREFIX.sub("", out, count=1)
    return out


#: Words that run the command following them. ``nohup rm -rf /`` is a prefix in
#: exactly the sense ``FOO=bar`` is, and an ``^``-anchored pattern stops seeing
#: past it the same way. ``timeout`` and ``xargs`` take arguments of their own,
#: so the duration or the flag is consumed too -- bounded, like every other
#: repetition in this module. The last alternative is an interpreter handed a
#: command as a string: once the quotes are off, ``sh -c sh -c rm -rf /`` peels
#: one level per pass, so nesting needs no depth limit to be seen through.
RUNNER_PREFIX = re.compile(
    r"""^\s*(?:
          (?:command|builtin|exec|env|nohup|setsid|stdbuf|time|nice|ionice)
        | (?:timeout|xargs|sudo|doas)
            (?:
                # An option that takes a VALUE, and its value. `sudo -u root
                # rm -rf /` used to reduce to `root rm -rf /`: the option was
                # consumed and the user name left standing in the command
                # position. Nothing was bypassed, because every rule shipped
                # today happens to tolerate a leading prefix -- which is the
                # `git --git-dir=.git push` accident again, a pattern passing
                # for the wrong reason. The next strictly-anchored rule would
                # not have been so lucky.
                #
                # The list is short and closed on purpose. Consuming the next
                # token after a VALUELESS option would be the worse bug:
                # `sudo -i rm -rf /` would reduce to `-rf /` and stop matching
                # anything at all.
                  \s+-[ugpCUrtDRhT]\s+\S{1,64}
                | \s+--(?:user|group|prompt|close-from|chdir|chroot|type|role)=\S{1,64}
                | \s+-\S{1,16}
                | \s+\d+(?:\.\d+)?[smhd]?
            ){0,4}
        | (?:(?:ba|z|k|da|fi)?sh|python[23]?(?:\.\d{1,2})?|perl|ruby|node)
            (?:\s+-\S{1,16}){0,3}\s+-[A-Za-z]{0,8}c
        | eval
      )\s+""",
    re.VERBOSE,
)

#: Most times the reductions below will peel a single command.
#:
#: Each pass rebuilds the string, so the loop is quadratic in the length of its
#: input -- and the input is whatever a model emitted. Twenty thousand stacked
#: `env` prefixes cost 71 ms on CPython 3.13 and nine to twenty seconds on
#: 3.10, a version this project supports; continuous integration failed on 3.10
#: alone while 3.11, 3.12 and 3.13 passed.
#:
#: Thirty-two is far past anything real. `sudo env nohup timeout 5 sh -c '...'`
#: is five deep, and a line needing more than thirty-two is not a command
#: somebody wrote.
MAX_REDUCTIONS = 32

#: A leading directory on the command word. A shell runs ``/bin/rm -rf /`` and
#: ``rm -rf /`` identically; a pattern anchored on ``rm`` sees only one of them.
COMMAND_PATH = re.compile(r"^\s*(?:/|\./|\.\./)\S{0,120}?/(?=[A-Za-z0-9_.-]{1,40}(?:\s|$))")

#: ``git``'s own options, which sit between the program and its subcommand.
#: Every rule in ``shell.yaml`` that watches git matches ``git`` followed
#: immediately by the subcommand, so all nine of them were walked past by
#: ``git -C . push --force``, ``git -c k=v reset --hard``,
#: ``git --no-pager clean -fd``. This is the ``sudo`` bug a third time -- that
#: one was fixed twice in two patterns, once in ``shell.destructive_rm`` and
#: again in ``shell.pipe_to_shell``, which is the argument for fixing it here
#: instead of in a tenth pattern: a program that takes options of its own
#: takes them whether or not a rule author remembered.
#:
#: Anchored, for two reasons that agree. By the time this runs the segment has
#: had its prefixes and its leading directory taken off, so the program name is
#: at the front -- and an unanchored pattern rescans the whole line on every
#: pass of the fixpoint below, which turned an adversarial line of fifty
#: thousand ``env`` prefixes from milliseconds into minutes. The two
#: transformations beside it are anchored and fail in constant time; this one
#: has to be as well.
GIT_GLOBAL_OPTION = re.compile(
    r"""^\s*git(?:\s+(?:
          (?:-[cC]|--exec-path|--git-dir|--work-tree|--namespace|--super-prefix)
            (?:=\S{1,120}|\s+\S{1,120})
        | --(?:no-pager|paginate|bare|no-replace-objects|literal-pathspecs
             |glob-pathspecs|noglob-pathspecs|icase-pathspecs
             |no-optional-locks|no-lazy-fetch)
        | -P
      )){1,6}(?=\s)""",
    re.VERBOSE,
)


def _segments(command: str) -> list[str]:
    """``command`` split where a shell would start a new command.

    Quote-aware, and that is the whole difficulty. A shell does not read the
    semicolon in ``git commit -m "fix; rm -rf /"`` as a separator, so neither
    does this: splitting there would invent a segment nobody is going to run
    and refuse an honest commit message for naming the command it fixes. A
    comment is dropped for the mirror-image reason -- the shell never runs it,
    so ``rm -rf / #cleanup`` is a reading of ``rm -rf /`` and nothing else.

    Every segment is returned. There is deliberately no cap: a "first N
    segments" window is a bypass with a published offset, which is the mistake
    that retired two earlier rules. Cost is linear in the length of the line
    and measured at roughly 3 ms per thousand segments, so the bound that
    matters is the one on the input.
    """
    out: list[str] = []
    current: list[str] = []
    quote: str | None = None
    index, length = 0, len(command)
    while index < length:
        char = command[index]
        if quote is not None:
            current.append(char)
            if char == "\\" and quote == '"' and index + 1 < length:
                current.append(command[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "'\"":
            quote = char
            current.append(char)
            index += 1
            continue
        if char == "\\" and index + 1 < length:
            # An escaped character is a literal, never syntax: `\;` is a
            # semicolon handed to the command, not a separator.
            current.append(char)
            current.append(command[index + 1])
            index += 2
            continue
        if command[index : index + 2] in ("&&", "||"):
            out.append("".join(current))
            current = []
            index += 2
            continue
        if char in ";\n|&":
            out.append("".join(current))
            current = []
            index += 1
            continue
        if char == "#" and (not current or current[-1].isspace()):
            while index < length and command[index] != "\n":
                index += 1
            continue
        current.append(char)
        index += 1
    out.append("".join(current))
    return [stripped for stripped in (segment.strip() for segment in out) if stripped]


def _as_the_shell_runs_it(segment: str) -> str:
    """``segment`` reduced to the command a shell will actually execute.

    Subshell punctuation, an environment prefix, a runner word, an interpreter
    taking the rest as a string, a backslash that only defeats an alias, a
    directory on the command word, and the quotes around an argument: seven
    spellings that change nothing about what runs and everything about what an
    anchored pattern sees. ``rm -rf '/'`` is the plainest of them -- two
    apostrophes, and the project's headline BLOCKER stopped firing.

    A fixpoint rather than a fixed number of passes, so ``sh -c 'sh -c "rm -rf
    /"'`` is peeled however deep it goes. It terminates because every branch
    either shortens the string or leaves it alone, and the loop exits on the
    first pass that changes nothing.

    **Bounded, because the input is the attacker's.** Each pass rebuilds the
    string, so a line of twenty thousand stacked ``env`` prefixes is quadratic
    in its length -- 71 ms on CPython 3.13 and **nine to twenty seconds on
    3.10**, which this project supports and which failed in continuous
    integration while the newer interpreters passed. A model can emit that
    line, and screening freezing for twenty seconds is the same availability
    defect as any other.

    Thirty-two is far past anything a shell is ever handed: ``sudo env nohup
    timeout 5 sh -c '...'`` is five. Past the bound the reductions stop and the
    readings collected so far are returned, so a pathological line costs a
    bounded amount of work and is still screened against everything peeled off
    it before the limit.
    """
    out = segment.strip()
    # Quotes and escapes first and once: they are about the arguments, and a
    # quoted runner word has to be unquoted before it can be recognised.
    out = out.replace("\\", "").replace('"', "").replace("'", "")
    previous = None
    passes = 0
    while previous != out and passes < MAX_REDUCTIONS:
        passes += 1
        previous = out
        out = out.strip().strip("(){}").strip()
        out = without_env_prefix(out)
        out = RUNNER_PREFIX.sub("", out, count=1)
        out = COMMAND_PATH.sub("", out, count=1)
        out = GIT_GLOBAL_OPTION.sub("git", out, count=1)
    return out.strip()


def shell_readings(command: str) -> list[str]:
    """Every string a shell would run, given ``command``.

    The engine screens all of them and a rule fires on any. This is the
    argument :func:`without_env_prefix` makes, carried to the rest of the
    syntax: a pattern anchored at ``^`` sees the start of the line, a shell
    sees the start of *each command on it*, and everything between those two
    readings was getting through. ``echo ok && rm -rf /`` walked past
    ``shell.destructive_rm``; so did ``rm -rf / && echo done``, whose end the
    closing ``$`` anchor never reached, and ``(rm -rf /)``, and
    ``/bin/rm -rf /``, and ``sh -c 'rm -rf /'``, and -- plainest of all --
    ``rm -rf '/'``.

    The anchors are not the bug and are not removed. ``$`` is what tells
    ``rm -rf /`` apart from ``rm -rf /home/me/project``; dropping it would
    trade a bypass for a rule that refuses every delete. Segmenting hands the
    anchor the single command it was always meant to be measuring.

    Every transformation **adds** a reading, and the typed string is always
    the first, so no detection that worked before can be weakened by this:
    the rule that wants to see the pipe, the assignment or the ``sudo`` still
    sees it.
    """
    if not isinstance(command, str) or not command:
        return []
    readings: list[str] = [command]
    seen = {command}

    def remember(candidate: str) -> None:
        if candidate and candidate not in seen:
            seen.add(candidate)
            readings.append(candidate)

    remember(without_env_prefix(command))
    for segment in _segments(command):
        remember(segment)
        remember(_as_the_shell_runs_it(segment))
    return readings
