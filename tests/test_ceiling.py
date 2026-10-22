"""
The request-size ceiling: refused unread rather than read for minutes.

Why this exists
---------------
Screening costs time linearly in the length of what arrives, and until this
ceiling nothing bounded the total. `MAX_SCREEN_CHARS` bounds one *slice* and a
tool result arrives in as many slices as its length requires. The budget does
not catch it either, and that is deliberate: `measure_request` counts the
system messages and the tool schemas, because conversation is what compaction
reduces -- so a 40 MB tool result passes the budget and is forwarded.

Found by asking what a hostile request *shape* costs. One tool result of
40 MB -- a tool that read a large file, no hostility required -- took minutes
of a synchronous screen inside an asynchronous handler, during which the
gateway served nobody, and then went upstream to an engine that would refuse
it for context length anyway.

The tests that matter here are the two that could go wrong in opposite
directions: that nothing is screened above the line, and that nothing changes
below it.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import httpx
import pytest

from ai_bunker.budget import (
    CEILING_CHARS_PER_TOKEN,
    CHARS_PER_TOKEN,
    Counter,
    request_chars,
)
from ai_bunker.config import Settings, Upstream
from ai_bunker.pipeline import RequestTooLarge, apply_inbound

SERVED = 32768
CEILING = SERVED * CEILING_CHARS_PER_TOKEN


# ---------------------------------------------------------------------------
# Counting the request, which has to be cheap and must not recurse.
# ---------------------------------------------------------------------------


def test_the_count_includes_keys_as_well_as_values():
    """A request made of a million one-character keys is not cheaper than one
    made of a million one-character values, and the engine will tokenize
    both."""
    assert request_chars({"ab": "cde"}) == 5
    assert request_chars({}) == 0
    assert request_chars([{"a": "b"}, {"c": "d"}]) == 4


def test_the_count_does_not_recurse():
    """The depth of a request body is chosen by whoever sends it.

    A recursive walk would be a stack that deep, which is the defect this
    whole module is about wearing different clothes: two thousand levels of
    nesting is a legal JSON document and a 413 is a better answer than a
    `RecursionError`.
    """
    deep: object = {"end": "x"}
    for _ in range(5000):
        deep = {"n": deep}
    assert request_chars(deep) == 5000 + 3 + 1  # 5,000 "n" keys, "end", "x"


def test_a_cycle_is_not_this_function_s_problem():
    """`request_chars` reads a body parsed from JSON, which cannot contain a
    cycle. Asserted so the next reader does not add a `seen` set to defend
    against something the parser makes impossible -- and pays for it on every
    request."""
    import json

    assert json.loads(json.dumps({"a": [{"b": "c"}]})) == {"a": [{"b": "c"}]}


# ---------------------------------------------------------------------------
# The ceiling itself, and the reason the number is what it is.
# ---------------------------------------------------------------------------


def test_the_ceiling_is_far_above_anything_that_could_fit():
    """The property that makes the ceiling safe, tied to the ratio it is
    measured against.

    `CHARS_PER_TOKEN` is the measured *floor*, so the largest request that
    could ever fit a served context is about `served * CHARS_PER_TOKEN`
    characters. The ceiling must sit well clear of that: refusing a request
    that would have fitted is a worse failure than screening one that would
    not have.

    Asserted as a relationship rather than as two numbers, so lowering the
    ceiling into the legitimate range fails here instead of in production.
    """
    largest_that_fits = SERVED * CHARS_PER_TOKEN
    assert largest_that_fits * 5 < CEILING, (
        f"the ceiling is {CEILING:,} characters and a request that fits can be "
        f"{largest_that_fits:,.0f}; that margin is too thin to be safe"
    )


def _kwargs(**over):
    from ai_bunker.charter import load_charter
    from ai_bunker.rules import load_rules

    base = {
        "charter": load_charter("charter"),
        "rules": load_rules("charter/rules"),
        "counter": Counter(allow_ratio=True),
        "served_context": SERVED,
    }
    base.update(over)
    return base


def test_a_request_past_the_ceiling_is_refused_before_anything_screens_it(monkeypatch):
    """The assertion that justifies the whole change: *nothing* ran.

    A guard that refuses after screening has saved nobody anything, and a
    timing would only prove it on the machine that ran it -- round 7's lesson,
    and round 9 ignored it. So the screen is replaced with something that
    raises if it is ever reached.
    """
    import ai_bunker.pipeline as pipeline

    def refuse(*args, **kwargs):
        raise AssertionError("the request was screened despite being over the ceiling")

    monkeypatch.setattr(pipeline, "screen_inbound", refuse)
    monkeypatch.setattr(pipeline, "screen_tools", refuse)

    body = {"model": "m", "messages": [{"role": "tool", "content": "A" * (CEILING + 1)}]}
    with pytest.raises(RequestTooLarge) as caught:
        apply_inbound(body, **_kwargs())

    assert caught.value.ceiling == CEILING
    assert caught.value.chars > CEILING
    # The message has to name both numbers: a client told only "too large"
    # cannot tell whether to split the request or give up.
    assert f"{CEILING:,}" in str(caught.value)
    assert f"{caught.value.chars:,}" in str(caught.value)


def test_a_request_under_the_ceiling_is_screened_exactly_as_before():
    """The other direction, which is the one that would be a security
    regression: the guard must not shadow the screening for anything that
    fits.

    A secret below the line still has to come back redacted -- otherwise a
    ceiling introduced to bound a cost has quietly become a way past the
    rules.
    """
    secret = "api_key = sk-" + "a" * 32
    body = {"model": "m", "messages": [{"role": "tool", "content": f"before {secret} after"}]}
    applied = apply_inbound(body, **_kwargs())

    sent = str(applied.request["messages"])
    assert secret not in sent, "a secret under the ceiling must still be redacted"
    assert applied.inbound, "the rule must still be reported as having fired"


def test_the_boundary_is_not_off_by_one():
    """Exactly at the ceiling passes; one character past it does not."""
    body = {"model": "m", "messages": [{"role": "tool", "content": ""}]}
    body["messages"][0]["content"] = "A" * (CEILING - request_chars(body))
    assert request_chars(body) == CEILING, "the fixture has to sit exactly on the line"
    apply_inbound(body, **_kwargs())  # must not raise

    body["messages"][0]["content"] += "A"
    with pytest.raises(RequestTooLarge):
        apply_inbound(body, **_kwargs())


# ---------------------------------------------------------------------------
# And what the client is actually told.
# ---------------------------------------------------------------------------


@pytest.fixture
def gateway(monkeypatch):
    from fastapi.testclient import TestClient

    from ai_bunker.gateway import create_app

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tokenize"):
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kw: httpx.Client(transport=transport).post(url, **kw),
    )

    settings = Settings(
        api_key="",
        charter_dir="charter",
        rules_dir="charter/rules",
        upstreams={
            "local": Upstream(
                name="local", base_url="http://up.test/v1", served_context=SERVED, model="m"
            )
        },
        default_upstream="local",
        audit_log="",
    )
    return TestClient(create_app(settings), raise_server_exceptions=False)


@pytest.mark.parametrize("route", ["/v1/chat/completions", "/v1/budget"])
def test_the_client_gets_a_413_that_names_the_ceiling(gateway, route):
    """Both entry points, because `/v1/budget` promises to answer *without*
    sending anything anywhere -- and it kept that promise by reading 40 MB for
    several minutes."""
    body = {"model": "m", "messages": [{"role": "tool", "content": "A" * (CEILING + 1)}]}
    response = gateway.post(route, json=body)
    assert response.status_code == 413

    payload = response.json()
    error = payload.get("error") or payload.get("detail") or {}
    assert error.get("code") == "request_too_large"
    assert error.get("ceiling") == CEILING
    assert error.get("characters") > CEILING


def test_a_refused_request_is_never_forwarded(gateway):
    """It is refused *instead of* being served, not alongside."""
    body = {"model": "m", "messages": [{"role": "tool", "content": "A" * (CEILING + 1)}]}
    assert gateway.post("/v1/chat/completions", json=body).status_code == 413
    ok = {"model": "m", "messages": [{"role": "user", "content": "hello"}]}
    assert gateway.post("/v1/chat/completions", json=ok).status_code == 200


def test_the_published_ceiling_matches_the_constant():
    """Both READMEs state the multiplier in words. If it changes, they lie.

    This is the cheapest possible instance of what `scripts/lint_claims.py`
    exists for, done at the point of introduction rather than three releases
    after somebody notices: a published bound nobody checks is a published
    bound that drifts. Spelled out in words in the prose because "32" in a
    sentence reads like a figure that was measured, and this one was chosen.
    """
    from ai_bunker.adopt import ROOT

    words = {
        4: ("four", "quatre"),
        8: ("eight", "huit"),
        16: ("sixteen", "seize"),
        32: ("thirty-two", "trente-deux"),
        64: ("sixty-four", "soixante-quatre"),
    }
    assert CEILING_CHARS_PER_TOKEN in words, (
        f"the ceiling is now {CEILING_CHARS_PER_TOKEN}, which this test cannot "
        "spell: add it here and state it in both READMEs"
    )
    english, french = words[CEILING_CHARS_PER_TOKEN]

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    lisezmoi = (ROOT / "LISEZMOI.md").read_text(encoding="utf-8")
    assert f"{english} characters per token" in readme, "README.md states a different ceiling"
    assert f"{french} caractères par token" in lisezmoi, "LISEZMOI.md states a different ceiling"
