# The launch film

Ninety seconds on what ai-bunker is, built from the repository rather than
about it.

| File | What it is |
|---|---|
| `SCRIPT.md` | The eight beats, with the source of every claim named per beat |
| `film.yaml` | The same claims, checkable — `make-film verify` reads each one out of the file that decides it |
| `film/index.html` | The composition: one HTML file, one paused GSAP timeline, no renderer-specific magic |
| `film/narration/` | The spoken track and the cue file the whole film is cut to |

## Rebuild it

```bash
make-film verify video/film.yaml --root .     # are the numbers still true?
cd video/film && npx hyperframes check        # lint, layout, motion, contrast
npx hyperframes render                        # → out/*.mp4
```

The MP4 is not committed. Everything that produces it is.

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

## Timing

Every beat is cut to the **measured** length of its narration, read from
`film/narration/narration.vtt`, not to an estimate of how long a line takes to
say. The boundaries live in one array at the top of the timeline, so
re-narrating a line moves everything cut to it instead of leaving eight
hand-typed numbers to drift apart one at a time.

Which is the same argument as the rest of the project, pointed at a video.
