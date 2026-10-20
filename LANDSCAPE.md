# Landscape

[🇫🇷 PAYSAGE.md](PAYSAGE.md) · 🇬🇧 English

Tools that sit between a coding agent and a model, compared against `ai-bunker`.
Ratings are ⭐ (1) to ⭐⭐⭐⭐⭐ (5), scored on this project's intended job: **stand in
front of your own graphics processing unit (GPU) and enforce, for every client, a
charter, a rule engine and a context budget the server actually counts.**

A tool optimised for a different job is not being criticised; the score reflects fit to
*this* niche. Several entries below are excellent at theirs, and three of them are
better than this project at something named in the table.

Two abbreviations run through the names in the table and the prose after it: **AI**
is artificial intelligence, and an **LLM** is a large language model — the kind of
model every tool here stands in front of.

Surveyed 2026-10-19.

## At a glance

<!-- TABLE:START -->
| Serving layer | Nothing leaves the network | Screens what the agent reads | Refuses what the agent runs | Counts the budget server-side | Serves team standards | Rules ship with tests | Any OpenAI client | Provider breadth |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **ai-bunker** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| LiteLLM | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Portkey | ⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Kong AI Gateway | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| NeMo Guardrails | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| Guardrails AI | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| LLM Guard | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ |
| Open Policy Agent | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ |
| Client-side harness config | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐ |
<!-- TABLE:END -->

## Positioning map

