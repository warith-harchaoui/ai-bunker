# ai-bunker — launch film

**Eight beats, ~95 seconds.** Every number in it comes from the repository and
is declared in `film.yaml`, so `make-film verify` fails the build when one
drifts. That is not a flourish — it is the closing line of the film itself,
and a film that makes that claim and cannot keep it is the exact failure the
whole project is about.

Sources are named per beat. Where a figure already exists as an SVG in
`assets/`, the film reuses it rather than redrawing it: the picture on screen
and the picture in the README are then the same file, and the figure audit
already gates it.

---

## 1 — Opening punchline · 0:00–0:08

> **An agent that estimates its own context**
> **is a bank that estimates your balance.**
>
> On the 25th of September, one of them sent **40,433 tokens**
> to a server that holds **32,768**.

*Source: `README.md` § Why the server has to count.*
*On screen: the two numbers, the smaller one underneath, and the overflow.*

---

## 2 — What · 0:08–0:18

> ai-bunker is a serving layer.
> It stands between your coding agent and **your own** graphics card,
> and it speaks OpenAI — so every client you already use works unchanged.
>
> Nothing leaves the network.

*Source: `pyproject.toml` description; `README.md` § The Promise.*
*On screen: `assets/figure-path.svg` — the four positions, ai-bunker lit.*

---

## 3 — Problem · 0:18–0:34

> The client was not lying. It was **estimating**, with its own tokenizer rule.
> The gap measured **55 %**.
>
> And estimating has a worse failure than refusal. Fifty-nine agent skills on
> one workstation cost **17,754 tokens** — sixty-eight percent of the floor,
> against a window of 26,000.
>
> That session compacted on turn one with nothing to compact.
> Build, compact, build. **Eight tokens a turn.** The accelerator busy for
> nothing.
>
> The harness never said a word.

*Source: `README.md` § Why the server has to count; `ai_bunker/budget.py`.*
*On screen: `assets/figure-budget.svg` — the second bar crossing the trigger.*

---

## 4 — Solution · 0:34–0:48

> There is exactly one party that can count correctly:
> the one holding the **tokenizer**. That party is the server.
>
> ai-bunker measures the floor with the engine's own tokenizer,
> itemises it **by owner** — yours and ours —
> and refuses a session with no room left to work,
> naming the component responsible.
>
> Not a warning. An **exit code**.

*Source: `ai_bunker/budget.py` `measure_request`, `Budget.verdict`; `--gate`.*
*On screen: the itemised floor table, the VERDICT line landing last.*

---

## 5 — Secret sauce · 0:48–1:06

> A turn crosses the gateway four times, and the order carries the meaning.
>
> On the way **in**: tool results are screened, the charter is injected,
> the budget is measured.
> On the way **back**: the model's tool calls are screened —
> because a shell command inside a tool call is a command that
> **has not run yet**.
>
> Stages one and four are the same rule engine, read at both ends of one turn.
> A gateway is the only position from which both ends are visible.

*Source: `README.md` § Four stages; `ai_bunker/pipeline.py`, `rules.py`.*
*On screen: `assets/figure-pipeline.svg`, lanes revealed in order.*

---

## 6 — Best example · 1:06–1:22

> One H100. Eighty gibibytes. Every slot filled.
>
> Ask for pictures, and the arithmetic tells you the price before you pay it:
> the coder drops from the eighty-billion mixture-of-experts
> to a dense twenty-four.
>
> Printed **before** you deploy it — not discovered after.
>
> And the guardrails themselves? The charter and the index cost
> **under five percent** of the window.
> There is a test that fails the day that stops being true.

*Source: `ai-bunker sizing --accelerator h100-80 --image auto`;
`README.md` line 178, gated by `test_our_own_guardrails_are_cheap`.*

*The first cut said "972 tokens, three percent" — a real measurement from
`scripts/measure_overhead.py`, and the wrong thing to burn into a frame: it
moves whenever the charter is edited. The claim that is **gated** is "under
five percent", so that is the one the film makes. This is the skill's own
lesson applied to itself before the first render rather than after.*
*On screen: `assets/figure-plan.svg`, the image slot highlighted, then the 3 %.*

---

## 7 — Call to action · 1:22–1:32

> Read it: **deraison.ai/ai-helpers**
> Star it: **github.com/warith-harchaoui/ai-bunker**
>
> BSD-3-Clause. One author. **1,147 tests**, and the count in this line
> is checked by one of them.

*On screen: both URLs, the GitHub star glyph, the licence line small.*

---

## 8 — Closing punchline · 1:32–1:40

> Every number in this film is in the repository,
> and a test fails when one of them drifts.
>
> **Count. Don't estimate.**

*On screen: the wordmark, then the two words alone.*

---

## Why these two punchlines

The opening had to land the failure in one image without a diagram, because
nothing is on screen yet. *A bank that estimates your balance* is the same
category error as a harness that estimates its own tokens — unacceptable in
one domain, normal in the other, and the film's job is to make the second feel
like the first.

The closing had to be a claim the film itself keeps. Saying *count, don't
estimate* over a film whose own numbers had rotted would be the joke told
about the project rather than by it — so the line is earned by `film.yaml`
and `make-film verify`, and it is the reason the spec exists at all.
