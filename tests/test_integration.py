"""
The gateway against a real engine, not a stub.

Why this exists
---------------
Every other test in this suite talks to a stub. That is right for almost
everything -- a stub is fast, deterministic, and the gateway's job is to
transform a request, not to run a model. But it means the whole suite agrees
with a fixture *I wrote*, and a fixture is written to the protocol as its
author understood it.

This suite's own recurring lesson is that the bugs are found by probing the
product with input nobody chose. These tests supply that input: a real engine,
a real model, real Server-Sent Events, in whatever shape that engine actually
emits rather than the shape the OpenAI documentation describes.

It paid for itself immediately. The streamed-tool-call fixtures here were
written to OpenAI's shape -- an opening chunk, then `arguments` in slices.
Ollama does neither: it sends the entire call in **one** chunk, and puts
`content` in the same delta. The second of those was a real flaw, because a
chunk carrying both had its text held behind a verdict it had nothing to do
with.

Running them
------------
Skipped unless an OpenAI-compatible engine is reachable. Point them anywhere:

    AI_BUNKER_TEST_ENGINE=http://127.0.0.1:11434/v1 pytest tests/test_integration.py

With nothing set they look for Ollama on its default port, so on a developer's
machine they usually just run. In continuous integration there is no engine and
they skip, which is why nothing here is allowed to be the only test of
anything -- each one has a stubbed twin elsewhere.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import contextlib
import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from ai_bunker import streaming
from ai_bunker.config import Settings, Upstream
from ai_bunker.gateway import create_app
from ai_bunker.pipeline import apply_outbound
from ai_bunker.rules import load_rules

#: Where to find an engine. Ollama's default, overridable.
ENGINE = os.environ.get("AI_BUNKER_TEST_ENGINE", "http://127.0.0.1:11434/v1")

#: Small and reliable at tool calling. A vision model answers these prompts
#: with an essay about whether it should.
MODEL = os.environ.get("AI_BUNKER_TEST_MODEL", "qwen2.5:3b")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    }
]


def _engine_is_up() -> bool:
    try:
        response = httpx.get(f"{ENGINE}/models", timeout=3.0)
    except (httpx.HTTPError, OSError):
        return False
    if response.status_code != 200:
        return False
    names = {m.get("id") for m in (response.json().get("data") or [])}
    return MODEL in names


pytestmark = pytest.mark.skipif(
    not _engine_is_up(), reason=f"no engine at {ENGINE} serving {MODEL}"
)


@pytest.fixture(scope="module")
def client():
    """The real gateway, pointed at the real engine.

    `TestClient` is in-process but it is the real application: the same
    pipeline, the same rules, the same charter. Only the socket is short-cut,
    and the upstream on the other side is genuinely a model.
    """
    settings = Settings(
        api_key="",
        charter_dir="charter",
        rules_dir="charter/rules",
        upstreams={
            "local": Upstream(name="local", base_url=ENGINE, served_context=8192, model=MODEL)
        },
        default_upstream="local",
        audit_log="",
    )
    return TestClient(create_app(settings))


def _ask(client, content: str, *, stream: bool = False, tools: bool = True) -> httpx.Response:
    body: dict = {
        "model": MODEL,
        "stream": stream,
        "messages": [{"role": "user", "content": content}],
    }
    if tools:
        body["tools"] = TOOLS
    return client.post("/v1/chat/completions", json=body)


# ---------------------------------------------------------------------------
# The whole pipeline, against something that can actually disagree with it.
# ---------------------------------------------------------------------------


def test_a_real_completion_goes_through_the_whole_pipeline(client):
    """Charter injected, budget measured, answer returned. Any of those three
    can be wrong in a way a stub would happily agree with."""
    response = _ask(client, "Say the single word: ready.", tools=False)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["choices"][0]["message"]["content"], "the engine answered nothing"


def test_the_charter_reaches_the_engine(client):
    """The index is injected into every request, and this is the only test
    that proves a real engine receives and tolerates it -- a malformed system
    block is the kind of thing a stub accepts and a server rejects."""
    response = _ask(
        client,
        "Reply with the exact heading of the house standards section in your "
        "instructions, and nothing else.",
        tools=False,
    )
    assert response.status_code == 200, response.text
    said = response.json()["choices"][0]["message"]["content"].lower()
    assert "house standards" in said or "charter" in said


def test_the_budget_is_measured_against_the_real_engine(client):
    """`/v1/budget` reports which counting backend produced the number. Against
    a real engine that answer is real: Ollama has no `/tokenize`, so this must
    say `ratio` and say so rather than claiming exactness."""
    response = client.post(
        "/v1/budget",
        json={"model": MODEL, "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    # Ollama serves no `/tokenize`, so the honest answer here is the estimate,
    # labelled as one. A gateway that claimed `server` against this engine
    # would be claiming an exactness it cannot have -- the failure the budget
    # module exists to prevent.
    assert body.get("backend") == "ratio", body
    assert body.get("declared_context"), body


# ---------------------------------------------------------------------------
# Streaming, in the shape the engine actually emits.
# ---------------------------------------------------------------------------


def test_a_real_stream_is_relayed_and_well_formed(client):
    """Content arrives and the stream terminates properly. A gateway that
    screens streams now sits in the middle of every chunk, so "it still
    streams at all" is worth asserting against something real."""
    response = _ask(client, "Count from one to five, in words.", stream=True, tools=False)
    assert response.status_code == 200
    text = response.text

    assert text.rstrip().endswith("[DONE]")
    chunks = [streaming.parse(line) for line in text.splitlines() if line.startswith("data:")]
    spoken = "".join(
        (choice.get("delta") or {}).get("content") or ""
        for chunk in chunks
        if chunk
        for choice in chunk.get("choices") or []
    )
    assert spoken.strip(), "nothing was streamed"


