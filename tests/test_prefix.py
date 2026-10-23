"""
The charter block has to be byte-identical from one request to the next.

Why this exists
---------------
This project's central efficiency claim is "index, don't concatenate": a
charter served as a short index that every request carries, with pages read on
demand. That only pays if an engine's prefix cache **hits** -- and a prefix
cache hits on identical leading tokens, nothing less.

Nothing asserted it. A session identifier, a timestamp, a count of anything,
or injecting the charter *after* the client's own system message would each
make the leading bytes vary per request or per client, the cache would miss
every time, and the claim would be quietly void while every other test stayed
green. There is no symptom to notice: the gateway would be correct and slow.

Measured before this file existed, over five request shapes and three client
system-prompt arrangements: one distinct block, 2,430 characters, in every
case.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import hashlib

import pytest

from ai_bunker.budget import Counter
from ai_bunker.charter import load_charter
from ai_bunker.pipeline import apply_inbound
from ai_bunker.rules import load_rules

SERVED = 32768


@pytest.fixture(scope="module")
def engine():
    return load_charter("charter"), load_rules("charter/rules"), Counter(allow_ratio=True)


def _prepared(engine, body):
    charter, rules, counter = engine
    return apply_inbound(
        body, charter=charter, rules=rules, counter=counter, served_context=SERVED
    ).request["messages"]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


SHAPES = {
    "plain": {"model": "m", "messages": [{"role": "user", "content": "hello"}]},
    "a different question": {
        "model": "m",
        "messages": [{"role": "user", "content": "something else entirely"}],
    },
    "with a tool declared": {
        "model": "m",
        "messages": [{"role": "user", "content": "hi"}],
        "tools": [{"type": "function", "function": {"name": "bash", "description": "run"}}],
    },
    "with a tool result": {
        "model": "m",
        "messages": [
            {"role": "user", "content": "hi"},
            {"role": "tool", "content": "build passed"},
        ],
    },
    "the first one again": {"model": "m", "messages": [{"role": "user", "content": "hello"}]},
}


def test_the_injected_charter_is_the_same_bytes_every_time(engine):
    """Five request shapes, one block.

    A prefix cache keys on identical leading tokens. Anything request-specific
    in here -- a session, a timestamp, a count -- costs every hit, and costs
    them invisibly.
    """
    digests = {
        label: _digest(
            "\n".join(
                m.get("content") or "" for m in _prepared(engine, body) if m.get("role") == "system"
            )
        )
        for label, body in SHAPES.items()
    }
    assert len(set(digests.values())) == 1, (
        "the charter block varies between requests, so an engine's prefix "
        f"cache cannot hit: { ({k: v[:12] for k, v in digests.items()}) }"
    )


def test_the_charter_leads_whatever_the_client_sends(engine):
    """And it has to be *first*.

    Injected after the client's own system message, the cacheable prefix would
    start with text the client chose: stable for one client, different for
    every other, and a shared engine would cache one prefix per harness
    instead of one for the deployment.
    """
    arrangements = {
        "no client system": [{"role": "user", "content": "hi"}],
        "client system first": [
            {"role": "system", "content": "You are Bob."},
            {"role": "user", "content": "hi"},
        ],
        "a different client system": [
            {"role": "system", "content": "You are Alice, entirely different."},
            {"role": "user", "content": "hi"},
        ],
    }
    firsts = {}
    for label, messages in arrangements.items():
        prepared = _prepared(engine, {"model": "m", "messages": messages})
        assert prepared[0].get("role") == "system", f"{label}: the charter must lead"
        firsts[label] = _digest(prepared[0].get("content") or "")
    assert len(set(firsts.values())) == 1, (
        "the first message differs between clients, so each one gets its own "
        f"cached prefix: { ({k: v[:12] for k, v in firsts.items()}) }"
    )


def test_the_client_keeps_its_own_system_message(engine):
    """The other direction: leading must not mean replacing. A gateway that
    dropped the client's instructions to protect its prefix would be trading
    the harness's behaviour for a cache hit."""
    prepared = _prepared(
        engine,
        {
            "model": "m",
            "messages": [
                {"role": "system", "content": "You are Bob."},
                {"role": "user", "content": "hi"},
            ],
        },
    )
    assert any("You are Bob." in (m.get("content") or "") for m in prepared)