<!-- FIGURE:START -->
A two-dimensional representation of the table above, by principal component
analysis (PCA) (see [`standpoint`](https://github.com/warith-harchaoui/standpoint)).

![Positioning map](https://raw.githubusercontent.com/warith-harchaoui/ai-bunker/main/assets/landscape.png)

Read it as a shape, not a scoreboard. The axes read **Horizontal — Resourceful ↔
Disciplined** and **Vertical — Protected ↔ Managed**.
<!-- FIGURE:END -->

## What the map actually shows

Three clusters, and an empty corner.

**Left — the gateways.** LiteLLM, Kong, Portkey. They answer *"how do I put one
OpenAI-shaped surface over a hundred providers, with keys, budgets, retries and
observability?"* and answer it very well. What they do not do is look at what the agent
is reading or about to run: a tool result full of secrets and a `rm -rf ~` pass through
a gateway as ordinary bytes.

**Centre and lower right — the rule engines.** NeMo Guardrails, Guardrails AI, LLM
Guard. They inspect content properly — personally identifiable information (PII),
toxicity, injection, schema conformance —
and several do it better than this project does. What they are not is a gateway: they
are libraries you call from your own application, which means an agent that does not
call them is unprotected, and swapping harness loses them entirely.

**Bottom right — policy without a position.** Open Policy Agent writes and tests
policy better than anything here, and is not in the request path at all. A client-side
harness config is in the path and is a file on a laptop.

**Top right is empty except for this project.** Nobody else combines the gateway's
position (every request, every client, no opt-out) with the rule engine's inspection and
a budget the server counts. That is a claim about coverage, not about quality.

## Positioning

The gateways route; the guardrails inspect; neither counts. `ai-bunker` is the
intersection, and three things follow from standing there.

**Both ends of an agent's turn are visible from one place.** A `role: "tool"` message is
text the world just handed the agent — where secrets leak in and where indirect prompt
injection arrives. A `tool_call` carrying a shell command is a command that **has not run
yet**. Screening the first and refusing the second are the two scopes of the same rule
engine, and a gateway is the first place both exist at once.

**The budget is counted by the party holding the tokenizer.** Every harness estimates its
own token count and under-counts; Claude Code compacts at "effective context minus a
13,000-token buffer", which is an estimate about an estimate. One measured session
believed it was under 32,768 and sent 40,433. `ai-bunker` counts with the serving
engine's own tokenizer, itemises the floor **by owner**, and refuses a session that has
no room to work — naming the component responsible rather than failing later as a
context-length error nobody can act on.

**Standards arrive whether the client asked or not.** A charter in each developer's
dotfiles drifts. Behind the endpoint there is one copy, versioned, and no way to use the
model without it.

## Where this project is behind

Worth stating, since a landscape where one tool wins every column is a landscape nobody
believes.

- **Provider breadth: LiteLLM, by a wide margin.** A hundred providers against whatever
  you configure here. If the question is "call many providers through one client",
  LiteLLM is simply the answer, and `ai-bunker` can sit in front of it rather than
  compete.
- **Content classifiers: LLM Guard and Guardrails AI.** Their scanners are trained
  models and curated validator hubs; this project ships versioned regular expressions
  with an entropy gate. Regexes are reviewable, diffable and free to run — a deliberate
  trade, and on raw detection quality it is a trade, not a win.
- **Policy expressiveness and testing: OPA.** Rego expresses conditions a regex cannot,
  and OPA's test tooling with coverage is better than `rules --check`. The idea of
  policy carrying its own tests was taken from there.
- **Maturity.** This is `0.1.0-alpha` next to projects with years of production use.

## Ideas taken from the field

None of this was invented here, and saying so costs nothing.

- **Open Policy Agent: policy carries its own tests, and decisions are logged from day
  one.** Both are now load-bearing here — every shipped rule has `examples:` checked in
  continuous integration (CI), and that caught three wrong patterns before they reached
  a deployment.
- **gitleaks: regex *and* an entropy gate, plus per-rule allowlists.** A scanner that
  cries wolf teaches its readers to ignore it. The entropy threshold here was measured
  rather than guessed.
- **Microsoft's *spotlighting*: mark retrieved content as data.** Pattern matching
  catches clumsy injection attempts; the structural marking is what holds when the
  patterns miss.
- **The "prevention versus cure" split in agent-harness research.** Prevention agents
  bound context growth structurally; cure agents let it grow and compress. This project
  is prevention, moved server-side — which the taxonomy does not have a box for.

## Per-tool write-up

### LiteLLM

The de-facto open-source gateway: licensed under the terms the Massachusetts Institute
of Technology gave its name to (MIT), self-hostable, one OpenAI-shaped surface over a
hundred-plus providers, with virtual keys, budgets, fallbacks and retries. For sovereign
deployments it is the standard answer, and deservedly.

It routes; it does not inspect. Nothing in it reads a tool result, refuses a tool call,
or counts a session floor. Complementary rather than competing: `ai-bunker` in front of
LiteLLM gets both, and that is a reasonable deployment.

### Portkey

Gateway plus guardrails plus prompt versioning, with the broadest feature list in the
field. The catch for this niche is where those features run: semantic caching, guardrails
and versioning are primarily hosted SaaS — software as a service, running on the
vendor's machines — and the on-premises option is enterprise. A
guardrail that evaluates on someone else's servers is a guardrail that has already seen
the prompt.

### Kong AI Gateway

Makes sense when a gateway must live inside infrastructure you already run — and only
then. Heavy to operate otherwise, with PII redaction and enterprise single sign-on
(SSO) behind a paid licence.

### NeMo Guardrails

NVIDIA, Apache 2.0. Programmable rails in Colang across five rail types, with real
dialogue-flow control that regular expressions cannot express. The strongest of the rule
engines on expressiveness.

The trade is the DSL — a domain-specific language. Colang is a learning cost paid by
every reader of a rule file; this project's rules are regexes in YAML, a configuration
file format, with a description, and they re-read without a manual.
That trade is defensible at two people and gets worse as the rules get subtler.

### Guardrails AI

Apache 2.0, with a validator Hub covering hallucination, PII, toxicity and format
conformance. The validators are better than anything here on content classification, and
its testing culture is the closest in the field to this project's.

It is a library, not a gateway. An application that forgets to call it is unprotected.

### LLM Guard

The most security-focused of the three, with the best scanner set for prompt injection
and data leakage specifically. Same structural limit: called from your application
rather than standing in the path.

### Open Policy Agent

Not an LLM tool at all, and the best policy engine here. Rego expresses conditions a
regex cannot, `opa test` reports coverage, and decision logs are structured and
first-class. The two ideas this project took from it — policy ships with its tests,
decisions are logged by default — are the two that improved it most.

What it is not: in the path, and LLM-aware. It has no notion of a tool result, a token
budget or a system prompt.

### Client-side harness config

The default answer: `opencode.json`, `.claude/settings.json`, a plugin folder. It is the
only place some things *can* live — a file read is bounded before it happens, and no
endpoint can reach that. This project ships exactly those and no more
(see [`clients/`](clients/README.md)).

What it cannot do is hold: it is a file on a laptop, disabled by an edit, and absent the
moment someone opens a different harness.
