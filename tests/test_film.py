"""
The launch film, and the gate that keeps its closing line true.

The film ends on *"every number in this film is in the repository, and a test
fails when one of them drifts"*. For the first week of its existence there was
no such test. `video/film.yaml` declared the claims and named the file that
decides each one, and the only thing that read it was a command typed by hand
on a machine that happened to have `make-film` installed -- not a dependency of
this package, not a step in the lane, not reachable from `pytest`.

So the film shipped making a promise about gates, with no gate. That is the
third occurrence here of a claim with no check behind it, after `py.typed`
against twenty-five `mypy` errors and `pytest-cov` against a coverage figure
nobody had measured, and it landed in a directory created the same week the
other two were written up.

`scripts/lint_film.py` is the answer, and this file is what makes it one: the
four checks run against the real film, and each is then fed the regression it
exists to catch. A gate nobody has seen fail is a gate nobody should trust --
the same argument `tests/test_figures.py` makes for the figure audit.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

#: Interpreter-independent: a YAML spec against the files it names.
#: See `markers` in pyproject.toml — this module runs once, on the newest.
pytestmark = pytest.mark.gate

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("lint_film", ROOT / "scripts" / "lint_film.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["lint_film"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    return _load()


# --------------------------------------------------------------------------
# The real film.
# --------------------------------------------------------------------------


def test_every_claim_the_film_makes_still_holds(guard):
    """The `verify` half: each claim, read out of the file that decides it."""
    assert guard.claims_that_drifted() == []


def test_every_figure_on_screen_is_declared(guard):
    """The `scan` half, which is the one that catches a number nobody sourced.

    It found three the first pass had left: the incident date -- on screen as
    "25 September 2026" and in the README as `2026-09-25`, so no literal search
    for the film's own wording could have found it -- the card, and the size of
    the coder that asking for pictures displaces.
    """
    assert guard.numbers_nobody_declared() == []


def test_every_beat_is_cut_to_the_measured_length_of_its_narration(guard):
    """The claim the composition's own comment makes about itself.

    Each boundary is supposed to be the end of a spoken line as measured in the
    WebVTT beside the audio, rather than a guess. That was true when it was
    written and nothing kept it true: Kokoro does not promise the same waveform
    across versions, so regenerating the voice moves every cue and desynchronises
    a film that still renders perfectly.
    """
    assert guard.cuts_that_left_the_narration() == []


def test_every_asset_the_render_feeds_on_is_on_disk(guard):
    assert guard.assets_that_vanished() == []


def test_the_spec_names_a_source_for_every_claim_and_a_reason_for_every_label(guard):
    """The escape hatch, kept narrow.

    `labels` is how a figure that is an ordinal rather than a quantity stays
    out of the scan. Without a required reason it becomes the place numbers go
    to stop being checked, which is the failure the scan was written against.
    """
    document = guard.spec()
    assert document["claims"], "a spec with no claims gates nothing"
    for claim in document["claims"]:
        assert set(claim["source"]) >= {"path", "method", "selector"}
        assert claim["source"]["method"] in {"literal", "regex_count"}
    for entry in document.get("labels", []):
        assert entry["why"].strip(), f"label {entry['shown']!r} is unexplained"


# --------------------------------------------------------------------------
# And the proof that each check can go red.
# --------------------------------------------------------------------------


def test_the_guard_catches_a_claim_whose_source_moved_on(guard, monkeypatch):
    """The regression that will actually happen.

    `scripts/sync_counts.py` rewrites the test count in the README from what
    pytest collects. The day it writes 1,160 there, the film still says 1,140
    and renders perfectly.
    """
    monkeypatch.setattr(
        guard,
        "spec",
        lambda: {
            "claims": [
                {
                    "text": "1,140 tests",
                    "value": "1140 tests, `ruff` clean",
                    "source": {
                        "path": "README.md",
                        "method": "literal",
                        "selector": "1140000 tests, `ruff` clean",
                    },
                }
            ]
        },
    )
    problems = guard.claims_that_drifted()
    assert len(problems) == 1
    assert "no longer contains" in problems[0]


def test_the_guard_catches_a_count_that_changed(guard, monkeypatch):
    """A fifth stage added to the pipeline, with the film still saying four."""
    monkeypatch.setattr(
        guard,
        "spec",
        lambda: {
            "claims": [
                {
                    "text": "a turn crosses the gateway four times",
                    "value": 99,
                    "source": {
                        "path": "scripts/make_figures.py",
                        "method": "regex_count",
                        "selector": r'\("0[1-9]", "(?:orange|blue)", \d+,',
                    },
                }
            ]
        },
    )
    problems = guard.claims_that_drifted()
    assert len(problems) == 1
    assert "the film says 99" in problems[0]


def test_the_guard_refuses_a_method_it_does_not_implement(guard, monkeypatch):
    """A check that silently does nothing is the defect this file is about."""
    monkeypatch.setattr(
        guard,
        "spec",
        lambda: {
            "claims": [
                {
                    "text": "anything",
                    "value": "anything",
                    "source": {"path": "README.md", "method": "vibes", "selector": "x"},
                }
            ]
        },
    )
    assert guard.claims_that_drifted() == ["'anything': unknown method 'vibes'"]


def test_the_scan_catches_a_number_typed_straight_into_a_keyframe(guard, monkeypatch, tmp_path):
    """The one a reviewer cannot catch by reading the spec.

    Somebody edits the composition at midnight, writes a throughput figure into
    a card, and every other check stays green: the claims still hold, the cuts
    still line up, the assets are all there.
    """
    composition = tmp_path / "index.html"
    composition.write_text(
        '<section class="scene clip" data-start="0" data-duration="1">'
        "<p>Serving 94,000 tokens a second.</p></section>",
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "COMPOSITION", composition)
    monkeypatch.setattr(guard, "spec", lambda: {"claims": [], "labels": []})
    problems = guard.numbers_nobody_declared()
    assert len(problems) == 1
    assert "'94,000' is on screen and in no claim" in problems[0]


def test_the_scan_accepts_a_number_a_claim_states_in_prose(guard, monkeypatch, tmp_path):
    """And the other direction, so the scan is not merely strict.

    Thousands separators are normalised away: `40,433` on screen and `40433`
    in a source file are one number, which is the whole reason a spec exists
    between them.
    """
    composition = tmp_path / "index.html"
    composition.write_text('<section class="clip"><p>40,433 tokens</p></section>', encoding="utf-8")
    monkeypatch.setattr(guard, "COMPOSITION", composition)
    monkeypatch.setattr(
        guard,
        "spec",
        lambda: {"claims": [{"text": "the overflow", "value": "40433 tokens"}]},
    )
    assert guard.numbers_nobody_declared() == []


def test_the_scan_ignores_lengths_hidden_in_a_stylesheet(guard, monkeypatch, tmp_path):
    """A CSS pixel is not a claim, and a scan that says it is gets deleted."""
    composition = tmp_path / "index.html"
    composition.write_text(
        "<style>.tag { left: 700px; letter-spacing: -0.035em }</style>"
        '<!-- 42 in a comment --><section class="clip"><p>nothing numeric</p></section>',
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "COMPOSITION", composition)
    monkeypatch.setattr(guard, "spec", lambda: {"claims": []})
    assert guard.numbers_nobody_declared() == []


def test_the_guard_catches_a_cut_that_drifted_from_its_narration(guard, monkeypatch, tmp_path):
    """Regenerate the voice, keep the cut: the exact silent desynchronisation.

    Beat two is left starting where the old cue ended, a tenth of a second
    before the new one, which is enough to clip the first word and far too
    little for anyone to notice in a spec file.
    """
    composition = tmp_path / "index.html"
    composition.write_text(
        '<div data-composition-id="main" data-duration="20">'
        '<section id="beat1" class="scene clip" data-start="0" data-duration="10"></section>'
        '<section id="beat2" class="scene clip" data-start="10" data-duration="10"></section>'
        "</div>",
        encoding="utf-8",
    )
    narration = tmp_path / "narration.vtt"
    narration.write_text(
        "WEBVTT\n\n1\n00:00:00.000 --> 00:00:10.100\nfirst\n\n"
        "2\n00:00:10.100 --> 00:00:20.000\nsecond\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(guard, "COMPOSITION", composition)
    monkeypatch.setattr(guard, "NARRATION", narration)
    problems = guard.cuts_that_left_the_narration()
    assert any("beat1 ends at 10s" in p for p in problems)
    assert any("beat2 starts at 10s" in p for p in problems)


def test_the_guard_catches_a_beat_with_no_line_to_speak(guard, monkeypatch, tmp_path):
    """A ninth beat added and no ninth cue recorded."""
    composition = tmp_path / "index.html"
    composition.write_text(
        '<div data-composition-id="main" data-duration="10">'
        '<section id="beat1" class="clip" data-start="0" data-duration="5"></section>'
        '<section id="beat2" class="clip" data-start="5" data-duration="5"></section>'
        "</div>",
        encoding="utf-8",
    )
    narration = tmp_path / "narration.vtt"
    narration.write_text("WEBVTT\n\n1\n00:00:00.000 --> 00:00:05.000\nonly one\n", encoding="utf-8")
    monkeypatch.setattr(guard, "COMPOSITION", composition)
    monkeypatch.setattr(guard, "NARRATION", narration)
    assert guard.cuts_that_left_the_narration() == [
        "2 beat(s) in the composition against 1 narration cue(s)"
    ]


def test_the_guard_lets_the_last_beat_hold_its_closing_frame(guard, monkeypatch, tmp_path):
    """The one asymmetry, and why it is there.

    Every beat but the last ends where the next line begins. The last has no
    next line, so it is allowed to run on past the final word -- the film holds
    "Count. Don't estimate." for about a second after the voice stops -- and
    only a cut that ends *early*, truncating a word, is a failure.
    """
    composition = tmp_path / "index.html"
    composition.write_text(
        '<div data-composition-id="main" data-duration="12">'
        '<section id="beat1" class="clip" data-start="0" data-duration="12"></section></div>',
        encoding="utf-8",
    )
    narration = tmp_path / "narration.vtt"
    narration.write_text("WEBVTT\n\n1\n00:00:00.000 --> 00:00:11.000\nheld\n", encoding="utf-8")
    monkeypatch.setattr(guard, "COMPOSITION", composition)
    monkeypatch.setattr(guard, "NARRATION", narration)
    assert guard.cuts_that_left_the_narration() == []

    narration.write_text("WEBVTT\n\n1\n00:00:00.000 --> 00:00:13.000\nclipped\n", encoding="utf-8")
    problems = guard.cuts_that_left_the_narration()
    assert any("before its last word" in p for p in problems)


def test_the_guard_catches_an_asset_that_left_the_tree(guard, monkeypatch):
    monkeypatch.setattr(
        guard, "spec", lambda: {"assets": [{"rel": "assets/figure-that-never-was.svg"}]}
    )
    problems = guard.assets_that_vanished()
    assert len(problems) == 1
    assert "is declared in film.yaml and is not in video/film/" in problems[0]