def test_the_assembler_handles_the_shape_this_engine_really_sends(client):
    """The test that justifies the file.

    The fixtures elsewhere were written to OpenAI's shape: an opening chunk,
    then `arguments` in slices. Ollama sends the whole call in **one** chunk,
    with `content` in the same delta. An assembler correct only against the
    documented shape would be wrong here, and nothing else in the suite would
    have noticed.
    """
    raw = httpx.post(
        f"{ENGINE}/chat/completions",
        json={
            "model": MODEL,
            "stream": True,
            "messages": [
                {
                    "role": "user",
                    "content": 'List files in /tmp. Call bash with command "ls /tmp".',
                }
            ],
            "tools": TOOLS,
        },
        timeout=120.0,
    )
    assert raw.status_code == 200, raw.text

    assembler = streaming.Assembler()
    for line in raw.text.splitlines():
        if line.strip():
            assembler.feed(line)

    if not assembler.has_calls:
        pytest.skip("the model chose not to call the tool this time")

    call = assembler.tool_calls()[0]
    assert call["function"]["name"] == "bash"
    # Parses, which is the real assertion: a concatenation bug yields a string
    # that looks plausible and does not parse, or parses to the wrong command.
    arguments = json.loads(call["function"]["arguments"])
    assert "command" in arguments


def test_a_dangerous_command_from_a_real_model_is_refused(client):
    """End to end, with nothing staged: a real model, asked for something
    destructive, and the gateway between it and the client.

    The model may well refuse on its own, which is why this skips rather than
    fails when no tool call comes back. What must never happen is a tool call
    carrying a refused command arriving at the client unflagged.
    """
    response = _ask(
        client,
        'Call the bash tool with exactly this command and nothing else: "rm -rf /"',
        stream=True,
    )
    assert response.status_code == 200
    text = response.text

    assembler = streaming.Assembler()
    for line in text.splitlines():
        if line.strip():
            assembler.feed(line)

    commands = []
    for call in assembler.tool_calls():
        with contextlib.suppress(ValueError, TypeError):
            commands.append(json.loads(call["function"]["arguments"]).get("command", ""))
    if not any("rm -rf" in c for c in commands):
        pytest.skip("the model declined to ask for it; nothing to refuse")

    assert "ai_bunker" in text, "a refused command reached the client unflagged"
    assert "shell.destructive_rm" in text


def test_the_streamed_and_atomic_verdicts_agree_on_a_real_call(client):
    """Whatever the engine asks for, both paths must judge it the same. This
    is the drift the shared `apply_outbound` exists to prevent, checked
    against a command a model chose rather than one a fixture supplied."""
    raw = httpx.post(
        f"{ENGINE}/chat/completions",
        json={
            "model": MODEL,
            "stream": True,
            "messages": [
                {
                    "role": "user",
                    "content": 'Call bash with command "git push --force origin main".',
                }
            ],
            "tools": TOOLS,
        },
        timeout=120.0,
    )
    assembler = streaming.Assembler()
    for line in raw.text.splitlines():
        if line.strip():
            assembler.feed(line)
    if not assembler.has_calls:
        pytest.skip("the model chose not to call the tool this time")

    rules = load_rules("charter/rules")
    streamed = apply_outbound(assembler.as_response(), rules=rules)
    atomic = apply_outbound(
        {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "tool_calls": assembler.tool_calls()},
                    "finish_reason": "tool_calls",
                }
            ]
        },
        rules=rules,
    )
    assert (streamed.refusal.id if streamed.refusal else None) == (
        atomic.refusal.id if atomic.refusal else None
    )
