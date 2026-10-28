"""
Every surface this gateway serves, and what has to be true of it.

Why this exists
---------------
`/a2a/v1/message:send` was added with neither the request ceiling nor the
worker thread the chat path had, and it is the surface that takes text another
agent wrote. Nothing noticed, because nothing anywhere asked the question
route by route: it took building the table by hand, one round, to see the two
blanks in it.

So the table lives here now. A route added without a line in it fails this
test, and that failure is the point -- a protection is a decision, and a
decision that nobody wrote down is one somebody skipped.

What is asserted mechanically rather than by reading the source: whether a
route demands a key, and whether a body past the ceiling comes back refused.
Those are the two that were actually missing.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import functools
import importlib.util
import inspect

import pytest

from ai_bunker.budget import CEILING_CHARS_PER_TOKEN
from ai_bunker.config import Settings, Upstream
from ai_bunker.gateway import create_app

SERVED = 32768
CEILING = SERVED * CEILING_CHARS_PER_TOKEN

#: (method, path) -> (needs a key, enforces the request ceiling)
#:
#: `False` for a ceiling means one of two things, and the comment says which:
#: the route carries no body to bound, or it carries one this gateway neither
#: screens nor forwards.
EXPECTED: dict[tuple[str, str], tuple[bool, bool]] = {
    # Open on purpose. `/health` is how a load balancer and an operator find
    # out whether this is up; the agent card exists to be read by a peer that
    # has not met this agent yet, and one behind a key cannot be discovered.
    ("GET", "/health"): (False, False),
    ("GET", "/.well-known/agent-card.json"): (False, False),
    # The dashboard's shell and its strings. Every number on it comes from a
    # route below that does demand a key, so an unauthenticated visitor gets
    # chrome and no data.
    ("GET", "/gui"): (False, False),
    ("GET", "/gui/i18n"): (False, False),
    # Read-only state. No body.
    ("GET", "/v1/models"): (True, False),
    ("GET", "/v1/charter"): (True, False),
    ("GET", "/v1/charter/{ref:path}"): (True, False),
    ("GET", "/v1/decisions"): (True, False),
    ("GET", "/v1/breaker"): (True, False),
    # A query parameter, not a body: there is nothing to put a ceiling on.
    ("POST", "/v1/breaker/reset"): (True, False),
    # The three that carry a body worth bounding.
    ("POST", "/v1/chat/completions"): (True, True),
    ("POST", "/v1/budget"): (True, True),
    ("POST", "/a2a/v1/message:send"): (True, True),
    ("POST", "/v1/embeddings"): (True, True),
    # The ceiling is checked BEFORE the route is resolved, which is why this
    # is `True` on a deployment with no image route at all: a body too large
    # to read is refused unread whether or not anything could have answered
    # it. The 501 comes after, and only for a body the gateway was willing to
    # parse.
    ("POST", "/v1/images/generations"): (True, True),
    # The MCP transport, on by default. The table never saw these: it built
    # the application with `enable_mcp=False`, so three routes existed in
    # every shipped deployment and in none of the assertions -- the same
    # blind spot, one layer up, as the surface this file was written for.
    #
    # They were open. The charter never leaked, because `tools/call` is
    # proxied to the HTTP route and came back 401, but an unauthenticated
    # caller got a session allocated and a `tools/list` naming the tools.
    # Bodies are JSON-RPC and bounded by nothing here, which is the library's
    # call rather than this gateway's; `False` says so rather than claiming a
    # ceiling that is not enforced.
    ("GET", "/mcp"): (True, False),
    ("POST", "/mcp"): (True, False),
    ("DELETE", "/mcp"): (True, False),
}

#: Whether `fastapi-mcp` is installed. The surface is optional, and a
#: checkout without the extra must not fail a test about routes it cannot
#: mount.
HAS_MCP = importlib.util.find_spec("fastapi_mcp") is not None


def _settings(**over) -> Settings:
    base = Settings(
        api_key="test-key",
        charter_dir="charter",
        rules_dir="charter/rules",
        upstreams={
            "local": Upstream(
                name="local", base_url="http://127.0.0.1:1/v1", served_context=SERVED, model="m"
            )
        },
        default_upstream="local",
        audit_log="",
        enable_mcp=HAS_MCP,
    )
    for key, value in over.items():
        setattr(base, key, value)
    return base


@functools.lru_cache(maxsize=4)
def _app(api_key: str = "test-key"):
    """Built once per key. `fastapi-mcp` costs about 24 seconds to import on a
    cold interpreter -- measured, and the gateway logs it for the same reason --
    so building the application per test turned a 40-second suite into a
    90-second one."""
    return create_app(_settings(api_key=api_key))


def _routes(app) -> dict[tuple[str, str], bool]:
    """(method, path) -> whether the route demands a key."""
    found: dict[tuple[str, str], bool] = {}
    for route in app.routes:
        path = getattr(route, "path", "")
        if path in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}:
            continue
        declared = {
            getattr(d.dependency, "__name__", "")
            for d in (getattr(route, "dependencies", []) or [])
        }
        signature = str(inspect.signature(route.endpoint))
        guarded = "_authenticate" in declared or "_authenticate" in signature
        for method in sorted(getattr(route, "methods", set()) or set()):
            if method in {"HEAD", "OPTIONS"}:
                continue
            found[(method, path)] = guarded
    return found


def test_every_route_is_accounted_for():
    """A route with no line in `EXPECTED` fails here.

    That is the whole mechanism: the next surface added to this gateway cannot
    reach a release without somebody deciding, in writing, whether it needs a
    key and a ceiling. The one that did reach a release without that decision
    is the reason this file exists.
    """
    served = set(_routes(_app()))
    declared = {route for route in EXPECTED if HAS_MCP or not route[1].startswith("/mcp")}
    assert served - declared == set(), (
        f"routes with no entry in EXPECTED: {sorted(served - declared)} -- decide "
        "whether each needs a key and a ceiling, then write it down"
    )
    assert declared - served == set(), (
        f"EXPECTED names routes that do not exist: {sorted(declared - served)}"
    )


def test_the_routes_demand_a_key_exactly_where_the_table_says():
    found = _routes(_app())
    wrong = {
        route: (guarded, EXPECTED[route][0])
        for route, guarded in found.items()
        if guarded != EXPECTED[route][0]
    }
    assert not wrong, f"authentication disagrees with the table: {wrong}"


def test_nothing_that_reaches_the_model_or_reveals_state_is_open():
    """The property behind the table, so a wrong line in it is still caught.

    An open route may serve liveness, a discovery document, or the dashboard's
    own shell. Anything that forwards to an engine, reads the audit record or
    reports breaker state has to demand a key.
    """
    open_routes = {path for (_method, path), guarded in _routes(_app()).items() if not guarded}
    assert open_routes == {
        "/health",
        "/.well-known/agent-card.json",
        "/gui",
        "/gui/i18n",
    }, f"an unexpected route is open: {sorted(open_routes)}"
    assert "/mcp" not in open_routes, (
        "the MCP transport mirrors `/v1/charter`, which demands a key; two "
        "answers to 'is the charter behind a key' is one too many"
    )


@pytest.mark.parametrize(
    "method,path",
    [route for route, (_auth, ceiling) in sorted(EXPECTED.items()) if ceiling],
)
def test_a_body_past_the_ceiling_is_refused_on_every_surface_that_bounds_one(method, path):
    """End to end, not by reading the source.

    Two of these enforce it indirectly, through `apply_inbound`, and a test
    that grepped handlers for `request_chars` reported them as gaps -- which
    is how a check about protections ends up protecting nothing.
    """
    from fastapi.testclient import TestClient

    client = TestClient(_app(""), raise_server_exceptions=False)
    big = "x" * (CEILING + 1)
    bodies = {
        "/v1/chat/completions": {"model": "m", "messages": [{"role": "tool", "content": big}]},
        "/v1/budget": {"model": "m", "messages": [{"role": "tool", "content": big}]},
        "/v1/embeddings": {"model": "m", "input": big},
        "/v1/images/generations": {"model": "m", "prompt": big},
        "/a2a/v1/message:send": {
            "message": {"role": "ROLE_USER", "messageId": "m-1", "parts": [{"text": big}]}
        },
    }
    response = client.request(method, path, json=bodies[path])
    assert response.status_code == 413, (
        f"{method} {path} accepted {CEILING + 1:,} characters; the table says it bounds them"
    )


def test_the_ceiling_is_not_vacuous():
    """A body just under the ceiling must not be refused for being large.

    Without this the test above passes on a gateway that refuses everything,
    which is the reassuring half of a wrong answer.
    """
    from fastapi.testclient import TestClient

    client = TestClient(_app(""), raise_server_exceptions=False)
    body = {
        "message": {
            "role": "ROLE_USER",
            "messageId": "m-1",
            "parts": [{"text": "x" * 1000}],
        }
    }
    assert client.post("/a2a/v1/message:send", json=body).status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        "example.com/",
        "example.com/x",
        "example.com?x",
        "example.com#x",
        "example.com/..",
        "example.com/v1/decisions",
        "a/b",
        "::1/x",
    ],
)
def test_a_malformed_host_header_does_not_shake_the_key_loose(host):
    """CVE-2026-48710, and the reason this gateway is not exposed to it.

    A `Host` header carrying `/`, `?` or `#` moves the boundary Starlette uses
    to split host from path, so the path reported to **middleware** stops
    matching the path the server received. A gateway that enforces
    authentication by matching paths in middleware then serves a request it
    meant to refuse -- reported against several, and the published exploit
    path for one of them ends in reading the provider keys out of the proxy's
    environment.

    This gateway attaches the dependency to the **route**, so nothing that
    rewrites a path string can detach it: by the time the dependency runs, the
    router has already chosen the endpoint. That was a taste decision long
    before the advisory existed, and this test is what stops it drifting --
    the tempting refactor, one authentication check in middleware instead of a
    dependency on fourteen routes, is exactly the shape that is vulnerable.
    """
    from fastapi.testclient import TestClient

    client = TestClient(_app(), raise_server_exceptions=False)
    assert client.get("/v1/decisions").status_code == 401, "the baseline must refuse"
    assert client.get("/v1/decisions", headers={"Host": host}).status_code == 401
