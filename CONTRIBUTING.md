# Contributing

## The one rule

**Every claim in this repository is a measurement or it is removed.**

That is not a slogan about rigour; it is what the project is for. A context
budget nobody counted, a rule nobody tested, a sizing nobody checked against a
real measurement — each of those is the exact failure ai-bunker exists to
prevent, and shipping one here would be the project contradicting itself.

Three consequences, in practice.

**A number in the documentation names where it came from.** "roughly 70% of
peak bandwidth" is a stated assumption with a flag to override it. "17,754
tokens" is something that was counted. Both are fine; a number with no
provenance is not.

**A rule ships with its own evidence.** `charter/rules/*.yaml` entries carry
`examples:` with `should_match` and `should_not_match`, and `ai-bunker rules
--check` runs them in continuous integration (CI). This is not ceremony: three
of the shipped patterns were wrong on first write, and the examples caught all
three.

**A limitation is published, not implied.** Command screening does not apply
to a stream. The shell-tool vocabulary is a default, not a claim to
completeness. The dashboard's accessibility lint is static only. Each of those
is stated in the code and in the README, because a guarantee that quietly does
not hold is worse than one that was never offered.

**An abbreviation is spelled out before it is used.** In place, at first use,
in that file and in that language — not in a glossary. A glossary explains a
term *after* every sentence that already used it, which is the wrong order, and
it asks the reader to leave the page. A reader who does not know that AP2 is
the Agent Payments Protocol cannot evaluate a claim about it, and that reader
is most of the audience.

`python scripts/lint_acronyms.py` enforces it over every prose file and both
languages of the site. It runs in both directions: it checks that each
catalogued abbreviation is spelled out at or before its first use, and it also
reports any two-capital token the catalogue has never heard of, so a new
abbreviation cannot arrive unnoticed. Names are exempt and listed — `NVIDIA`
and `LLM Guard` are things people named, not initials, and forcing an expansion
on them would mean inventing one.

## Getting set up

```bash
git clone https://github.com/warith-harchaoui/ai-bunker.git
cd ai-bunker
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[api,mcp,dev]"
```

## Before you push

```bash
ruff check ai_bunker tests scripts
ruff format ai_bunker tests scripts
pytest -q
ai-bunker rules --check              # the rules against their own examples
python scripts/audit_contrast.py     # the dashboard's WCAG gate
python scripts/lint_a11y.py          # the dashboard's static a11y gate
python scripts/lint_acronyms.py      # no abbreviation used before it is explained
python scripts/sync_counts.py        # rewrite every quoted figure from its source
```

CI runs exactly these, on Python 3.10 through 3.13.

One check is deliberately **not** in that list:

```bash
python3 scripts/verify_deployment.py   # does production match the repository?
```

It compares the site on the server, byte for byte, against what
`web/publish.py` would upload. That needs the network and a deployment to
exist, so it cannot be a gate on a pull request — it is what you run *after*
an upload, and it is the only check here that can tell you the upload did not
happen. See `web/DEPLOY.md`.

## Tests

**A test asserts a claim, and its name states the claim.**
`test_a_refused_command_is_not_retried` beats `test_refusal_2`. When a test
fails, its name should already say what broke.

**One claim per test.** A test asserting five things reports one failure and
hides four.

**A gate is tested for its ability to fail.** The contrast auditor, the a11y
linter and the rule checker each have a test that feeds them something broken
and asserts they say so. A linter that cannot fail produces a green tick and a
false sense that something was checked — which is worse than no linter at all.

**Prefer a real object to a mock.** The gateway tests stub an upstream rather
than patching the HyperText Transfer Protocol (HTTP) client, because the
gateway's job is to forward a *rewritten* request and the test needs to see what
actually arrived.

## Changing the rules

Add a rule in `charter/rules/`, with examples, and run `ai-bunker rules
--check`. The loader will refuse a pattern with a nested unbounded quantifier —
`(a+)+` and friends — because one of those on a shared server stalls every
session on the box. Bound the repetition; no realistic rule needs an unbounded
inner one.

A rule that gets in the way of legitimate work is a rule to change here, with
a `should_not_match` example that would have caught it, not a rule to work
around.

## Changing the dashboard

The page is `ai_bunker/static/gui.html`: hand-written Cascading Style Sheets
(CSS), no build step, **no external request**. The last constraint is not
stylistic. A gateway whose claim is that nothing leaves the network cannot serve
its operator a page that fetches a stylesheet from a CDN — a content delivery
network — on load.

Both gates run in CI. Beyond them, **look at it**:

```bash
ai-bunker serve --port 8000 &
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu --force-device-scale-factor=2 \
  --window-size=1280,2000 --virtual-time-budget=6000 \
  --screenshot=/tmp/gui.png "http://127.0.0.1:8000/gui?key=$AI_BUNKER_API_KEY"
```

Render, look, fix the source, render again. Both colour schemes. The record of
previous rounds lives in `.private/ralph-loop/` (gitignored). The last one
found two real bugs no test caught and one element that was large, prominent,
and said nothing.

## Commits

Describe the change and why it was needed. A commit that says *what* the diff
already shows has spent a line saying nothing.
