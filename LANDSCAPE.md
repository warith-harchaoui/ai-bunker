# Landscape

[🇫🇷 PAYSAGE.md](PAYSAGE.md) · 🇬🇧 English

Tools that sit between a coding agent and a model, compared against `ai-bunker`.
Ratings are ⭐ (1) to ⭐⭐⭐⭐⭐ (5), scored on this project's intended job: **stand in
front of your own graphics processing unit (GPU) and enforce, for every client, a
charter, a rule engine and a context budget the server actually counts.**

A tool optimised for a different job is not being criticised; the score reflects fit to
*this* niche. Several entries below are excellent at theirs, and three of them are
better than this project at something named in the table.

Three abbreviations run through the names in the table and the prose after it: **AI**
is artificial intelligence, an **LLM** is a large language model — the kind of model
every tool here stands in front of — and **MCP** is the Model Context Protocol, the
standard by which an agent discovers and calls tools.

Surveyed 2026-10-19, re-surveyed 2026-10-20 and 2026-10-29.

## At a glance

<!-- TABLE:START -->
| Serving layer | Nothing leaves the network | Screens what the agent reads | Screens the tool declarations | Refuses what the agent runs | Isolates tool execution | Counts the budget server-side | Serves team standards | Rules ship with tests | Any OpenAI client | Provider breadth |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **ai-bunker** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| LiteLLM | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Bifrost | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Portkey | ⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Kong AI Gateway | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| agentgateway | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| Envoy AI Gateway | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| NeMo Guardrails | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| Guardrails AI | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| LLM Guard | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ |
| agent-scan (ex mcp-scan) | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐ | ⭐ |
| ToolHive | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐⭐ | ⭐⭐ | ⭐ | ⭐ |
| Docker MCP Gateway | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ | ⭐ | ⭐ | ⭐ |
| Open Policy Agent | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | ⭐ |
| Client-side harness config | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐⭐ | ⭐ | ⭐ | ⭐⭐ |
<!-- TABLE:END -->

## Positioning map

