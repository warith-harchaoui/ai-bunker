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

**A limitation is published, not implied.** The shell-tool vocabulary is a
default, not a claim to completeness. The dashboard's accessibility lint is
static only. The deployment checker cannot see files the repository does not
list. Each of those is stated in the code and in the README, because a
guarantee that quietly does not hold is worse than one that was never offered.

And when a limitation is closed, **the statement of it goes too**. Command
screening did not apply to a stream; it does since 0.2.0. Eight files said
otherwise, seven were corrected, and the two site pages were missed — so the
published site advertised a hole that no longer existed for five commits. A
published limitation that is no longer true is worse than either: it is a
measurement of something that has changed.

That is what `scripts/lint_claims.py` is for. It holds a load-bearing claim to
one answer across every file that states it, the way `sync_counts.py` does for
figures. **Closing a limitation means registering it there**, which is a line
in `CLAIMS` and the price of the claim staying true. `CHANGELOG.md` is exempt:
it records what was true on the day it was written, and a struck-through
sentence is a withdrawal rather than a drift.

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
python scripts/lint_claims.py        # no claim that stopped being true
python scripts/lint_film.py          # the launch film still matches the repository
python scripts/lint_handoff.py       # the session handoff still describes this repository
python scripts/sync_counts.py        # rewrite every quoted figure from its source
```

CI runs all of these. The suite runs on **Python 3.10 and 3.13** — the two
ends of the range `pyproject.toml` declares — and everything else runs once,
on 3.13, because lint, format, rule evidence, the three page audits and
`doctor` cannot answer differently on a different interpreter. Four of the
commands above reach CI through the suite rather than through a workflow step,
because the suite calls them: the acronym linter (`tests/test_acronyms.py`),
the claim linter (`tests/test_claims.py`), the film linter
(`tests/test_film.py`) and `sync_counts.py --check` (`tests/test_site.py`).

`lint_handoff.py` is the odd one out and says so: it reads `.private/`, which
is working memory between sessions and is not committed, so in the lane it has
nothing to read and passes. `tests/test_handoff.py` feeds it synthetic
handoffs instead, because a gate whose input is absent in CI still has to be
shown capable of failing there.

A script in `scripts/` has to be run by one of those two routes, or listed in
`SCRIPT_RUNNERS` in `tests/test_packaging.py` with the reason it cannot be.
Adding a gate and forgetting to wire it up is the most common defect this
repository has found in itself — three times now — so the directory is
compared against that mapping on every run.

Two checks are deliberately **not** in that list.

```bash
pytest tests/test_integration.py   # the gateway against a real engine
```

Every other test talks to a stub, which is right for almost everything and
means the suite agrees with a fixture somebody wrote. These drive the real
gateway against a real model over real Server-Sent Events, and they skip when
no engine is reachable — so they run on a developer's machine and not in
continuous integration. Point them anywhere with `AI_BUNKER_TEST_ENGINE`;
with nothing set they look for Ollama. Nothing in there is the only test of
anything: each has a stubbed twin.

And two measurements that write a committed file rather than returning a
verdict, so they are run when their input changes rather than on every push:

```bash
python3 scripts/measure_type.py        # per-character text metrics, from the fonts
python3 scripts/measure_ratio.py       # the characters-per-token floor, from the tokenizers
```

The first needs `fontTools` and the four fonts the figures name; the second
needs the `tokenizers` extra and the network. Neither belongs in a lane, and
neither is unguarded: `tests/test_figures.py` fails when the figures change
font stack without a re-measure, and `tests/test_budget.py` holds the ratio
constant to what the estimate is allowed to assume.

And:

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
