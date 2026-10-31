#!/usr/bin/env python3
"""
Hold the handoff files to the repository they describe.

Why
---
`.private/die.md`, `fil.md` and `ASSESSMENTS.md` are how one session hands work
to the next. They are the most *credited* documents in this repository and the
only ones with no gate at all: every other claim here is read by something —
figures by `sync_counts.py`, sentences by `lint_claims.py`, abbreviations by
`lint_acronyms.py`, the film by `lint_film.py`, the pictures by
`audit_figures.py`. A handoff is read by a person and then believed.

The cost is not hypothetical and it was not paid here. A sibling project's
session read *"ai-bunker reads this engine descriptor"* out of its own handoff
file, built seven iterations of work on that premise, and published the
reason in a released changelog — without once opening this repository, where
the only mention of that descriptor is a line in `.gitignore`. A false reason
attached to correct work is the hardest kind to find later.

And this file's own handoff failed the same way within the hour. Round 32
renamed `measure_advances.py` to `measure_type.py`; `die.md` and `fil.md`,
written *after* the rename, still sent the next session to the old name.

So the rule, and it is deliberately crude:

**A path in backticks must exist.** A file that was renamed gets described in
prose and the *current* name in the literal — "renamed to
`scripts/measure_type.py`", never "`measure_advances.py` was renamed". One
rule, one failure mode, nothing to negotiate with a reader.

Plus the two other things in a handoff that rot on their own: a commit it
names must be reachable, and a line number it sends somebody to must be inside
the file.

What is deliberately NOT here
-----------------------------
Figures. The test count in the state table is owned by `sync_counts.py`, like
every other quoted number in this repository — one owner per figure, and a
second guard reading the same number is a second place for them to disagree.

    python3 scripts/lint_handoff.py          # report
    python3 scripts/lint_handoff.py --list   # what is being read

`.private/` is not committed, so this has nothing to read in continuous
integration and says so rather than failing. `tests/test_handoff.py` feeds it
synthetic handoffs, so the gate's ability to fail is proven where the real
files are absent.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Where the handoff lives. Outside the commit on purpose: it is working
#: memory between sessions, not a published document.
NOTES = ROOT / ".private"

#: The files that are *live* working memory, and only those.
#:
#: `.private/` also holds `thread.md`, an archive from before this convention
#: existed. It names files that have since moved to the website's own
#: repository, and it is left alone for the same reason `lint_claims.py` keeps
#: `CHANGELOG.md` out of its file list: it records what was true on the day it
#: was written, and editing it to satisfy a linter would turn a record into a
#: false statement. A record is not a handoff.
LIVE = ("die.md", "fil.md", "ASSESSMENTS.md")

#: Anything in backticks.
TICKED = re.compile(r"`([^`\n]+)`")

#: A ticked token is treated as a repository path when it carries one of these
#: suffixes, or names one of the directories below. Narrow on purpose: a
#: handoff is full of backticked identifiers (`served_context`, `max_output`)
#: and a checker that guessed at those would cry wolf until somebody deleted
#: it.
SUFFIXES = (".py", ".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".svg", ".html", ".csv")
DIRECTORIES = ("ai_bunker/", "scripts/", "tests/", "assets/", "charter/", "config/", "video/")

#: Outside this repository, so not this checker's business: a home-relative
#: path, an absolute one, a URL, or a command with an argument.
FOREIGN = ("~", "/", "http", " ")

#: A line number a handoff sends somebody to, in either language.
LINE_REFERENCE = re.compile(r"(?:ligne|line)\s+(\d+)")

#: A commit, as a handoff writes one.
COMMIT = re.compile(r"`([0-9a-f]{7,40})`")


def notes() -> list[Path]:
    """The live handoff files, or nothing when they are not on this machine."""
    return [path for name in LIVE if (path := NOTES / name).is_file()]


def _looks_like_a_path(token: str) -> bool:
    """Whether a backticked token is making a claim about a file.

    `(` excludes a symbol written with its module -- `adopt.without_site()` is
    a function, not a path, and reporting it would be reporting a reader's
    shorthand. A handoff is mostly backticked identifiers, so this stays
    narrow: a checker that cried wolf here would be deleted within a round.
    """
    if token.startswith(FOREIGN) or " " in token or "(" in token:
        return False
    return token.endswith(SUFFIXES) or token.startswith(DIRECTORIES)


def _resolves(token: str) -> bool:
    """Whether a ticked path names something in this repository.

    A full relative path is checked as written; a pattern with `*` is matched,
    because a handoff legitimately points at `video/film/renders/*.mp4` rather
    than at one render. A bare basename -- `ci.yml`, `pipeline.py`, the way
    prose names a file whose directory the reader already knows -- is resolved
    by searching, because requiring the full path everywhere would make a
    handoff unreadable to buy nothing.
    """
    if "*" in token:
        return any(ROOT.glob(token))
    if (ROOT / token).exists():
        return True
    if "/" in token:
        return False
    found = [
        p
        for p in ROOT.rglob(token)
        if ".git" not in p.parts and "node_modules" not in p.parts and "__pycache__" not in p.parts
    ]
    return bool(found)


def dead_paths() -> list[str]:
    """Paths a handoff names that are not in the repository any more."""
    problems = []
    for note in notes():
        for number, line in enumerate(note.read_text(encoding="utf-8").splitlines(), 1):
            for token in TICKED.findall(line):
                if _looks_like_a_path(token) and not _resolves(token):
                    problems.append(
                        f"{note.name}:{number}: `{token}` is not in the repository — "
                        f"name the current file, and put the old name in prose"
                    )
    return problems


def unknown_commits() -> list[str]:
    """Commits a handoff names that this checkout has never seen.

    Reachability from `HEAD` is deliberately not required: a handoff written
    on a branch that was later rebased names commits that still exist and are
    no longer ancestors, and reporting those would be reporting history rather
    than a defect. Existence is the claim worth checking — a transposed
    character gives a hash nothing resolves.
    """
    problems = []
    for note in notes():
        for number, line in enumerate(note.read_text(encoding="utf-8").splitlines(), 1):
            for sha in COMMIT.findall(line):
                known = subprocess.run(
                    ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                    cwd=ROOT,
                    capture_output=True,
                    check=False,
                )
                if known.returncode != 0:
                    problems.append(f"{note.name}:{number}: no commit {sha} in this checkout")
    return problems


def stale_line_numbers() -> list[str]:
    """A line number past the end of the file it points into.

    `die.md` sends the next session to `ai_bunker/budget.py` "around line 655".
    That is the most perishable sentence a handoff can contain -- the line
    moves on the next edit above it -- and the cheap half is checkable: a
    number past the end of the file is certainly wrong.
    """
    problems = []
    for note in notes():
        for number, line in enumerate(note.read_text(encoding="utf-8").splitlines(), 1):
            reference = LINE_REFERENCE.search(line)
            if reference is None:
                continue
            target = next(
                (t for t in TICKED.findall(line) if _looks_like_a_path(t) and t.endswith(".py")),
                None,
            )
            if target is None or not (ROOT / target).exists():
                continue
            length = len((ROOT / target).read_text(encoding="utf-8").splitlines())
            wanted = int(reference.group(1))
            if wanted > length:
                problems.append(
                    f"{note.name}:{number}: points at {target} line {wanted}; "
                    f"the file is {length} lines"
                )
    return problems


def check() -> list[str]:
    return dead_paths() + unknown_commits() + stale_line_numbers()


def main(argv: list[str] | None = None) -> int:
    """`argv` is a parameter rather than `sys.argv` so a test can call this.

    `sync_counts.py` takes one for the same reason: a `main` that reads the
    process arguments cannot be exercised from inside a test runner, whose
    arguments it would try to parse.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--list", action="store_true", help="print what is being read")
    args = parser.parse_args(argv)

    found = notes()
    if args.list:
        for note in found:
            print(f"{note.relative_to(ROOT)}  {len(note.read_text(encoding='utf-8')):,} bytes")
        print(f"\n{len(found)} handoff file(s)")
        return 0

    if not found:
        print(".private/ is not on this machine; nothing to read")
        return 0

    problems = check()
    for problem in problems:
        print(problem)
    if problems:
        print(f"\n{len(problems)} problem(s) in the handoff: the next session would be misled")
        return 1
    print(f"every path, commit and line number in {len(found)} handoff file(s) still resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
