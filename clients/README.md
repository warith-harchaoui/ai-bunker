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
never compacts halves the number of sessions a graphics processing unit (GPU)
carries, for identical output.

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

## Two kinds of client, and why their kits differ

A **code agent** is somebody else's loop. The kit is a config file, and it has
to reach into the harness for the three rows marked **client** above, because
the harness is what decides them.

An **agent framework** is your loop. There is no harness to configure: bounded
reads, what goes in the prompt and when to compact are all code you already
write. So the kit is a module you import, and it carries only the two things a
framework cannot get right on its own — which endpoint to call, and what
context window to believe.

Thinner is not weaker. The charter, the secret and injection screening, the
refusal of dangerous commands and the token count all live behind the endpoint
and apply to both kinds identically. Verified rather than asserted: a tool
result carrying `AWS_ACCESS_KEY_ID=AKIA...` sent through the LangGraph kit came
back redacted, logged as `global.aws_access_key`, before the model read it.

## Installing

```bash
ai-bunker adopt /path/to/project                  # charter + both code-agent kits
ai-bunker adopt /path/to/project --client opencode
ai-bunker adopt /path/to/project --client langgraph --client smolagents
ai-bunker adopt /path/to/project --list           # what would be written
```

Nothing is overwritten without `--force`, and the gateway's URL — its uniform
resource locator — and key come from the environment so a kit can be
committed.

**Code agents** (written by default):

- [`opencode/`](opencode) — provider config plus one plugin, for the one thing
  the gateway cannot do.
- [`claude-code/`](claude-code) — settings and environment.

**Agent frameworks** (opt-in, because a kit that writes Python into a
repository by default is authoring application code rather than configuring a
tool):

- [`langgraph/`](langgraph) — `ChatOpenAI`, so anything built on LangChain
  works too. `pip install langchain-openai`
- [`llamaindex/`](llamaindex) — `OpenAILike` rather than `OpenAI`, which
  validates model names against OpenAI's own catalogue and refuses every model
  a sovereign deployment serves. `pip install llama-index-llms-openai-like`
- [`smolagents/`](smolagents) — `OpenAIModel`. `pip install smolagents`

One warning that belongs with the code rather than in a footnote: a smolagents
`CodeAgent` executes the model's Python locally by default. The gateway refuses
dangerous *shell* commands because it sees them as tool calls before they run,
and it cannot see an `exec` inside the harness at all. Use
`executor_type="docker"` for anything that is not a toy. It is the one risk a
gateway genuinely does not cover, and the kit says so in its own docstring.
