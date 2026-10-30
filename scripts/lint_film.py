#!/usr/bin/env python3
"""
Hold the launch film to the repository it makes claims about.

Why
---
The film's closing line is *"every number in this film is in the repository,
and a test fails when one of them drifts"*. That sentence is on screen for
seven seconds and it was, until this file existed, **false** -- not because any
number was wrong, but because nothing failed. `video/film.yaml` declares
sixteen claims and names the file that decides each one; the tool that reads it
(`make-film verify`) was run by hand, once, from a laptop that had it
installed. The lane never ran it, `pyproject.toml` never declared it, and the
suite never touched `video/` at all.

That is the third time this repository has shipped a claim with no gate behind
it -- `py.typed` against twenty-five `mypy` errors, `pytest-cov` against a
coverage figure nobody had measured -- and this one arrived in a directory
created the same week two tests were written about exactly that failure mode.
Hence a gate with no dependency outside what the package already installs, so
that there is no version of this repository where the film is unguarded.

What is checked
---------------
Four things, in the order they go wrong:

1. **Drift.** Every claim in `film.yaml` still holds in the file it names.
   `1,140 tests` on screen stops being true the moment `sync_counts.py`
   rewrites the README to say 1,160, and this is what notices.
2. **Numbers nobody declared.** The scan runs the other way: every figure
   rendered in the composition must be accounted for by a claim. This is the
   half that catches the number typed straight into a keyframe, and it caught
   three -- the incident date, the card, and the size of the coder it displaces
   -- that the first pass left on screen with nothing behind them.
3. **A cut that left its narration.** Every beat boundary is supposed to be
   the *measured* end of a spoken line, read out of the WebVTT that
   `sprezzature-audio` wrote beside the audio. Kokoro does not promise the same
   waveform across versions, so regenerating the voice moves every boundary and
   the film silently desynchronises. The composition and the VTT are compared
   cue by cue.
4. **An asset that vanished.** Everything `film.yaml` lists as feeding the
   render has to be on disk.

What is deliberately NOT checked
--------------------------------
Contrast and layout inside the frames: `make-film check` owns those, it needs a
browser, and a browser is not a thing to put in a lane for this. The four
checks here are the ones that can be made from text, which is why they can be
made every time.

    python3 scripts/lint_film.py          # report
    python3 scripts/lint_film.py --list   # what is guarded, and from where

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

SPEC = ROOT / "video" / "film.yaml"
TREE = ROOT / "video" / "film"
COMPOSITION = TREE / "index.html"
NARRATION = TREE / "narration" / "narration.vtt"

#: Cuts are compared in seconds, and both sides are written to the millisecond.
#: Half a millisecond is below what either format can express, so a difference
#: at or above it is a real edit rather than a rounding artefact.
TOLERANCE = 0.0005

#: A figure on screen, as the scan sees it: digits, then anything that can
#: appear inside one. Trailing separators are stripped afterwards, so `2026.`
#: at the end of a sentence and `H100,` before a comma both normalise to the
#: number a claim would state.
NUMBER = re.compile(r"\d[\d,.]*")


def _number_tokens(text: str) -> set[str]:
    """The figures in a string, with thousands separators removed.

    Commas go and the digits stay, so `40,433` in prose and `40433` in code are
    the same claim. Trailing punctuation is stripped rather than parsed: the
    point is to recognise a number, not to evaluate it.
    """
    out = set()
    for raw in NUMBER.findall(text):
        token = raw.rstrip(".,").replace(",", "")
        if token:
            out.add(token)
    return out


def spec() -> dict:
    """`video/film.yaml`, parsed."""
    return yaml.safe_load(SPEC.read_text(encoding="utf-8"))


def visible_text(html: str) -> str:
    """What a viewer reads, out of the composition's markup.

    `<script>` and `<style>` go whole -- a CSS length is not a claim -- and
    every remaining tag becomes a space so that two words either side of a
    `<em>` do not weld together.
    """
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))


def claims_that_drifted() -> list[str]:
    """Every claim, read out of the file that decides it.

    Two methods, which is all `film.yaml` uses and all it should: a `literal`
    is a phrase that must still be in the file, and a `regex_count` is a
    pattern whose number of matches must still be the number the film states.
    An unknown method is reported rather than skipped -- a check that quietly
    does nothing is the failure this whole file is about.
    """
    problems = []
    for claim in spec()["claims"]:
        source = claim["source"]
        path = ROOT / source["path"]
        shown = claim["text"]
        if not path.exists():
            problems.append(f"{shown!r}: {source['path']} does not exist")
            continue
        text = path.read_text(encoding="utf-8")
        method = source["method"]
        if method == "literal":
            if source["selector"] not in text:
                problems.append(
                    f"{shown!r}: {source['path']} no longer contains {source['selector']!r}"
                )
        elif method == "regex_count":
            found = len(re.findall(source["selector"], text))
            expected = int(claim["value"])
            if found != expected:
                problems.append(
                    f"{shown!r}: {source['path']} matches {source['selector']!r} "
                    f"{found} time(s), the film says {expected}"
                )
        else:
            problems.append(f"{shown!r}: unknown method {method!r}")
    return problems


def numbers_nobody_declared() -> list[str]:
    """Figures rendered in the film that no claim accounts for.

    The declared set is built from the claims themselves -- their `text` and
    their `value` -- so declaring a number and stating it are the same act.
    `labels` is the narrow escape for a figure that is an ordinal rather than a
    quantity, and it is narrow on purpose: adding a fifth stage to the diagram
    puts `05` on screen and turns this red, which is the correct answer.
    """
    document = spec()
    declared: set[str] = set()
    for claim in document["claims"]:
        declared |= _number_tokens(f"{claim['text']} {claim['value']}")
    declared |= {str(entry["shown"]) for entry in document.get("labels", [])}

    text = visible_text(COMPOSITION.read_text(encoding="utf-8"))
    problems = []
    seen: set[str] = set()
    for match in NUMBER.finditer(text):
        raw = match.group(0)
        token = raw.rstrip(".,").replace(",", "")
        if not token or token in declared or token in seen:
            continue
        seen.add(token)
        here = match.start()
        excerpt = text[max(0, here - 40) : here + 40].strip()
        problems.append(f"{raw!r} is on screen and in no claim — …{excerpt}…")
    return problems


def _cues(vtt: str) -> list[tuple[float, float]]:
    """The narration's cue boundaries, in seconds."""
    out = []
    for start, end in re.findall(r"(\d\d:\d\d:\d\d\.\d\d\d)\s+-->\s+(\d\d:\d\d:\d\d\.\d\d\d)", vtt):
        out.append((_seconds(start), _seconds(end)))
    return out


