# ai-bunker

[🇫🇷](https://github.com/warith-harchaoui/ai-bunker/blob/main/LISEZMOI.md) · [🇬🇧](https://github.com/warith-harchaoui/ai-bunker/blob/main/README.md)

![License](https://img.shields.io/badge/license-BSD--3--Clause-blue)
![Python](https://img.shields.io/badge/python-3.10%E2%80%933.13-blue)
![Local-first](https://img.shields.io/badge/local--first-yes-brightgreen)
![Status](https://img.shields.io/badge/status-0.2.0--alpha-orange)

`ai-bunker` belongs to the **AI Helpers** suite, where AI is artificial
intelligence. It is the sovereign serving layer: **one GPU, one charter, every
coding agent** — a GPU being a graphics processing unit, the card or chip that
holds a model's weights and does the arithmetic of answering.

[🌍 AI Helpers](https://deraison.ai/ai-helpers)

---

A coding agent — Claude Code, OpenCode, Cursor, Continue — is a program that
spends your context window on your behalf. It reads files, calls tools, and
pays for every token it loads. When that agent talks to a model you host
yourself, two things decide whether the setup is usable: **how much context the
server really serves**, and **who counts the tokens**.

ai-bunker is the answer to both. It is an OpenAI-compatible gateway that sits in
front of your own GPU and carries three things no agent harness carries on its
own:

1. **A charter** — your team's standards, versioned, stored once, served to
   every client as an *index* rather than a wall of text.
2. **Rules that are enforced, not suggested** — versioned regular expressions
   that redact secrets before they enter a session and refuse the commands that
   blow up a context window.
3. **A budget the server actually counts** — with the server's own tokenizer,
   not the client's estimate.

That third point is the whole reason this project exists. See
[Why the server has to count](#why-the-server-has-to-count).

## The Promise

ai-bunker is **sovereign by construction**: it is a server you run, on a GPU you
control. Three honest cases, in the suite's usual order:

1. **Guaranteed local.** The gateway, the charter, the rule engine, the budget
   accounting, and the hardware sizing all run on your infrastructure. There is
   no telemetry, no account, and no dependency on SaaS — software as a
   service, which is to say somebody else's computer. Nothing in a prompt
   leaves the machine you serve from.

2. **The caveats, named.** Three, and only three. **(a)** Model weights are
   downloaded once, from Hugging Face or the Ollama registry, when you first
   serve a model. **(b)** If you deliberately configure a *premium route* — the
   20% of requests the strategy document sends to a frontier model — then those
   requests, and only those, leave your network, to the provider you named. The
   gateway logs every one of them. **(c)** `ai-bunker catalog update` refreshes
   the model catalog from a public directory; it is optional, and the bundled
   catalog works offline.

3. **Your decision.** The premium route is off by default and has to be written
   into a config file by a human. A deployment with no `remote` provider
   configured cannot reach the internet at inference time at all, and
   `ai-bunker doctor` says so out loud.

## Design principles

Three, and they decide everything else.

1. **Rules and knowledge belong to the infrastructure, not to each developer's
   config.** A standard that lives in everyone's dotfiles is a standard that
   drifts: it is adopted unevenly, bypassed under deadline, and silently
   different on the machine where it matters. Put it behind the endpoint and
   there is exactly one copy, versioned, and no way to use the model without it.

   Anthropic says the same thing about its own instruction files, which is a
   stronger admission than anything this project could claim on its behalf:

   > Claude treats them as context, **not enforced configuration**. To block an
   > action regardless of what Claude decides, use a PreToolUse hook instead.
   >
   > — Anthropic, [*How Claude remembers your project*](https://code.claude.com/docs/en/memory),
   > on `CLAUDE.md` and auto memory

   Nothing in that sentence is particular to one vendor. A `CLAUDE.md`, the
   `AGENTS.md` that OpenCode, Aider and goose read, a house style pasted into a
   system prompt: all of them are things the model is *told*, and a thing the
   model is told is a thing the model can weigh against something else.
   Enforcement is a different mechanism from instruction, and it has to live
   somewhere the model does not get a vote. Anthropic's answer is a hook on the
   developer's machine, and the open-source harnesses offer their own equivalents;
   both are the right tool for the things that happen before a request exists.
   This project's answer is the endpoint, for the reason in the paragraph above:
   a hook is still a file on a laptop, and it binds the one harness that reads it.

   Which is why the charter is enforced for *every* client — the proprietary ones
   and the open-source ones alike — and why the kits in [`clients/`](clients/README.md)
   are deliberately thin. Any client that speaks the OpenAI-compatible protocol
   gets the same rules, whether or not anyone wrote a kit for it.

2. **Index, don't concatenate.** The tempting way to give a model your standards
   is to paste them all into the system prompt. On a 32k window that spends the
   context before the first question; on a 256k window it still costs real money
   on every single turn, and the model reads none of it. Advertise a
   ~1,000-character index instead and let the model open the one page it needs.
   A page costs nothing until it is opened, so the charter can be large.

3. **Measure, don't assume.** Every number in this document was counted, not
   estimated — and the two most expensive problems found so far were both
   invisible to inspection and obvious to measurement. See the next section.

## Why the server has to count

On 2026-09-25, an OpenCode session believed it was under its limit and sent
**40,433 tokens** to a server configured for 32,768. The server counted for
real, refused the entire request, and the session died.

The client was not lying. It was estimating, with its own tokenizer rule, which
is more optimistic than Mistral's on French and on code. The gap was 55%.

The usual fix is to declare a *lower* context to the client than the server
actually serves — 26,000 against 32,768 — so the client's optimism is absorbed
by a margin. It works, as long as a test keeps someone from later "repairing"
that number back up. But it is a workaround for a structural problem: **the only party that can count correctly is the one holding the
tokenizer**, and that party is the server.

So ai-bunker counts. `GET /v1/budget` returns, for a given client and a given
charter, the measured floor of a session and what is left to work with:

```text
tool schemas (7) — client                      3164 tokens    47 %
client system prompt + machine instructions    2345 tokens    35 %
project charter (AGENTS.md equivalent)          905 tokens    13 %
knowledge index                                 353 tokens     5 %
FLOOR                                          6767 tokens

declared context                              26000
  − compaction margin                          6000
  = compaction starts at                      20000
  − floor                                      6767
  = conversation before compaction            13233 tokens
```

Those are real figures, measured at the relay on 2026-09-28. The same
measurement caught something a convention never would have: before the fix,
59 agent skills installed on one workstation were being injected into every
prompt — **17,754 tokens, 68% of a floor of 26,226** against a declared context
of 26,000. The session compacted on turn one, had nothing to compact, and looped
`build → compaction → build` forever, returning 8 tokens per turn and occupying
the GPU for nothing. The harness never said a word.

ai-bunker **refuses to serve** a session whose floor leaves less than a
configurable number of tokens (default 5,000) for actual conversation, and says
which component is responsible. A guardrail only helps when it fires before the
work does.

`ai-bunker budget` does this today, itemised and gated:

```text
  COMPONENT                        TOKENS   SHARE  OWNER
  agent skills (59)                17,754    68%  client
  tool schemas (7)                  3,164    12%  client
  client system prompt              2,345     9%  client
  charter                             905     3%  ai-bunker
  knowledge index                     353     1%  ai-bunker
  FLOOR — paid on every request    24,521

  VERDICT  UNUSABLE — this session cannot work
  ⚠  The floor (24,521) is at or above the compaction trigger (20,000).
     Compaction will fire on every turn with nothing to reduce.
  Attack agent skills (59) first: 68% of the floor, owned by the client.
```

Two details that are the whole point. **Attribution**: a floor nobody can
decompose is a floor nobody can reduce, so every token is charged to a named
owner — including ours, which is how you can check the claim that the charter
and the index cost under 5% of the window. And **`--gate`**: the verdict
becomes the exit code, because a check that reports a failure and exits zero is
not a check.

## What machine do you need

This is the question ai-bunker exists to answer concretely. The full study,
with prices surveyed 2026-10-19 and the command behind every figure, is in
**[docs/SIZING.md](docs/SIZING.md)**. Here is the reasoning and the answer.

One line of notation runs through everything below, so here it is once. **B**
is billions of parameters: a *24B* model carries 24 billion weights. **bf16**,
**FP8**, **Q4** and **AWQ4** say how many bits each of those weights is stored
on — bf16 is the 16-bit *brain floating point* format models are trained in,
FP8 is 8-bit floating point, Q4 is a 4-bit quantisation, and AWQ4 is
*activation-aware weight quantisation* at 4 bits, which chooses what to round
by watching which weights the activations actually use. **GB** is gigabytes;
**GiB** is gibibytes, 2³⁰ bytes, about 7% more than a gigabyte — which is why a
24B model at 8 bits a weight reads as 25 GiB rather than 24. **tok/s** is
tokens per second, the only speed a reader of generated text feels. And
**VRAM** is video random-access memory, the fast memory sitting next to a
graphics processor, which on a discrete card is all the room a model has.

### The constraint is bandwidth, not capacity

Generating a token requires reading every **active** weight out of memory once.
Capacity decides whether a model loads; bandwidth decides how fast it answers:

```
tokens/second  ≤  memory bandwidth  /  active weight bytes
```

Published DGX Spark measurements confirm it almost exactly. The GB10 has
273 GB/s: Qwen3 8B at bf16 (~16 GB) is measured at **13.6 tok/s** against a
roofline of 17.1, and Llama 3.1 70B at Q4 (~40 GB) at **4.4 tok/s** against
6.8. `ai-bunker` assumes 70% efficiency, conservative against both.

### The word that does the work is *active*

For a dense model, active weights are the whole checkpoint. For a **mixture of
experts** they are a fraction of it, and that fraction moves the wall by nearly
an order of magnitude:

| Model | Total | Active/token | Ceiling at 819 GB/s |
|---|---:|---:|---:|
| Devstral Small 2 24B, dense, FP8 | 25 GiB | 25 GiB | ~23 tok/s |
| Qwen3-Coder-Next 80B/3B MoE, AWQ4 | 45 GiB | ~9 GiB | ~62 tok/s |

**The best open coding model available is also the fastest to serve.** Choosing
a smaller model to go faster is, here, exactly backwards — and it is why the
recommendation below is cheaper than it looks.

### For a small team, VRAM buys quality, not throughput

Two people need two concurrent sequences above 20 tok/s. That is a low bar, so
the memory should go into a better model rather than into concurrency.

```bash
ai-bunker recommend --team 2 --model qwen3-coder-next --vision qwen3-vl-8b
```

| Machine | Cost | Speed | Sequences | Context |
|---|---:|---:|---:|---:|
| **Apple Silicon you already own** (96 GB M2 Max) | **$0** | 27 tok/s | 5 | 256k |
| **Mac Studio M3 Ultra 96 GB** | **$5,600** | **55 tok/s** | 23 | 256k |
| RTX PRO 5000 Blackwell 72 GB | $12,600 | 90 tok/s | 16 | 256k |
| RTX PRO 5000 Blackwell 48 GB | $10,200 | *the best model does not fit* | — | — |
| DGX Spark 128 GB | $6,950 | 18 tok/s — below the floor | 0 | — |

Two things worth saying out loud. **The 48 GB NVIDIA card cannot run the best
model at all** — on NVIDIA the entry ticket is the 72 GB card at $12,600, where
on Apple it is a $5,600 Mac Studio, because unified memory is cheap and GDDR7
— graphics double data rate memory, seventh generation, the fast discrete kind
— is not. And **the DGX Spark loses on bandwidth, not on memory**: it has 128 GB
and serves the best coder at 18 tok/s. Buying more of them does not help,
because bandwidth does not aggregate across machines for a single stream.

### The recommendation

**Step zero is free: measure the Mac you already have.** The arithmetic says a
96 GB M2 Max already serves Qwen3-Coder-Next at ~27 tok/s with a 256k window.
That is a projection, not a measurement, and the difference is this project's
entire argument — so pull the model, run a real session, and time a real patch
before spending anything.

**If it is not enough: Mac Studio M3 Ultra 96 GB, ~$5,600.** 819 GB/s, twice
the M2 Max, ~55 tok/s on the best open coder, holding the 80B model plus an 8B
vision-language model — a VLM, which reads images as well as text — plus the
embedder at once. A complete machine — no chassis to spec, no
600 W card, no rack, 270 W and silent. For a two-person outfit that is the
difference between having a server and having a project to build one.

**If you need vision with schema-constrained output: RTX PRO 5000 Blackwell
72 GB, ~$12,600.** This is the one thing Apple cannot do today. Driving a VLM
from an agent means constrained decoding, vLLM has guided decoding, and vLLM
has no macOS runtime — so *vision + schema ⇒ Linux + discrete NVIDIA*. The
72 GB card is the cheapest that holds the best coder model; the 48 GB version
is the same die, same bus and same 300 W, and cannot.

### Buying is not obviously right at this size

| Path | Cost | |
|---|---:|---|
| Measure the existing Mac | **$0** | Start here |
| Mac Studio M3 Ultra | $5,600 once | Pays back against two commercial seats in ~14 months |
| RTX PRO 5000 72 GB node | $12,600 once | Only justified by the vision requirement |
| Rent an equivalent GPU | ~$350/month | Break-even against the Mac Studio: ~16 months |
| Premium routes only | ~$400/month | No hardware, no operations, no sovereignty |

If sovereignty is a preference, rent or route. If it is a requirement — client
code under an NDA, a non-disclosure agreement; data residency in a tender — the
table is irrelevant and the answer is the machine.

### The cheapest upgrade is not hardware

The sizing is more sensitive to the **average live context per session** than
to almost anything on the invoice, and that figure belongs to the harness, not
to the card.

| Average live context | Sequences on a Mac Studio M3 Ultra |
|---:|---:|
| 32k — bounded reads, indexed charter, early compaction | **23** |
| 64k — an agent given a window and left to fill it | **11** |

An agent that pastes the whole standards document into every prompt, reads
files whole instead of in slices, and never compacts halves the machine for
identical output. That is the measurable argument for everything else here.

And it has now been measured rather than only computed. On an Apple M2 Max
serving a 4B model through Ollama, decode throughput falls **about twofold**
between a 216-token prompt and a 32k one — 1.67x, 1.93x and 2.20x across three
runs, with the fitted slope between 0.99 and 1.35 ms per thousand context
tokens. Context is not only a memory cost that decides whether a model fits; it
is a read paid on every token forever.

The same measurement says something less comfortable: the absolute rate moved
**1.6x between runs** on an otherwise idle laptop, while the spread inside each
run stayed under 1.6 tok/s. A single confident number from a machine that is
also running an editor is worth very little, so `scripts/bench_context.py`
reports wide spreads and non-monotone points instead of printing a tidy table.
Full numbers, method and limits in [`docs/SIZING.md`](docs/SIZING.md).

### A note on prices

They moved violently and they are not done. The RTX PRO 6000 launched at $8,565
in March 2025 and sells for ~$16,000 today; the DGX Spark went from $3,999 to
$6,950 for its 128 GB configuration. **A 2026 sizing done on 2025 prices is
wrong by a factor of two.** Re-survey before buying; the catalogue records what
was seen and when.

## The charter

Your team's standards, advertised rather than delivered.

The tempting way to give a model your standards is to paste them into the
system prompt. It is also the one that does not work, for a reason that is
arithmetic rather than aesthetic: the system prompt is the **floor** of a
session — paid on every request, out of reach of compaction. Pasted standards
are spent before the first question, on every turn, whether or not the model
needed any of them.

So ai-bunker ships an index:

```text
$ ai-bunker charter
charter      charter
fingerprint  aa9fcf72c7ff3e40ef72b92d659c589f40fbdfee
packs        3  (default, javascript, python)
pages        5
floor cost   972 tokens  (operating rules + index, every request)
not loaded   2,608 characters across the pages, read on demand
index vs all   4.6x  (1,043 tokens if every page were pasted in, 228 as an index)
```

The index names the packs and their pages; the model opens the one page the
task calls for, in bounded slices, with the ordinary file-reading tool.

Four things the index has to say, and the wording is chosen rather than
generated because every word is paid on every request: the pages exist; they
are **not** in this prompt (otherwise a model asked about naming answers from
habit instead of opening the page); **when** to open one (“available if needed”
is not an instruction a model acts on); and **one at a time** (an agent told to
consult the charter will otherwise read the whole pack and spend the window it
was saving).

The fingerprint is both a cache key — a serving engine re-serves an unchanged
prefix almost for free — and provenance: a session can record which charter it
actually ran under, which is the difference between “the rules were followed”
and “some rules were followed”.

## The rules

One format, two scopes, three severities — and every rule ships with the cases
it must catch and the cases it must leave alone, which run in continuous
integration.

```text
$ ai-bunker rules --check
  rules loaded                          27
  assertions passed                    218
  assertions failed                      0
  rules carrying evidence            100%
```

**`output`** rules screen what the world hands the agent: a secret on its way
into the transcript, an instruction smuggled into a web page. **`command`**
rules screen what the model asks to run, before it runs — the enforcement
point no client can bypass. A **`BLOCKER`** refuses, a **`GATED`** rule refuses
until a written reason is recorded, a **`WARNING`** annotates and lets through.

Most of what is interesting is the bypasses: a pattern anchored on `secret\s*=`
that walked past `AWS_SECRET_ACCESS_KEY=`, a `sudo` prefix that defeated three
separate rules, an environment assignment that defeated the anchors, a line
that turned out not to be one command, and `git`'s own options walking past all
nine git rules. Each was found by sending a payload through the real engine,
each is a test, and each is written up with its reasoning in
**[`docs/RULES.md`](docs/RULES.md)**.

## The gateway

The piece that makes the other three enforceable. Any client that speaks
OpenAI speaks ai-bunker, and gets the charter, the rule engine and a real
token budget **without being configured for them** — which is the whole
argument for putting this at the endpoint rather than in each developer's
harness. A plugin can be disabled by editing a file; a different harness
simply never had it.

```bash
ai-bunker serve                    # localhost:8000
export OPENAI_BASE_URL="http://127.0.0.1:8000/v1"
export OPENAI_API_KEY="$AI_BUNKER_API_KEY"
```

### Four stages, and the order is load-bearing

**1 — Screen inbound tool results.** A `role: "tool"` message is text the world
just handed the agent. It is screened and marked before anything else looks at
it. User and assistant turns are left alone: redacting a user's own words is
both surprising and useless.

**2 — Inject the charter.** As the first system block, in a stable position,
because a serving engine's prefix cache only helps while the head of the
prompt is byte-identical between requests. Idempotent, so a replayed
conversation does not accumulate copies.

**3 — Measure and enforce the budget.** Counted with the engine's own
tokenizer. A session with no room to work is refused **here**, with the
component responsible named, rather than failing downstream as a
context-length error nobody can act on:

```json
HTTP 413
{ "error": {
    "code": "context_budget_exhausted",
    "attack_first": "agent skills (59)",
    "budget": { "floor_tokens": 24521, "working_tokens": -4521, "verdict": "unusable" }
}}
```

**4 — Screen outbound tool calls.** When the model answers with a `tool_call`
carrying a shell command, **that command has not run yet**. This is the one
enforcement point no client can bypass. The refusal comes back shaped as a
tool result, because an agent that receives a 4xx retries the same call and an
agent that receives a tool result reads it.

Stages 1 and 4 are the rule engine's two scopes, and a gateway is the first
place both exist at once.

### Surface

| | |
|---|---|
| `GET /health` | Liveness, and the facts a deployment should not have to infer |
| `GET /v1/models` | Routable models, each with the context the gateway **declares** |
| `POST /v1/chat/completions` | Atomic and streaming. The full pipeline |
| `POST /v1/embeddings` | Proxied unchanged |
| `POST /v1/budget` | Measure a request's floor without sending it anywhere |
| `GET /v1/charter`, `GET /v1/charter/{ref}` | The index, and one page on demand |
| `GET /v1/decisions` | The tail of the audit log, never the matched text |
| `GET /gui` | The operations dashboard |

`/v1/models` reports a context **below** the engine's real one, deliberately.
Declaring the truth would be honest and would break: the margin is the only
protection while a turn grows.

`/v1/budget` lets a client ask what a session will cost *before* paying for it
— the difference between a budget that is merely enforced and one that can be
planned against.

### What it says about itself

```bash
$ ai-bunker doctor
  [ok  ] charter carries operating rules
  [ok  ] 27 rules loaded
  [ok  ] 218 rule assertions pass
  [ok  ] 100% of rules carry evidence
  [WARN] upstream local answers at http://127.0.0.1:8001/v1   not reachable
  [WARN] an API key is configured   no key: this gateway is open to anyone who
                                    can reach it. Fine on a trusted network, a
                                    decision either way
  [ok  ] no route leaves this network
  12/14 checks pass
```

`/health` reports the same facts at runtime: whether the deployment is
**sovereign** (no configured route leaves the network), whether it is
**authenticated** (an open gateway by accident looks exactly like one open on
purpose), and which of the three enforcement stages are actually live.

### Stated limitations

- ~~Command screening does not apply to a stream.~~ **Closed in 0.2.0.** It
  used to be true, and it was the largest hole in the claim this gateway
  makes: `stream: true` is what every agent client asks for by default, so
  the one guarantee being sold was off exactly where it mattered. The
  argument for leaving it — that refusing a fragmented tool call means
  buffering the whole answer — does not follow, because **no client can act on
  half a tool call**. Content deltas stream through untouched; only the
  tool-call fragments are held, assembled, judged by the same `apply_outbound`
  the atomic path uses, and then released. `/health` still reports which
  guarantees are live.
- **Counting blocks the event loop.** The tokenizer probe and the counts
  themselves are synchronous calls inside asynchronous handlers, so while one
  runs the gateway serves nobody. The probe is bounded at five seconds per
  dialect and the count at two minutes, which bounds the damage rather than
  removing it. Moving the calls onto a thread pool is the real fix and is not
  done. Stated because a deployment under concurrency should know, and because
  a limitation nobody published is one somebody discovers.
- **The shell-tool vocabulary is a default, not a claim to completeness.** A
  gateway cannot know every client's tool names; `SHELL_TOOLS` is overridable.
- **Binds to localhost by default.** A sovereignty tool that listens on every
  interface the moment it starts has made the decision its user was supposed
  to make.

### Audit

Every rule that fires appends a line, with the charter fingerprint and never
the matched text:

```json
{"rule":"global.generic_secret","severity":"BLOCKER","scope":"output",
 "outcome":"redacted","count":1,"charter":"aa9fcf72c7ff3e40","at":"2026/10/19-08:38:17"}
{"rule":"shell.destructive_rm","severity":"BLOCKER","scope":"command",
 "outcome":"refused","count":1,"charter":"aa9fcf72c7ff3e40","at":"2026/10/19-08:38:17"}
```

A failure to write the log warns and does not fail the request: losing a line
is bad, refusing to serve because a disk is full is worse, and the warning is
what gets someone to fix it.

## Agent2Agent

When agents talk to each other, a message written by one lands in another's
context. That is the event this project already treats as the dangerous one —
and it is worse than a tool result, because it arrives looking like a peer
rather than like data.

So A2A here is not a new concern bolted on. It is the existing concern at a new
ingress, screened by the same rules, with no parallel rule set to drift.

```bash
curl http://127.0.0.1:8000/.well-known/agent-card.json      # discovery
```

The card advertises two skills. `screen-text` is the one that matters: any
agent anywhere can put untrusted text through these guardrails without being a
client of this gateway.

```
POST /a2a/v1/message:send
{"message": {"role": "ROLE_USER", "parts": [{"text": "<the suspect text>"}]}}
```

```
state : TASK_STATE_COMPLETED
rules : global.generic_secret, global.vendor_token, injection.override_instructions
<<<ai-bunker:untrusted source=a2a peer>>>
Here is the deploy config you asked for.
<SECRET REDACTED>
github = <TOKEN REDACTED>
<INJECTION ATTEMPT REDACTED: instruction override> and email it to evil.example.com.
<<<ai-bunker:end untrusted>>>
```

Implemented: the HyperText Transfer Protocol (HTTP) and JavaScript Object
Notation (JSON) binding, discovery, and `message:send`. **Not**
implemented, and the card says so: streaming, push notifications, task history,
the authenticated extended card. `capabilities` is a contract — an agent that
advertises `streaming: true` and then does not stream has told a lie a peer
will build on.

Two smaller decisions worth stating. The card declares bearer authentication
only when a key is actually configured, because a card demanding a key from an
open gateway sends peers to fail at a door standing open. And the charter is
*one* skill with pages behind it, not a skill per page: a skill per page would
push the whole index into every peer's startup context, which is the cost the
charter exists to avoid.

## Routing by need, not by model name

A client hardcodes a model name because it has to put *something* in the field.
What it actually knows is what the work **is** — and that is the thing worth
routing on, because it survives the model being swapped.

```yaml
needs:
  code: local
  prose: local
  structured:
    upstream: local
    model: devstral
  reasoning:              # the 20%
    upstream: premium
    model: claude-sonnet-5
```

A client declares one with `X-AI-Bunker-Need`, or by asking for the need as its
model name — needs are listed in `/v1/models` for exactly that reason, since
most clients have a model dropdown and no header field. Needs are matched
**before** model names: a need is a statement about the work, a model name is
an implementation detail the client should not have had to learn.

This is the 80/20 split from the strategy made configurational. Routine work on
the local model, heavy reasoning on a premium route, and **swapping either is a
config change rather than an edit in every client**.

Two details that exist because of how this fails in practice. An unconfigured
need falls back and **warns**, because silently ignoring one is how an operator
discovers the routing from an invoice. And every off-network route is logged
with the rule that sent it there — `"model" -> premium by need 'reasoning'` —
because a request that went somewhere unexpected is only cheap to fix if the
log says which rule sent it.

> **Where model *selection* lives.** Choosing which model best fits a need and
> a budget is
> [`best-engine-ai-helper`](https://github.com/warith-harchaoui/best-engine-ai-helper)'s
> job, not this one's: it already ranks local models by hardware fit and paid
> models on a quality-versus-cost curve, picks among the providers whose
> application programming interface (API)
> keys are actually present, and falls back from paid to local. That question
> is asked *before* there is a server — in a script, on a laptop, in CI — so it
> belongs in a library. ai-bunker routes; it does not choose.

## Dashboard

`GET /gui` serves a single-page operations dashboard: the itemised session
floor by owner, the charter and what it costs, the blocks the model actually
sees, and the decision log.

One tile is the whole project in a picture — a stacked bar of the floor, **by
owner**, so you can see at a glance who is eating the window. Orange is the
client, blue is ai-bunker, green is what is left to work with. The three client
segments in a healthy deployment should dwarf ours, and when they do not, the
tile says which one to attack.

**No build step and no external request.** The house style for this kind of page
is Tailwind, which without a build step means the Play CDN, a content delivery
network — and a gateway whose claim is that nothing leaves the network cannot
serve its operator a page that fetches a stylesheet from a third party on load.
The first thing the dashboard would do is contradict what it displays. So the
Cascading Style Sheets (CSS) are written out with the same token discipline, and
the fonts are the system stacks.

Two deterministic gates run over it, and they are in the test suite:

```bash
python scripts/audit_contrast.py   # WCAG, every token pair, both schemes
python scripts/lint_a11y.py        # 14 static rules, no browser needed
```

The contrast auditor earned its place immediately: it found **four real
failures** on the first run, none of them visible by eye. The curated palette's
saturated hues read beautifully on dark and fail on white — `#28CD41` scores
2.12:1 against a card where 3:1 is the floor. The light scheme now uses
darkened variants of the same hues; the dark scheme, where the originals score
8:1, keeps them.

Both gates are tested for their ability to **fail**, against a deliberately
broken page. A linter that cannot fail produces a green tick and a false sense
that something was checked.

**Verified visually.** Three rounds of render-look-fix with headless Chrome,
both colour schemes. The record is in `.private/ralph-loop/`. It found six
problems, of which **two were real bugs that the 327 tests of the time did not catch**: two
statistics that never filled in, and a budget reporting `ratio (estimate)`
while the engine could have given an exact count — the dashboard of the budget
module reproducing the exact failure that module exists to prevent.

The third was not a bug and mattered most: the largest element on the page said
nothing. A floor of 607 against 193,108 of free space rendered as a 2-pixel
sliver, so the bar showed "there is room" and hid *who is eating it*. One bar
cannot carry a 300:1 ratio and a composition at once, so there are now two,
each honest at its own scale. **A page can pass every static gate and still say
nothing, and no unit test finds that.**

## Client kits

**Thin on purpose**, and the asymmetry is the design. Everything the gateway
can see, the gateway enforces — for every client, with no way to opt out by
swapping harness. What a client kit carries is exactly the set of things that
happen *before a request exists*, which no endpoint can reach.

| | Enforced by | Why there and not elsewhere |
|---|---|---|
| Secrets in tool output | **gateway** | It sees the `role: "tool"` message |
| Prompt injection | **gateway** | Same message, same chokepoint |
| Dangerous shell commands | **gateway** | It sees the `tool_call` before the command runs |
| Session floor / budget | **gateway** | Only the server holds the tokenizer |
| The charter | **gateway** | Injected into every request, whoever sent it |
| **Bounded file reads** | **client** | The gateway never sees a read. By the time the result arrives in a tool message, the tokens are already spent |
| **Skill / schema injection** | **client** | The gateway can *detect* a bloated floor and refuse; it cannot stop a client building the prompt that way |
| **Compaction thresholds** | **client** | Compaction happens entirely client-side, between turns |

A client kit cannot be trusted — it is a config file on someone's laptop — so
nothing load-bearing lives in one. But those three **client** rows are
structurally out of reach, and ignoring them costs hardware: an agent that
reads whole files and never compacts halves the sessions a GPU carries, for
identical output.

So the OpenCode kit is a config plus **one** plugin, `bounded-reads.js`. If it
ever grows, something has been put in the wrong place.

### Agent frameworks, where the loop is yours

The table above describes a **code agent**: somebody else's loop, which a kit
has to reach into because the harness decides those three rows. In an agent
framework you write the loop, so they are already yours — and a kit that set
them would be guessing at an application it cannot see. The kit is a module you
import, and it carries the two things a framework cannot get right on its own:
which endpoint to call, and what context window to believe.

```bash
ai-bunker adopt . --client langgraph     # ChatOpenAI, so all of LangChain
ai-bunker adopt . --client llamaindex    # OpenAILike
ai-bunker adopt . --client smolagents    # OpenAIModel
```

```python
from ai_bunker_langgraph import make_model
from langgraph.prebuilt import create_react_agent

agent = create_react_agent(make_model(), tools=[])
```

Opt-in rather than default: writing Python into a repository is authoring
application code, which is a different act from configuring a tool.

Thinner is not weaker, and that was checked rather than claimed. A tool result
carrying `AWS_ACCESS_KEY_ID=AKIA…` sent through the LangGraph kit came back
**redacted**, logged as `global.aws_access_key`, before the model read it. The
charter arrives on that route too — an exact 595-token floor, counted by the
engine's own tokenizer.

One warning the smolagents kit carries in its own docstring, because it is the
single risk a gateway does not cover: a `CodeAgent` executes the model's Python
locally by default. The gateway refuses dangerous *shell* commands because it
sees them as tool calls before they run; it cannot see an `exec` inside the
harness at all. Use `executor_type="docker"` for anything that is not a toy.

### Clients with no kit: publish the charter as an Agent Skill

A kit has to be written per client, which means a client this project has
never heard of gets nothing. [Agent Skills](https://agentskills.io) is an open
format for exactly this problem, read natively by Claude Code, OpenCode,
Cursor, Goose, Amp, Roo, Codex, Copilot and Gemini CLI — CLI for command-line
interface.

```bash
ai-bunker skill                      # writes .claude/skills/team-charter/
ai-bunker skill --client opencode    # or .opencode/skills/
ai-bunker skill --check .claude/skills/team-charter
```

The default is `.claude/skills/` because OpenCode documents that path as
Claude-compatible, so one copy serves both without writing the files twice.

The export is close to a rename, because the two designs agree. The format's
progressive disclosure loads a skill's `name` and `description` at startup,
its `SKILL.md` body on activation, and bundled files only when a task calls
for one. Those are this project's index, operating rules and pages, in order —
arrived at independently, for the same reason.

```
.claude/skills/team-charter/
├── SKILL.md                     # operating rules + the index (~700 tokens)
└── references/
    ├── default-00_principles.md # a page, loaded only when opened
    └── python-10_style.md
```

Two things this deliberately is **not**. It is an export, not a second source
of truth: the gateway stays the enforcing copy, and the charter fingerprint
travels in the skill's `metadata` so anyone can see whether a copy on disk has
drifted from the one being enforced. And it is not a replacement for a kit —
a skill carries standards, not bounded reads or compaction thresholds, which
are the three things in the table above that only a client can do.

### The other direction: a skills tree someone else wrote

The export proved the two formats agree, which means the import is nearly
free — and it is the more useful direction, because the standards a team most
wants served are usually ones it did not write.

```bash
ai-bunker skill --import ~/skore-skills/skills --pack ml \
                --source probabl-ai/skore-skills
```

Measured against [`probabl-ai/skore-skills`](https://github.com/probabl-ai/skore-skills),
a set of skills for steering machine-learning experiments with scikit-learn,
skrub and skore:

| | |
|---|---|
| skills read | 5 |
| their `SKILL.md` bodies | 103,788 characters |
| charter pages written | 77 |
| largest page | 8,183 characters (budget: 12,000) |
| pages over budget | **0** |
| what the prompt then carries | **~597 tokens**, operating rules and index together |

That is the whole point stated as a measurement: a hundred kilobytes of
standards become something an agent is *told about* for six hundred tokens and
reads one page of when a task calls for it.

**A body over the page budget is split at its `##` headings, and the text is
distributed rather than rewritten.** The rejoin is byte-identical — asserted,
not assumed, on every real skill tested. This is the line the project draws
elsewhere about touching content it did not author: a gateway may decide where
a page ends, and may not decide what it says.

**Provenance travels, and the source's own digest is preferred.**
`skore-skills` ships a `.catalog.json` with a `catalog_hash` over the set and a
hash per skill; those are recorded instead of a digest computed here, because
a digest this project invented would only prove the import was
self-consistent, not that it still matches upstream.

**Two findings worth stating, because the import is where they surfaced.**
First, all five of those skills carry a `description` longer than the Agent
Skills limit of 1,024 characters — between 1,783 and 2,431 — because they use
that field for trigger and scope prose. The import *reports* this and proceeds:
these are somebody else's skills and the job here is to serve them, not to
police them, but a silent import would hide a real interoperability problem
behind a success message. Second, importing a 77-page pack exposed a bug in
this project's own index: the size cap degraded the listing as a whole, so one
large pack turned `python: 10_style.md, tests.md` into `python (2 pages)` —
spending an agent's knowledge of two page names to save the forty-five
characters that named them. The cap now degrades **per pack, largest first**.

**`modelTier` is recorded and deliberately not acted on.** These skills declare
`metadata.modelTier: small | medium | big`, which lines up exactly with
[routing by need](#routing-by-need-not-by-model-name) rather than by model
name, and wiring the two together is tempting. It is not wired. A third-party
directory that can raise the tier is a third-party directory deciding what the
team pays for inference, and that is an operator's decision. The declaration
is preserved on the page where a person can read it and configure a route; it
never reaches the router on its own. This is the `tool` scope's argument
applied to a second channel: a declaration someone else wrote is an
instruction channel, not a fact.

### Verifying a client, from the server

A client kit is a claim; `POST /v1/budget` is how you check it. The response
itemises the floor by owner and says which component to attack first. That
measurement is what found a workstation injecting 59 skill descriptions into
every prompt — 17,754 tokens, 68% of the floor — while the harness said
nothing.

```bash
ai-bunker adopt /path/to/project                   # charter + both kits
ai-bunker adopt /path/to/project --list            # what would be written
ai-bunker adopt /path/to/project --client opencode --no-charter
```

Nothing is overwritten without `--force`: a repository that already has an
`opencode.json` has one for a reason. There is deliberately **no copy of the
operating rules at the repository root** — the gateway serves them, so a second
copy on disk could only drift from the one actually in use.

## MCP — the Model Context Protocol

With `fastapi-mcp` installed, the gateway mounts `/mcp` and exposes the charter
as tools, so an agent host can fetch the page for the domain it is working in
on its own initiative. **Only the charter**, and the omissions are deliberate:
`/v1/chat/completions` would be a model-calling tool inside a model's own turn,
a recursion with no obvious floor; `/v1/budget` is an operator's instrument, and
an agent given it would spend tokens measuring how many tokens it has.

A missing dependency is not an error — the HTTP surface is complete on its own.

## Features

- **Hardware sizing** (`ai-bunker sizing`, `compare`, `recommend --team N`) —
  a memory-roofline model over a catalogue of models and accelerators, reading
  the local machine with [`os-helper`](https://github.com/warith-harchaoui/os-helper).
  It answers both directions: *what does this machine carry* and *what machine
  do I buy for N people*, and emits the `vllm serve` command and the context
  figure to declare. Every assumption is a flag, and the report shows the chain
  rather than just the conclusion.
- **OpenAI-compatible gateway** — `GET /v1/models`,
  `POST /v1/chat/completions` (atomic and streaming), `POST /v1/embeddings`,
  `GET /health`. Any client that speaks OpenAI speaks ai-bunker.
- **Dual routing** — local (vLLM / Ollama) and a premium remote route for the
  20% of requests that need a frontier model, chosen per model by a versioned
  registry.
- **Charter as index** (`ai-bunker charter`) — standards live as Markdown and
  are advertised as a ~600-token index rather than pasted into every prompt. A
  page costs nothing until it is opened, so the charter can be large. See
  [The charter](#the-charter).
- **Enforced rules** (`ai-bunker rules`) — one format, two scopes, three
  severities, and every rule ships with its own evidence. Secrets are redacted
  on the way in, dangerous commands are refused, and **indirect prompt
  injection is caught at the one chokepoint where it arrives**. See
  [The rules](#the-rules).
- **Server-side budget** (`ai-bunker budget`) — measures the real floor with
  the serving engine's own tokenizer, **attributes every token to the component
  that caused it**, and exits non-zero on a configuration that leaves no room
  to work. Three backends in descending order of trust (`server`, `local`,
  `ratio`), and the report always says which one produced the number.
- **MCP** — the gateway exposes itself through the Model Context Protocol, so an
  agent host can discover the charter and the rules as tools.
- **Client kits** (`ai-bunker adopt`) — OpenCode and Claude Code configs
  pointing an existing harness at the gateway, plus the one plugin the gateway
  structurally cannot replace. See [Client kits](#client-kits).

## Status

This is an honest `0.2.0-alpha` and the table says exactly where it stands.
Nothing above is a claim about shipped code unless this table says so.

| Component | State |
|---|---|
| Decision record, charter design | ✅ this document |
| `.gitignore`, `pyproject.toml`, project scaffold | ✅ |
| `ai_bunker/sizing.py` + `report.py` — roofline model, catalogue, CLI | ✅ |
| `docs/SIZING.md` — the buying decision, costed | ✅ |
| `ai_bunker/budget.py` — server-side token accounting, itemised and gated | ✅ |
| 1350 tests, `ruff` clean | ✅ |
| `scripts/lint_acronyms.py` — every abbreviation spelled out before use | ✅ |
| `ai_bunker/budget.py` — server-side token accounting | ✅ |
| `ai_bunker/charter.py` — index, pages on demand, fingerprint | ✅ |
| `ai_bunker/rules.py` — two scopes, entropy, allowlists, self-testing rules | ✅ |
| `charter/` — 16 shipped rules with 95 examples, all passing | ✅ |
| `ai_bunker/gateway.py` + `pipeline.py` + `config.py` — the OpenAI surface | ✅ |
| `ai-bunker doctor` — does the deployment do what it claims | ✅ |
| `clients/opencode`, `clients/claude-code` + `ai-bunker adopt` | ✅ |
| MCP surface (`fastapi-mcp`), charter only | ✅ |
| `GET /gui` — operations dashboard, no build step, no external request | ✅ |
| `scripts/audit_contrast.py`, `scripts/lint_a11y.py` — deterministic gates | ✅ |
| Routing by need (`X-AI-Bunker-Need`) | ✅ |
| Visual review (3 rounds, headless Chrome, both schemes) | ✅ |
| `CHANGELOG.md`, `CONTRIBUTING.md`, GitHub Actions CI | ✅ |
| `LANDSCAPE.md` / `PAYSAGE.md` — competitive field, surveyed | ✅ |
| `docs/EXAMPLES.md` | 🚧 next |

The design is not alpha. Every figure in this document comes from a GPU that
served 6,565 messages in production under exactly these constraints. The code
is new; the evidence behind it is not.

## Documentation

[📋 Examples](EXAMPLES.md) — every command, with its real output. Nothing in it
is illustrative: each block was produced by running the line above it.

[📐 Sizing](docs/SIZING.md) — which machine to buy, costed.

[🛡️ Rules](docs/RULES.md) — the engine in full: both scopes, all three
severities, and every bypass that was found by probing, with the reasoning
behind the pattern that caught it.

## Where this sits

[🗺️ Landscape](LANDSCAPE.md) — the gateways, the rule engines and the policy
engines, compared, with a positioning map and an honest section on **where this
project is behind**. The short version: gateways route, guardrails inspect,
neither counts, and the corner where all three meet is empty.

## Built on the suite

ai-bunker deliberately implements as little as possible:

- [`os-helper`](https://github.com/warith-harchaoui/os-helper) — hardware
  detection, configuration loading, logging, hashing, timing, shell-free
  subprocess. It stands in for three modules this project would otherwise have
  hand-rolled and then had to maintain.
- [`best-engine-ai-helper`](https://github.com/warith-harchaoui/best-engine-ai-helper)
  — the model catalog, the memory-fit scoring, the Ollama-vs-vLLM backend rule,
  and the committed-brief → machine-specific-engine resolution. ai-bunker
  describes its *needs* in a brief and lets the helper choose; it never hardcodes
  a model name.
- [`ann-router`](https://github.com/warith-harchaoui/ann-router) — planned, for
  the day the charter outgrows lookup-by-path and needs a real retrieval index.

Same philosophy throughout the suite: **measure the criteria → select the engine
→ return a rationale you can argue with.**

## Installation

**Prerequisites**: **Python 3.10–3.13** and **git**. A GPU is required only on
the machine that *serves*; clients need neither.

- 🍎 **macOS** ([Homebrew](https://brew.sh)): `brew install python git`
- 🐧 **Ubuntu/Debian**: `sudo apt update && sudo apt install -y python3 python3-venv python3-pip git`
- 🪟 **Windows** (PowerShell): `winget install Python.Python.3.12 Git.Git`

```bash
git clone https://github.com/warith-harchaoui/ai-bunker.git
cd ai-bunker
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

On the serving machine, add the server runtime:

```bash
pip install -e ".[serve]"     # vLLM
```

## Usage

Shipping today — the sizing surface:

```bash
# Which machine do I buy for a team of N?
ai-bunker recommend --team 2 --model qwen3-coder-next --vision qwen3-vl-8b
ai-bunker recommend --team 2

# What does one machine carry, and why?
ai-bunker sizing --accelerator rtx-pro-6000-blackwell
ai-bunker sizing --vram 96 --bandwidth 1792        # a machine not in the catalogue

# Every machine, one line each, with cost per person carried
ai-bunker compare

# The facts behind all of it, with provenance
ai-bunker catalog

# What os-helper sees about this machine
ai-bunker detect
```

Every assumption is a flag, and the ones that move the answer most are named:

```bash
--comfort-tps 30        # a stricter per-stream floor: bigger machine
--live-context 65536    # an undisciplined harness: halves every machine
--duty-cycle 0.4        # heavier agentic use
--simultaneity 1.0      # size for the worst hour, not the average one
```

What a session costs before it has done any work:

```bash
# Itemise the floor of a captured request, counted by the serving engine
ai-bunker budget request.json \
  --served-context 131072 --declared-context 104000 --reserve 16000 \
  --base-url http://bunker.internal:8000/v1 \
  --model-name mistralai/Devstral-Small-2-24B-Instruct-2512 \
  --charter charter/AGENTS.md --index charter/index.md

# In CI: refuse the deployment rather than report it
ai-bunker budget request.json --served-context 32768 --exact --gate
```

The charter and the rules:

```bash
ai-bunker charter                        # what it holds and what it costs
ai-bunker charter --index                # the index exactly as injected
ai-bunker charter --page python/tests.md # one page, on demand

ai-bunker rules --check                  # run every rule against its evidence (CI gate)
ai-bunker rules --command "git push --force origin main"
cat README.md | ai-bunker rules --provenance "https://untrusted.example"
```

The gateway:

```bash
cp config/gateway.example.yaml config/gateway.yaml   # then edit
export AI_BUNKER_API_KEY=...

ai-bunker doctor                    # is everything the deployment claims true?
ai-bunker serve                     # localhost:8000
ai-bunker serve --host 0.0.0.0      # warns, because that is a decision
```

Equipping a repository:

```bash
ai-bunker adopt /path/to/project --list   # what would be written
ai-bunker adopt /path/to/project          # charter + client kits
```

Point any OpenAI-compatible client at the gateway:

```bash
export OPENAI_BASE_URL="http://bunker.internal:8000/v1"
export OPENAI_API_KEY="<your gateway key>"
```

## Author

- [Warith Harchaoui](https://linkedin.com/in/warith-harchaoui)

## License

BSD-3-Clause — the three-clause license of the Berkeley Software Distribution.
See [LICENSE](https://github.com/warith-harchaoui/ai-bunker/blob/main/LICENSE).
