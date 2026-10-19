# Client kits

**Thin on purpose.** Everything the gateway can see, the gateway enforces —
for every client, with no way to opt out by swapping harness. What is left for
a client kit is exactly the set of things that happen *before a request exists*,
which no endpoint can reach.

## The division of labour

| | Enforced by | Why there and not elsewhere |
|---|---|---|
| Secrets in tool output | **gateway** | It sees the `role: "tool"` message |
| Prompt injection in tool output | **gateway** | Same message, same chokepoint |
| Dangerous shell commands | **gateway** | It sees the `tool_call` before the command runs |
| Session floor / budget | **gateway** | Only the server holds the tokenizer |
| The charter | **gateway** | Injected into every request, whoever sent it |
| **Bounded file reads** | **client** | The gateway never sees a read. By the time the result arrives in a tool message, the tokens are already spent in the request |
| **Skill / tool-schema injection** | **client** | The gateway can *detect* a bloated floor and refuse, but it cannot stop a client from building the prompt that way |
| **Compaction thresholds** | **client** | Compaction happens entirely client-side, between turns |
| Declared context | **client**, audited by the gateway | `GET /v1/models` publishes what the gateway expects; a client that declares more will eventually be refused |

The asymmetry is the point. A client kit cannot be trusted — it is a config file
on someone's laptop — so nothing load-bearing lives in one. But the three rows
marked **client** are structurally out of the gateway's reach, and a deployment
that ignores them pays for it in hardware: an agent that reads whole files and
never compacts halves the number of sessions a GPU carries, for identical output.

## Verifying a client, from the server

A client kit is a claim. `POST /v1/budget` is how you check it:

```bash
# Capture what your client actually sends (any proxy will do), then:
curl -s -H "Authorization: Bearer $AI_BUNKER_API_KEY" \
     -H 'Content-Type: application/json' \
     http://127.0.0.1:8000/v1/budget -d @captured-request.json
```

The response itemises the floor by owner. A client whose tool schemas or skill
blocks dominate it is misconfigured, and the report says which component to
attack first. That measurement found a workstation injecting 59 skill
descriptions into every prompt — 17,754 tokens, 68% of the floor — which made
every session loop without answering while the harness said nothing.

## Installing

```bash
ai-bunker adopt /path/to/project                  # charter + both client kits
ai-bunker adopt /path/to/project --client opencode
ai-bunker adopt /path/to/project --list           # what would be written
```

Nothing is overwritten without `--force`, and the gateway URL and key come from
the environment so a kit can be committed.

- [`opencode/`](opencode) — provider config plus one plugin, for the one thing
  the gateway cannot do.
- [`claude-code/`](claude-code) — settings and environment.
