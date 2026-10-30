# The launch film

Ninety seconds on what ai-bunker is, built from the repository rather than
about it.

| File | What it is |
|---|---|
| `SCRIPT.md` | The eight beats, with the source of every claim named per beat |
| `film.yaml` | The same claims, checkable — nineteen of them, each naming the file that decides it |
| `film/index.html` | The composition: one HTML file, one paused GSAP timeline, no renderer-specific magic |
| `film/narration/` | The spoken track and the cue file the whole film is cut to |

## Rebuild it

```bash
python3 scripts/lint_film.py                  # the gate: claims, scan, cuts, assets
cd video/film && npx hyperframes check        # lint, layout, motion, contrast
npx hyperframes render                        # → out/*.mp4
```

The MP4 is not committed. Everything that produces it is.

`make-film verify video/film.yaml --root .` answers the first question too, and
`make-film scan` the second. Neither is what the lane runs, and the reason is
the point of the next section.

## The one rule this film has to keep

Its closing line is *"every number in this film is in the repository, and a
test fails when one of them drifts"*, which is a promise, and a film is the
worst possible place to make one: a README gets re-read and a number burned
into a keyframe does not.

So `film.yaml` exists before the first frame did, and it earned its keep
immediately — it caught two drifts in the first draft of the script:

- *"thirteen hundred tests"* was 1,140;
- *"972 tokens, three percent"* was a real measurement from
  `scripts/measure_overhead.py` and the wrong thing to burn into a frame,
  because it moves whenever the charter is edited. The claim that is **gated**
  is *under 5% of the window*, so that is the one the film makes.

The second correction is the more interesting one. A true number and a
defensible number are not the same thing, and a film can only carry the
second kind.

### And then the promise shipped without the test

For a week, nothing read `film.yaml`. The spec was correct, the claims held,
and the only thing that checked them was `make-film` typed by hand on the one
machine that had it — not a dependency of this package, not a step in the
workflow, not reachable from `pytest`. The film's closing frame promised a
failing test and there was no test.

That is the third time this repository has shipped a claim with no gate
behind it, after `py.typed` against twenty-five `mypy` errors and `pytest-cov`
against a coverage figure nobody had measured. It landed in a directory
created the same week the other two were written up, which is the useful part:
naming a failure mode does not protect the next thing you build.

`scripts/lint_film.py` is the gate, with no dependency outside what installing
this package already brings, so there is no checkout where the film is
unguarded. It checks four things:

| | |
|---|---|
| **Drift** | every claim still holds in the file it names |
| **Scan** | every figure on screen is declared — this caught three the first pass had left |
| **Cuts** | every beat boundary is still a cue boundary in the narration |
| **Assets** | everything the render feeds on is on disk |

`tests/test_film.py` runs all four against the real film and then feeds each
one the regression it exists to catch, because a gate nobody has seen fail is
a gate nobody should trust. And `tests/test_packaging.py` now asks the
question one level up: every module in `scripts/` is run by the lane, or by
the suite, or listed with a reason why it cannot be.

The three figures the scan caught are worth naming. Two were a card and a
model size. The third was the **date** — on screen as *25 September 2026*, in
the README as `2026-09-25`. No search for the film's own wording would ever
have found it, and that pair is the clearest argument for a spec file sitting
between the frame and the source: it is where two notations of one fact are
reconciled.

## Timing

Every beat is cut to the **measured** length of its narration, read from
`film/narration/narration.vtt`, not to an estimate of how long a line takes to
say. The boundaries live in one array at the top of the timeline, so
re-narrating a line moves everything cut to it instead of leaving eight
hand-typed numbers to drift apart one at a time.

Which is the same argument as the rest of the project, pointed at a video —
and it is now checked rather than asserted. The voice is generated, and Kokoro
does not promise the same waveform across versions, so re-narrating a line
moves every cue after it. `lint_film.py` compares the composition's eight beat
boundaries against the eight cues in `narration.vtt`: each beat starts where
its line starts and ends where the next one begins, except the last, which is
allowed to hold its closing frame after the voice stops.