<!-- FIGURE:START -->
A two-dimensional representation of the table above, by principal component
analysis (PCA) (see [`standpoint`](https://github.com/warith-harchaoui/standpoint)).
The map is drawn from `assets/landscape.csv`, which is the same table rendered as
numbers; `tests/test_landscape.py` fails if the two stop agreeing.

![Positioning map](https://raw.githubusercontent.com/warith-harchaoui/ai-bunker/main/assets/landscape.png)

Read it as a shape, not a scoreboard. The axes read **Horizontal — Resourceful ↔
Vigilant** and **Vertical — Protected ↔ Disciplined**, and they are not fixed labels:
they are what the criteria decompose into, so every row added rotates them. Together
they carry 58% of the table — 29.5% and 28.2%, which is worth saying plainly: two
axes explaining a little over half of ten columns is a sketch of the field, not a
measurement of it. The 42% they drop is why the prose below exists.
<!-- FIGURE:END -->

## What the map actually shows

![A turn travelling left to right through four boxes — a coding agent, the gateway position, a serving engine and the tool servers — with the tools that stand at each listed underneath: client-side configuration and guardrail libraries at the agent; LiteLLM, Kong, Portkey, Bifrost, agentgateway, the Envoy AI Gateway and ai-bunker at the gateway; ToolHive, the Docker MCP Gateway and agent-scan around the tool servers. Nothing stands at the serving engine.](assets/figure-path.svg)

The map above places a tool by how it scores; this one places it by where it stands, which the scoring cannot show. Two tools a centimetre apart in the scatter can sit on opposite sides of the serving engine.

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

**Bottom right — the Model Context Protocol layer.** ToolHive and the Docker MCP
Gateway run each tool server in its own container, inject secrets at call time, and keep
an inventory so nobody is running a server the security team never heard of — what the
Open Worldwide Application Security Project (OWASP), in its MCP Top 10, calls a
*shadow* server. `agent-scan` (the former `mcp-scan`, now
Snyk's) reads tool descriptions and finds poisoned ones, detects **rug pulls** by hashing
each description and noticing when it changes, and spots shadowing by comparing
descriptions across servers. This cluster is the one this project has the most to learn
from, and the one it overlaps least: they secure the tool *servers*, where this secures
the *conversation*.

**Bottom right also — policy without a position.** Open Policy Agent writes and tests
policy better than anything here, and is not in the request path at all. A client-side
harness config is in the path and is a file on a laptop.

**Upper middle — the agent-native gateways, and they are new.** `agentgateway` and
the Envoy AI Gateway did not exist in this table ten days ago and they are the most
important change in it. Both are proxies in the request path, both are self-hostable
in front of a local engine, both carry MCP tool policy, and both count tokens. They
sit between the routing cluster and this project's corner, which is exactly where the
field is moving.

**Top right is thinly populated, and emptier than it looks.** The combination this
project stands on — the gateway's position (every request, every client, no opt-out)
plus the rule engine's inspection plus a budget the server counts — is still not
assembled anywhere else in one process. But the gap narrowed twice this month, and
the honest version of the claim is narrower with it.

Two distinctions survive, and only two. The first is **which count, and what for**.
Token budgets at the gateway are now an ordinary feature: `agentgateway` does
tokens-per-minute, the Envoy AI Gateway does token-aware rate limiting with per-team
cost attribution. Those count *spend*, against a quota, to control a bill. This
counts the **context window** — the floor a session pays before anyone speaks,
measured with the serving engine's own tokenizer, itemised **by owner**, and refused
when what is left cannot hold a conversation. A gateway that rate-limits you at
10,000 tokens a minute has said nothing about whether your next request fits.

The second is **the charter**. `agentgateway`'s own documentation is explicit that it
never modifies a prompt, and that is a reasonable position for a proxy whose job is
transport. It is the opposite of this one. A standard that only arrives when the
client remembers to send it is not a standard, and the only place it can arrive
without the client's cooperation is behind the endpoint.

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
- **Isolation: ToolHive and the Docker MCP Gateway, completely.** They run each tool
  server in a container with restricted privileges and inject secrets at call time.
  This project isolates nothing: it decides what may run and then hands the command
  back to a harness that runs it on the host. That is the gap the Day 4 whitepaper
  calls Pillar 1, and closing it is not a gateway's job — pointing at someone whose job
  it is, is.
- **Tool provenance: `agent-scan`.** It reads the client's own configuration, so it
  knows which server each tool came from and can compare descriptions across origins.
  An OpenAI-shaped request does not carry that, so this project can report a colliding
  pair and cannot say which half is the impostor.
- **Throughput: Bifrost.** Written in Go specifically to get out from under Python's
  global interpreter lock, with semantic caching. This is Python in the request path,
  and honest about it.
- **Admission accounting: `go-llmflow/gateway`, and this one is a hole.** Its budget
  work reserves a request's **worst-case** cost before admitting it and settles
  afterwards, because counting after the response lets concurrent requests all check
  against the same figure and overshoot together — measured there at 3.3× the limit
  under concurrency against 0.03% with holds. This project screens and measures a
  request, then admits it; `max_tokens` does not enter the ceiling check at all, so a
  request admitted just under the line can produce a turn that is over it. The
  arithmetic is the same arithmetic and it is not implemented here yet.
- **Governance: `agentgateway`.** It is a Linux Foundation project with an
  institutional home for the gateway layer. This is one author's repository. For
  anyone whose procurement asks who owns the thing, that is the answer and it is not
  this one.
- **Maturity.** This is `0.2.0-alpha` next to projects with years of production use.

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
- **`agent-scan`: a tool description is worth screening, and worth hashing.** The first
  half arrived here as the `tool` scope. The second half — pinning each description and
  noticing when a server quietly changes one after it was approved, the *rug pull* — was
  named here as the best idea in this survey that this project had not taken, and it is
  taken now: `tool.contract_changed`, in two tiers. What is still theirs alone is
  knowing which server a tool came from, which an OpenAI-shaped request does not say.
- **`go-llmflow/gateway`: reserve, then settle.** The pattern above, named here
  because it is the best idea in this survey that this project has **not** taken. A
  gate that checks and then admits is a gate that two concurrent requests walk
  through together. Recorded in `.private/ASSESSMENTS.md` as the next round's work
  rather than claimed here as a feature.
- **Envoy AI Gateway: attribution applies to money too.** Per-team cost attribution
  is the floor-by-owner argument pointed at the invoice instead of the window. The
  two are the same sentence — a number nobody can decompose is a number nobody can
  reduce — and seeing it arrive independently in a second product is the best
  evidence the argument is right.
- **Cisco's MCP Scanner: YARA rules for tool metadata.** A rule format with a decade
  of tooling behind it, pointed at tool descriptions. This project's rules are
  versioned regular expressions with their own `examples:`; a shared, portable rule
  format is strictly better than a private one, and that is worth saying even though
  nothing has been taken from it yet.
- **Google's 5-Day AI Agents course, Day 4.** Named two obfuscation techniques this
  project had never tested itself against. Three of six probes walked past every rule,
  and two walked past a `BLOCKER`. The value was the checklist, not the knowledge: the
  paper says invisible payloads bypass *human review* and never claims they bypass
  pattern matching, which is the part the probes found.

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

### Bifrost

Written in Go specifically to get out from under Python's global interpreter lock,
which is the bottleneck every Python gateway shares — this one included. It speaks the
Model Context Protocol in both directions, acting as client and server so an agent
connects to one endpoint while Bifrost brokers the tools behind it, and it ships regex,
secret detection, model-as-judge and MCP guardrail rules.

The relevant caveat for this comparison is tiering: the content-safety guardrails are an
enterprise feature, where Portkey ships comparable ones in its open-source gateway. On
throughput it is simply ahead of anything written in Python.

### agentgateway

Solo.io's Rust proxy, donated to the Linux Foundation and the fourth project under the
Agentic AI Foundation as of June 2026 — the first time the gateway layer itself got an
institutional governance home, which matters more than any single feature. One data
plane for HyperText Transfer Protocol (HTTP), gRPC, MCP, Agent2Agent (A2A) and LLM
traffic, so the agent and non-agent halves of a network are run with one set of
patterns. Virtual application programming interface (API) keys per consumer, tool-level
role-based access control, denial-of-wallet limits, tokens-per-minute accounting rather
than request-rate limits, health-based failover, OpenTelemetry out of the box.

It is the closest thing in this table to this project's position, and the two differ on
exactly two things. Its token accounting **settles after the response**, by reading
usage off the model's reply — a quota for spend, not a check that the next request
fits. And it does not touch prompts, by design and by documentation. That is the right
call for a transport-layer proxy and it is why a charter cannot live there.

If the job is "one governed front door for every protocol an agent speaks", this is the
answer and this project is not competing with it. Put `ai-bunker` behind it.

### Envoy AI Gateway

Envoy and the Kubernetes Gateway API, extended with LLM-aware routing; renamed Agent
Router. Version 1.0 in June 2026: sixteen providers behind one OpenAI-compatible
surface, cross-provider translation, provider fallback, token-aware rate limiting, and
an MCP gateway with per-tool authorization expressed in the Common Expression Language
(CEL).

Two things here are worth taking seriously. **Per-team cost attribution** is the same
instinct as this project's floor-by-owner — a number nobody can decompose is a number
nobody can reduce — applied to spend rather than to context. And **CEL for per-tool
authorization** is a real policy language in the request path, which is more than a
regular expression can express and less than Rego; the comparison that matters is with
Open Policy Agent below, not with this project.

The cost is the Envoy configuration model, which is a large thing to learn if you are
not already in that ecosystem, and the whole stack assumes Kubernetes. For one
workstation with one graphics card, that is a great deal of machinery.

### agent-scan (formerly mcp-scan)

Invariant Labs built it, Snyk now publishes it, and it does the thing this project's
`tool` scope does — read tool descriptions and find the poisoned ones — plus two things
this project cannot. It hashes each description and reports a **rug pull** when a server
quietly changes one after approval, and it compares descriptions across servers to find
shadowing, which it can do because it reads the client's own configuration and therefore
knows where each tool came from.

One trade worth naming, because this project's first column is about it: by default
`agent-scan` sends tool names and descriptions to a hosted guardrail application
programming interface (API), and says so —
`--local-only` keeps everything on the machine at a stated cost in accuracy.

### ToolHive

Runs each Model Context Protocol server in its own container with restricted
privileges, with a registry, audit logs and identity enforcement, aimed squarely at
ending *shadow* servers — the ones nobody put in an inventory. Desktop application,
command-line tool and a Kubernetes operator.

It is the clearest example of the gap in this project: `ai-bunker` decides what may run
and then hands the command back to a harness that runs it on the host. ToolHive is the
answer to the question this one does not attempt.

### Docker MCP Gateway

The same idea with Docker's distribution behind it: one container per tool server,
secrets injected at call time rather than sitting in a configuration file. Narrower than
ToolHive and, for a team already running Docker, closer to free.

### Client-side harness config

The default answer: `opencode.json`, `.claude/settings.json`, a plugin folder. It is the
only place some things *can* live — a file read is bounded before it happens, and no
endpoint can reach that. This project ships exactly those and no more
(see [`clients/`](clients/README.md)).

What it cannot do is hold: it is a file on a laptop, disabled by an edit, and absent the
moment someone opens a different harness.

It is worth separating the two halves of this row, because they score differently and
the vendor separates them too. A hook *is* enforcement — that is why this column is not
one star. An instruction file is not, and Anthropic says so about its own:

> Claude treats them as context, **not enforced configuration**. To block an action
> regardless of what Claude decides, use a PreToolUse hook instead.
>
> — Anthropic, [*How Claude remembers your project*](https://code.claude.com/docs/en/memory)

So a `CLAUDE.md` is not a weaker version of a rule engine; it is a different kind of
thing, and the gap is the vendor's own description rather than this project's
characterisation of a competitor. What remains, for the hook that does enforce, is
reach: it binds one harness on one machine, and the row is scored on that.