def _seconds(stamp: str) -> float:
    hours, minutes, rest = stamp.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def _scenes(html: str) -> list[tuple[str, float, float]]:
    """Every timed clip in the composition: identifier, start, duration."""
    out = []
    for tag in re.findall(r"<section\b[^>]*>", html):
        classes = re.search(r'class="([^"]*)"', tag)
        if classes is None or "clip" not in classes.group(1).split():
            continue
        ident = re.search(r'id="([^"]*)"', tag)
        start = re.search(r'data-start="([\d.]+)"', tag)
        duration = re.search(r'data-duration="([\d.]+)"', tag)
        if ident and start and duration:
            out.append((ident.group(1), float(start.group(1)), float(duration.group(1))))
    return out


def cuts_that_left_the_narration() -> list[str]:
    """Beat boundaries against the spoken line each one is cut to.

    The composition's own comment says the boundaries are read from the VTT.
    That was true on the day it was written and nothing kept it true: the
    voice is generated, and a regenerated voice is a different set of
    boundaries. Each beat must start where its cue starts, and each beat but
    the last must end where the next cue starts; the last is allowed to run on
    past the final word, because the film holds its closing frame.
    """
    html = COMPOSITION.read_text(encoding="utf-8")
    scenes = _scenes(html)
    cues = _cues(NARRATION.read_text(encoding="utf-8"))

    if len(scenes) != len(cues):
        return [f"{len(scenes)} beat(s) in the composition against {len(cues)} narration cue(s)"]

    problems = []
    # `strict` is safe: the length mismatch is reported above and returns.
    paired = enumerate(zip(scenes, cues, strict=True))
    for index, ((ident, start, duration), (cue_start, cue_end)) in paired:
        if abs(start - cue_start) >= TOLERANCE:
            problems.append(f"{ident} starts at {start:g}s, its narration at {cue_start:g}s")
        last = index == len(scenes) - 1
        end = cue_end if last else cues[index + 1][0]
        if last:
            if start + duration + TOLERANCE < end:
                problems.append(
                    f"{ident} ends at {start + duration:g}s, before its last word at {end:g}s"
                )
        elif abs(start + duration - end) >= TOLERANCE:
            problems.append(
                f"{ident} ends at {start + duration:g}s, the next line starts at {end:g}s"
            )

    root = re.search(r'data-composition-id="main"[^>]*?data-duration="([\d.]+)"', html, re.S)
    if root is None:
        problems.append("the composition root declares no duration")
    elif scenes:
        _, final_start, final_duration = scenes[-1]
        declared, ends = float(root.group(1)), final_start + final_duration
        if abs(declared - ends) >= TOLERANCE:
            problems.append(f"the film runs {declared:g}s and its last beat ends at {ends:g}s")
    return problems


def assets_that_vanished() -> list[str]:
    """Everything the spec says the render feeds on, on disk."""
    return [
        f"{asset['rel']} is declared in film.yaml and is not in video/film/"
        for asset in spec().get("assets", [])
        if not (TREE / asset["rel"]).exists()
    ]


def check() -> list[str]:
    """Every problem, worst first."""
    return (
        claims_that_drifted()
        + numbers_nobody_declared()
        + cuts_that_left_the_narration()
        + assets_that_vanished()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--list", action="store_true", help="print the guarded claims")
    args = parser.parse_args()

    document = spec()
    if args.list:
        for claim in document["claims"]:
            source = claim["source"]
            print(f"{claim['text']:52s}  {source['path']} ({source['method']})")
        for entry in document.get("labels", []):
            print(f"{entry['shown']!s:52s}  label — {entry['why']}")
        return 0

    problems = check()
    for problem in problems:
        print(problem)
    if problems:
        print(f"\n{len(problems)} problem(s): the film is saying something the repository is not")
        return 1

    print(
        f"{len(document['claims'])} claim(s) hold, every figure on screen is declared, "
        f"and {len(_scenes(COMPOSITION.read_text(encoding='utf-8')))} beats are cut to the narration"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
