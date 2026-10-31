"""
The handoff files, and the one document in this repository with no gate.

Every claim here is read by something. Figures by `sync_counts.py`, sentences
by `lint_claims.py`, abbreviations by `lint_acronyms.py`, the launch film by
`lint_film.py`, the pictures by `audit_figures.py`, the published test count by
`test_site.py`. A handoff file is read by a person and then believed — the most
credited document in the repository and, until now, the least checked.

The cost was paid in a sibling project, not here. One of its sessions read
"ai-bunker reads this engine descriptor" out of its own handoff, built seven
iterations on the premise, and published the reason in a released changelog —
without once opening this repository, where the only mention of that
descriptor is a line in `.gitignore`.

And this repository's handoff failed the same way inside the hour. Round 32
renamed `measure_advances.py` to `scripts/measure_type.py`, and all three live
handoff files — written *after* the rename — still sent the next session to the
old name. Six references across three files, none of which resolved.

`.private/` is not committed, so in continuous integration there is nothing to
read and the gate says so. Which is exactly why the tests below feed it
synthetic handoffs: the real files are absent in the lane, so the gate's
ability to fail has to be proven without them.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "lint_handoff", ROOT / "scripts" / "lint_handoff.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["lint_handoff"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def guard():
    return _load()


@pytest.fixture
def handoff(guard, tmp_path, monkeypatch):
    """A synthetic `.private/` the guard reads instead of the real one."""
    notes = tmp_path / ".private"
    notes.mkdir()
    monkeypatch.setattr(guard, "NOTES", notes)

    def write(text: str, name: str = "die.md") -> None:
        (notes / name).write_text(text, encoding="utf-8")

    return write


# --------------------------------------------------------------------------
# The real handoff, when it is here.
# --------------------------------------------------------------------------


def test_the_live_handoff_still_describes_this_repository(guard):
    """Skipped in the lane, and that is the point rather than an evasion:
    `.private/` is working memory between sessions and is not committed, so
    there is nothing to read. The tests below are what run there."""
    if not guard.notes():
        pytest.skip(".private/ is not on this machine; the planted cases below cover the gate")
    problems = guard.check()
    assert problems == [], "\n".join(problems)


def test_an_archive_is_not_a_handoff(guard):
    """`thread.md` predates this convention and names files that have since
    moved to the website's own repository. It is left alone for the same
    reason `lint_claims.py` keeps `CHANGELOG.md` out of its file list: it
    records what was true when it was written, and editing it to satisfy a
    linter would turn a record into a false statement."""
    assert "thread.md" not in guard.LIVE
    assert set(guard.LIVE) == {"die.md", "fil.md", "ASSESSMENTS.md"}


# --------------------------------------------------------------------------
# And the regressions that actually happened.
# --------------------------------------------------------------------------


def test_the_guard_catches_the_rename_that_actually_shipped(guard, handoff):
    """The payload: round 32 renamed the measurer and then wrote the old name
    into the file that tells the next session what to run."""
    handoff("- `measure_advances.py` et `measure_ratio.py` sont des mesures\n")
    problems = guard.dead_paths()
    assert len(problems) == 1
    assert "measure_advances.py" in problems[0]
    assert "name the current file" in problems[0]

    handoff("- `scripts/measure_type.py` et `measure_ratio.py` sont des mesures\n")
    assert guard.dead_paths() == []


def test_a_bare_basename_is_resolved_by_searching(guard, handoff):
    """Prose names a file whose directory the reader already knows —
    `ci.yml`, `pipeline.py`. Demanding the full path everywhere would make a
    handoff unreadable and buy nothing."""
    handoff("the lane is `ci.yml` and the gateway is `pipeline.py`\n")
    assert guard.dead_paths() == []


def test_a_render_pattern_is_a_claim_about_a_directory(guard, handoff):
    """`video/film/renders/*.mp4` points at whatever was rendered, not at one
    file, and the first version of this reported it as missing."""
    handoff("| Rendu | `video/film/renders/*.mp4` — 1 min 54 s |\n")
    assert guard.dead_paths() == []

    handoff("| Rendu | `video/film/renders/*.mov` |\n")
    assert len(guard.dead_paths()) == 1


def test_a_function_written_with_its_module_is_not_a_path(guard, handoff):
    """`adopt.without_site()` is a symbol. A checker that reported a reader's
    shorthand would be deleted within a round, which would cost more than the
    one real finding it buys."""
    handoff("- `ai_bunker/adopt.without_site()` fige la réponse\n")
    assert guard.dead_paths() == []


def test_an_identifier_in_backticks_is_left_alone(guard, handoff):
    """A handoff is mostly backticked identifiers. None of these is a file."""
    handoff("`served_context`, `max_output`, `CAP_HEIGHT`, `--check`, `main`\n")
    assert guard.dead_paths() == []


def test_the_guard_catches_a_commit_nothing_resolves(guard, handoff):
    """A transposed character in a hash gives a reference the next session
    cannot follow, and `git log` will not tell them why."""
    handoff("| Dernier commit | `deadbee` — la borne verticale |\n")
    problems = guard.unknown_commits()
    assert len(problems) == 1
    assert "deadbee" in problems[0]


def test_a_commit_this_checkout_has_is_accepted(guard, handoff):
    import subprocess

    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    handoff(f"| Dernier commit | `{head}` |\n")
    assert guard.unknown_commits() == []


def test_the_guard_catches_a_line_number_past_the_end_of_the_file(guard, handoff):
    """`die.md` sends the next session to `ai_bunker/budget.py` "around line
    655" — the most perishable sentence a handoff can carry. The cheap half is
    decidable: a line past the end of the file is certainly wrong."""
    handoff("Lis `ai_bunker/budget.py` autour de la ligne 999999 avant de commencer.\n")
    problems = guard.stale_line_numbers()
    assert len(problems) == 1
    assert "999999" in problems[0]

    handoff("Lis `ai_bunker/budget.py` autour de la ligne 10 avant de commencer.\n")
    assert guard.stale_line_numbers() == []


def test_a_missing_private_directory_is_not_a_failure(guard, monkeypatch, tmp_path):
    """The lane has no `.private/`, and a gate that is permanently red is a
    gate nobody reads."""
    monkeypatch.setattr(guard, "NOTES", tmp_path / "nowhere")
    assert guard.notes() == []
    assert guard.check() == []
    assert guard.main([]) == 0
