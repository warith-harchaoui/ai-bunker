"""
The claim-drift guard, and its ability to fail.

`scripts/lint_claims.py` exists because `sync_counts.py` solves this problem
for figures and nothing solved it for claims. A stale test count is cosmetic;
a stale security claim is the product lying about itself, and the published
site advertised a closed hole for five commits because seven files were
corrected and two were missed.

A gate nobody has seen fail is a gate nobody should trust, so the tests here
feed it the real regression as well as the real repository.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

#: Interpreter-independent: a claim is a phrase in a file; no interpreter reads it differently.
#: See `markers` in pyproject.toml — this module runs once, on the newest.
pytestmark = pytest.mark.gate

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "lint_claims", ROOT / "scripts" / "lint_claims.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["lint_claims"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    return _load()


def test_the_repository_states_every_guarded_claim_consistently(guard):
    problems = guard.check()
    assert problems == [], "\n".join(problems)


def test_the_guard_catches_the_regression_that_actually_shipped(guard, tmp_path, monkeypatch):
    """The site said "Command screening does not apply to streamed completions"
    after it had stopped being true. That is the payload."""
    page = tmp_path / "start.en.py"
    page.write_text(
        "BODY = 'Command screening does not apply to streamed completions.'",
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(
        guard,
        "CLAIMS",
        (
            guard.Claim(
                name="streaming-is-screened",
                because="the one that shipped",
                forbidden=("Command screening does not apply",),
                files=("start.en.py",),
            ),
        ),
    )
    problems = guard.check()
    assert len(problems) == 1
    assert "start.en.py" in problems[0]
    assert "streaming-is-screened" in problems[0]


def test_a_withdrawn_claim_is_not_a_stale_one(guard, tmp_path, monkeypatch):
    """A struck-through sentence is a record of a claim, not the claim.

    The first version of this guard flagged all three of those and had a 100%
    false-positive rate on its first run -- which is how a checker teaches
    people to ignore it, the same reasoning `global.generic_secret` already
    carries for the word `example`.
    """
    page = tmp_path / "README.md"
    page.write_text(
        "- ~~Command screening does not apply to a stream.~~ **Closed in 0.2.0.**",
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(
        guard,
        "CLAIMS",
        (
            guard.Claim(
                name="streaming-is-screened",
                because="x",
                forbidden=("Command screening does not apply",),
                files=("README.md",),
            ),
        ),
    )
    assert guard.check() == []


def test_a_claim_nobody_states_is_reported(guard, tmp_path, monkeypatch):
    """`required_somewhere` is the other half: a position nothing states is one
    a reader cannot check, and silence is how a closed limitation becomes
    invisible rather than corrected."""
    (tmp_path / "README.md").write_text("nothing relevant here", encoding="utf-8")
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(
        guard,
        "CLAIMS",
        (
            guard.Claim(
                name="streaming-is-screened",
                because="x",
                required_somewhere=("screening applies to streamed",),
                files=("README.md",),
            ),
        ),
    )
    problems = guard.check()
    assert len(problems) == 1
    assert "nothing states the current position" in problems[0]


def test_the_changelog_is_not_policed(guard):
    """It records what was true on the day it was written, by the same rule
    that keeps it out of `sync_counts.SOURCES`. Rewriting a released entry
    turns a record into a false statement, which is worse than the drift this
    guard catches."""
    assert "CHANGELOG.md" not in guard.PROSE
    assert "CHANGELOG.md" in (ROOT / "CHANGELOG.md").name


def test_every_guarded_claim_explains_itself(guard):
    """A registry entry with no reason is one nobody can judge, and the next
    person to hit it will delete it rather than ask."""
    for claim in guard.CLAIMS:
        assert claim.because.strip(), claim.name
        assert claim.forbidden or claim.required_somewhere, claim.name


def test_every_registered_claim_can_actually_be_broken(guard, monkeypatch):
    """The figure audit's harness, pointed at the claim linter.

    Round 36 broke the committed figures on purpose and the two mutations
    that slipped through led to a caption running off the canvas for half the
    world's browsers. This is the same question asked of the other gate that
    reads prose: is every claim in the register one this script can actually
    catch somebody contradicting?

    Two mutations per claim, both in memory so no file is touched. Each
    forbidden phrase is appended to the first file the claim guards, and the
    claim's name has to come back. Then every required phrase is deleted from
    everywhere, and the name has to come back again.

    It found nothing: fourteen planted phrases, eight stripped requirements,
    no misses. That is worth keeping rather than worth celebrating — what it
    locks is the mistake nobody has made yet, a claim registered with a
    phrase that cannot match anything, which would sit in the register
    looking like protection and be none.
    """
    real_read = guard._read
    assert guard.check() == [], "the repository is not clean; this measures nothing"

    deaf: list[str] = []
    planted = 0

    for claim in guard.CLAIMS:
        target = claim.files[0]

        for phrase in claim.forbidden:

            def planted_read(relative, _phrase=phrase, _target=target):
                text = real_read(relative)
                if text is None:
                    return None
                return f"{text}\n{_phrase}\n" if relative == _target else text

            monkeypatch.setattr(guard, "_read", planted_read)
            reported = guard.check()
            monkeypatch.setattr(guard, "_read", real_read)
            planted += 1
            if not any(claim.name in line for line in reported):
                deaf.append(f"{claim.name}: {phrase[:48]!r} planted in {target}, not reported")

        if claim.required_somewhere:

            def stripped_read(relative, _claim=claim):
                text = real_read(relative)
                if text is None:
                    return None
                for phrase in _claim.required_somewhere:
                    text = text.replace(phrase, "")
                return text

            monkeypatch.setattr(guard, "_read", stripped_read)
            reported = guard.check()
            monkeypatch.setattr(guard, "_read", real_read)
            planted += 1
            if not any(claim.name in line for line in reported):
                deaf.append(f"{claim.name}: every required phrase removed, not reported")

    assert planted >= 20, f"only {planted} mutations; this stopped exercising the register"
    assert not deaf, (
        "a claim is registered that this script cannot catch anybody contradicting, "
        f"so it is protection in name only: {deaf}"
    )
