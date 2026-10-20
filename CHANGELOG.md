# Changelog

Semantic versioning. Dates follow ISO 8601, the International Organization for
Standardization's year-month-day order.

## [0.1.0] — 2026-10-19

First working version. Sizing, budget accounting, charter, rules, the gateway,
client kits and a dashboard.

### Hardware sizing

- A memory-roofline model over a catalogue of models and accelerators, keyed on
  the fact that decode speed is bounded by `bandwidth / active weight bytes`.
  Validated against published DGX Spark measurements (13.6 tok/s on Qwen3 8B,
  4.4 on Llama 70B Q4) to within the stated 70% efficiency assumption.
- `ai-bunker recommend --team N` solves the inverse problem, sizing on the
  **95th percentile** of a binomial rather than on the mean — a machine sized
  for average load is overloaded half the time.
- `sizing`, `compare`, `catalog`, `detect`. Every assumption is a flag.
- `docs/SIZING.md`: the buying decision for a two-person team, costed on prices
  surveyed 2026-10-19. The market for graphics processing units (GPUs) moved
  ~80% in eighteen months; a 2026
  sizing done on 2025 prices is wrong by a factor of two.

### Budget accounting

- `ai-bunker budget` itemises a session's floor **by owner** and gates on it.
  Three counting backends in descending order of trust (`server`, `local`,
  `ratio`), and the result always says which produced the number.
- `--gate` makes the verdict the exit code. A check that reports a failure and
  exits zero is not a check.

### Charter

- Standards served as a ~600-token index rather than pasted into every prompt.
  A page costs nothing until it is opened.
- A content fingerprint, usable both as a prefix-cache key and as provenance.

### Rules

- One format, two scopes (`output`, `command`), three severities, with the
  severity-by-scope table published because a `WARNING` on a `command` reads as
  if it stops something and does not.
- **Every rule ships with its own examples**, checked by `ai-bunker rules
  --check` in continuous integration (CI). Three shipped patterns were wrong on
  first write; the
  examples caught all three.
- **Indirect prompt injection** screened at the one chokepoint where it
  arrives, plus provenance marking (*spotlighting*) as the structural defence
  for what the patterns miss.
- Shannon entropy gate and per-rule allowlists, to tell a credential from a
  placeholder. The threshold (3.85) was measured, not guessed.
- A static guard rejects patterns with nested unbounded quantifiers before they
  can run. It caught two such patterns carried over from a working production
  rule set.
- A decision log recording which rule fired and what it did — **never the text
  it matched**.

### Gateway

- OpenAI-compatible: `/v1/models`, `/v1/chat/completions` (atomic and
  streaming), `/v1/embeddings`, `/v1/budget`, `/v1/charter`, `/v1/decisions`.
- Four stages: screen inbound tool results, inject the charter, measure and
  enforce the budget, screen outbound tool calls. Stages 1 and 4 are the rule
  engine's two scopes, and a gateway is the first place both exist at once.
- An exhausted budget is refused with HyperText Transfer Protocol (HTTP) status
  413 **naming the component
  responsible**, rather than failing downstream as a context-length error
  nobody can act on.
- Routing **by need** (`X-AI-Bunker-Need`) as well as by model name. An
  unconfigured need warns rather than falling back silently.
- `/mcp` exposes the charter as tools when `fastapi-mcp` is installed. Only the
  charter: `/v1/chat/completions` would be a model-calling tool inside a
  model's own turn, and `/v1/budget` is an operator's instrument. Importing
  `fastapi-mcp` costs ~24 seconds of startup on a cold interpreter, so
  `enforcement.mcp: false` turns the surface off, and the mount reports what it
  cost whenever it exceeds five seconds — a gateway that takes half a minute to
  answer should say which optional surface bought that.
- `ai-bunker doctor` checks that everything the deployment claims is true,
  including that an unauthenticated gateway is open on purpose.

### Client kits

- OpenCode and Claude Code configs, plus `ai-bunker adopt`.
- Deliberately thin: the gateway enforces everything it can see, so a kit
  carries only what happens *before a request exists* — bounded reads, no skill
  injection, compaction thresholds. The OpenCode kit is one config and **one**
  plugin.

### Dashboard

- `GET /gui`: the session floor by owner, the charter and its cost, the blocks
  the model sees, the decision log. No build step and **no external request** —
  a page whose purpose is to show that nothing leaves the network cannot start
  by fetching a stylesheet from a content delivery network (CDN).
- Two deterministic gates, `scripts/audit_contrast.py` and
  `scripts/lint_a11y.py`, both in CI and both tested for their ability to fail.
  The contrast auditor found four real failures on first run, none visible by
  eye.

### Site

- Eight hand-written pages in two languages, assembled from one shell rather
  than generated from Markdown, with the figures hand-authored as Scalable
  Vector Graphics (SVG).
- `scripts/audit_figures.py` checks the figures' contrast in **both** colour
  schemes against pairs that are declared rather than discovered. The figures'
  text sits on tints of the brand colours themselves, so a token that passes
  against white can fail against its own card — and the failures were
  light-scheme-only, which no amount of dark-mode review would have found.
- Every number the site quotes is tested against the repository that produced
  it, so hand-written pages cannot drift from the code.

### Security fixes found by running the real thing

- `global.generic_secret` anchored the keyword directly against the separator,
  so **`aws_secret_access_key = ...` — the literal spelling in
  `~/.aws/credentials` — did not match**, and its value class excluded `/` and
  `+`, so a base64 credential escaped on the first slash. Both fixed, with the
  failing cases added as rule examples.
- `global.vendor_token` is new: a bare `ghp_…`, `xoxb-…`, `sk-…`, `sk_live_…`
  or `AIza…` with no assignment around it is a live credential, and the generic
  rule only ever saw secrets with `key =` written in front of them. No entropy
  gate, for the reason the file already gives in reverse — a distinctive prefix
  is a stronger signal than randomness.
- Both were found by sending a real tool result through a real gateway to a
  real engine, not by reading the patterns. 17 rules, 107 assertions.

### Interoperability: the charter as an Agent Skill

- `ai-bunker skill` publishes the charter in the [Agent Skills](https://agentskills.io)
  format, an open specification read natively by Claude Code, OpenCode, Cursor,
  Goose, Amp, Roo, Codex, Copilot and Gemini CLI — a command-line interface. A
  client kit has to be
  written per client; this reaches the ones nobody will write a kit for.
- The export is close to a rename, because the two designs agree. The format's
  progressive disclosure loads `name` and `description` at startup, the
  `SKILL.md` body on activation, and bundled files on demand — which are this
  project's index, operating rules and pages, arrived at independently.
- Default output is `.claude/skills/`, because OpenCode documents that path as
  Claude-compatible: one copy, both clients, no duplicated files.
- The charter fingerprint travels in the skill's `metadata`, so a copy on disk
  can be checked against the charter the gateway is actually enforcing. The
  export is not a second source of truth.
- `ai-bunker skill --check` validates a skill directory against the
  specification's rules on `name`, `description`, `compatibility` and
  reference depth, and exits non-zero. Tested for its ability to fail.

### Known limitations

- Command screening does not apply to streamed completions: a tool call arrives
  in fragments, and refusing it would mean buffering the whole response.
  `/health` reports which guarantees are live.
- The shell-tool vocabulary (`SHELL_TOOLS`) is an overridable default, not a
  claim to completeness.
- The accessibility lint is static. Run a browser audit for what only a rendered
  page reveals.
- Sizing prices are a survey, not a quote, and they move fast.
