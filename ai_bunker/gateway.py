"""
The gateway: an OpenAI-compatible surface with the charter, the rules and the
budget wired in.

Any client that speaks OpenAI speaks ai-bunker, and gets the charter, the rule
engine and a real token budget without being configured for them. That is the
whole argument for putting this at the endpoint rather than in each developer's
harness: a plugin can be disabled by editing a file, and a different harness
simply never had it.

Surface
-------
``GET /health``
    Liveness, and whether the deployment is actually sovereign.
``GET /v1/models``
    The models this gateway will route, with the context it declares for each.
``POST /v1/chat/completions``
    Atomic and streaming. Runs the full pipeline.
``POST /v1/embeddings``
    Proxied with the same authentication and routing.
``GET /v1/budget``
    What a session costs before it works. The measurement, as an endpoint.
``GET /v1/charter`` and ``GET /v1/charter/{ref}``
    The index, and one page on demand.
``GET /v1/decisions``
    The tail of the audit log, for the dashboard. Rules and outcomes, never
    the matched text.
``GET /gui``
    A single-page operations dashboard. No build step and no external
    request: a page whose purpose is to show that nothing leaves the network
    cannot start by fetching a stylesheet from a CDN.
``/mcp``
    The same charter endpoints, through the Model Context Protocol, so an
    agent host can reach them as tools rather than as HTTP. Optional: enabled
    when ``fastapi-mcp`` is installed.

What the gateway declares, and why it is lower than what it serves
------------------------------------------------------------------
``/v1/models`` reports a context *below* the engine's real one. A client that
estimates its own token count under-counts -- one measured session believed it
was under 32,768 and sent 40,433 -- and the margin between declared and served
is the only protection while a turn grows. Declaring the truth would be
honest and would break.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
import os_helper as osh
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from ai_bunker import __version__
from ai_bunker.a2a import agent_card, handle_message_send
from ai_bunker.breaker import SESSION_HEADER, Breaker, session_of
from ai_bunker.budget import Counter
from ai_bunker.charter import build_index, load_charter, read_page
from ai_bunker.config import Settings, load_settings
from ai_bunker.mandates import Trust, load_trust
from ai_bunker.pipeline import (
    apply_inbound,
    apply_outbound,
    refusal_as_tool_result,
)
from ai_bunker.rules import decisions_for, load_rules
from ai_bunker.telemetry import Exporter, span_from_decisions

#: How long to wait on an upstream. Generous: a 256k prompt on a busy GPU is
#: slow to first token, and a gateway that times out before the model answers
#: is worse than no gateway.
UPSTREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=60.0, pool=10.0)


class State:
    """Everything loaded once at startup.

    The charter and the rules are read at startup rather than per request, and
    the counter's backend is resolved once. Re-reading a charter on every
    request would change the system prompt's bytes under a prefix cache that
    only helps while they are identical.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.charter = load_charter(settings.charter_dir)
        self.rules = load_rules(settings.rules_dir)
        self.counters: dict[tuple[str, str], Counter] = {}
        self.breaker = Breaker(threshold=settings.breaker_refusals, window=settings.breaker_window)
        self.started = time.time()

        self.output_rules = sum(1 for r in self.rules if r.scope == "output")
        self.command_rules = sum(1 for r in self.rules if r.scope == "command")
        self.tool_rules = sum(1 for r in self.rules if r.scope == "tool")
        osh.info(
            f"[gateway] charter {self.charter.fingerprint[:16]} "
            f"({len(self.charter.pages)} pages), {self.output_rules} output rules, "
            f"{self.command_rules} command rules, {self.tool_rules} tool rules, "
            f"{'sovereign' if settings.sovereign else 'WITH A REMOTE ROUTE'}"
        )

    def counter_for(self, upstream_name: str, model: str) -> Counter:
        """A token counter per (upstream, model), resolved once and reused.

        Keyed on both, and constructed with the model, because ``/tokenize``
        needs a model name to answer: a counter built without one can only
        ever fall back to the ratio estimate. That was a real bug here -- the
        backend is decided at construction, so passing the model afterwards
        was too late and every count was silently an estimate.

        Cached because resolving the backend is a round trip to the engine,
        and the answer does not change between requests.
        """
        key = (upstream_name, model)
        if key not in self.counters:
            up = self.settings.upstreams[upstream_name]
            counter = Counter(base_url=up.base_url, model=model, allow_ratio=True)
            if counter.backend == "ratio":
                osh.warning(
                    f"[gateway] {up.name} does not tokenize {model!r}; the budget for it "
                    "is an ESTIMATE. Exactly the kind of figure that let a client send "
                    "40,433 tokens to a 32,768-token server."
                )
            self.counters[key] = counter
        return self.counters[key]

    def trust(self) -> Trust | None:
        """The mandate key set, loaded once. None when none is configured."""
        if not self.settings.mandate_jwks:
            return None
        if getattr(self, "_trust", None) is None:
            self._trust = load_trust(
                self.settings.mandate_jwks,
                issuers=self.settings.mandate_issuers,
                revoked_file=self.settings.mandate_revocations,
            )
        return self._trust

    def exporter(self) -> Exporter | None:
        """The OTLP exporter, built once, or None when none is configured."""
        if not self.settings.telemetry_endpoint:
            return None
        if getattr(self, "_exporter", None) is None:
            self._exporter = Exporter(
                self.settings.telemetry_endpoint,
                service_name=self.settings.telemetry_service,
            )
        return self._exporter

    def audit(self, records: list[dict[str, Any]]) -> None:
        """Append decisions to the audit log, one JSON object per line.

        A failure to write the log is reported and does not fail the request.
        Losing an audit line is bad; refusing to serve because a disk is full
        is worse, and the warning is what gets someone to fix it.
        """
        # Telemetry first, and independent of the audit log: a deployment
        # that ships spans and keeps no file on disk is a reasonable one.
        if (exporter := self.exporter()) is not None:
            exporter.export(span_from_decisions(records))

        if not records or not self.settings.audit_log:
            return
        path = Path(self.settings.audit_log)
        try:
            osh.make_directory(str(path.parent))
            with path.open("a", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps({**record, "at": osh.now_string("log")}) + "\n")
        except OSError as exc:
            osh.warning(f"[gateway] could not write the audit log ({exc}).")


def _authenticate(request: Request) -> None:
    """Check the bearer token, when one is configured.

    An unconfigured key means an open gateway. That is a legitimate choice on
    a trusted network, so it is allowed -- and ``/health`` reports it, because
    a deployment that is open by accident looks exactly like one that is open
    on purpose.
    """
    settings: Settings = request.app.state.bunker.settings
    if not settings.api_key:
        return
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if token != settings.api_key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": {
                    "message": "Invalid API key for this gateway.",
                    "type": "invalid_request_error",
                    "code": "invalid_api_key",
                }
            },
        )


def _error(status: int, message: str, code: str, **extra: Any) -> JSONResponse:
    """An OpenAI-shaped error.

    Clients parse this shape. A gateway that invents its own error envelope
    produces a client that reports "unknown error" and a user who cannot act.
    """
    body: dict[str, Any] = {
        "error": {"message": message, "type": "invalid_request_error", "code": code}
    }
    body["error"].update(extra)
    return JSONResponse(status_code=status, content=body)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the gateway application."""
    app = FastAPI(
        title="ai-bunker",
        version=__version__,
        description=(
            "Sovereign serving layer for coding agents: one GPU, one charter, "
            "a context budget the server actually counts."
        ),
    )
    app.state.bunker = State(settings or load_settings())

    # -- health ----------------------------------------------------------

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Liveness, and the facts a deployment should not have to infer."""
        state: State = app.state.bunker
        s = state.settings
        return {
            "status": "ok",
            "version": __version__,
            "uptime_s": round(time.time() - state.started, 1),
            "sovereign": s.sovereign,
            "authenticated": bool(s.api_key),
            "charter": {
                "fingerprint": state.charter.fingerprint[:16],
                "packs": len(state.charter.packs),
                "pages": len(state.charter.pages),
            },
            "rules": {
                "output": state.output_rules,
                "command": state.command_rules,
                "tool": state.tool_rules,
            },
            "breaker": {
                "refusals": s.breaker_refusals,
                "window_s": s.breaker_window,
                "open": len(state.breaker.status()),
            },
            "enforcement": {
                "budget": s.enforce_budget,
                "commands": s.enforce_commands,
                "provenance": s.mark_provenance,
            },
            "audit_log": s.audit_log or None,
        }

    # -- models ----------------------------------------------------------

    @app.get("/v1/models", dependencies=[Depends(_authenticate)])
    async def models() -> dict[str, Any]:
        """List routable models, each with the context the gateway declares.

        The declared figure is deliberately below what the engine serves. See
        the module docstring.
        """
        state: State = app.state.bunker
        s = state.settings
        out = []
        seen: set[str] = set()

        def add(ident: str, upstream_name: str, kind: str) -> None:
            upstream = s.upstreams.get(upstream_name)
            if upstream is None or ident in seen:
                return
            seen.add(ident)
            out.append(
                {
                    "id": ident,
                    "object": "model",
                    "owned_by": "ai-bunker",
                    "kind": kind,
                    "context_length": int(upstream.served_context * s.declared_fraction),
                    "served_context": upstream.served_context,
                    "remote": upstream.remote,
                }
            )

        for name, upstream_name in s.routes.items():
            add(name, upstream_name, "model")
        # Needs are listed as models so a client with no custom-header support
        # can still declare one by picking it from the model dropdown. A need
        # is the better thing to ask for: it survives a model being swapped.
        for need, upstream_name in s.needs.items():
            add(need, upstream_name, "need")
        return {"object": "list", "data": out}

    # -- budget ----------------------------------------------------------

    @app.post("/v1/budget", dependencies=[Depends(_authenticate)])
    async def budget(request: Request) -> dict[str, Any]:
        """Measure a request's floor without sending it anywhere.

        A client can ask what a session will cost before paying for it, which
        is the difference between a budget that is enforced and a budget that
        can be planned against.
        """
        state: State = app.state.bunker
        body = await request.json()
        model = str(body.get("model") or "")
        need = request.headers.get("x-ai-bunker-need", "")
        upstream, resolved, _why = state.settings.route(model, need)
        applied = _prepare(state, {**body, "model": resolved}, upstream)
        assert applied.budget is not None
        return applied.budget.to_dict()

    # -- charter ---------------------------------------------------------

    # -- Agent2Agent ------------------------------------------------------
    #
    # Deliberately unauthenticated, like /health: a card exists to be read by
    # a peer that has not met this agent yet, and one behind a key cannot be
    # discovered. It carries no secrets -- it names skills and says whether a
    # key is needed to use them.

    @app.get("/.well-known/agent-card.json", include_in_schema=False)
    async def a2a_card(request: Request) -> JSONResponse:
        """A2A discovery."""
        state: State = app.state.bunker
        base = str(request.base_url).rstrip("/")
        card = agent_card(
            base_url=base,
            charter=state.charter,
            authenticated=bool(state.settings.api_key),
            sovereign=not any(u.remote for u in state.settings.upstreams.values()),
        )
        return JSONResponse(card, media_type="application/a2a+json")

    @app.post("/a2a/v1/message:send", dependencies=[Depends(_authenticate)])
    async def a2a_message_send(request: Request) -> JSONResponse:
        """Screen one A2A message, or serve the charter, and return a Task.

        An A2A message is text another agent wrote, arriving in this one's
        context. That is the event stage 1 of the pipeline exists for, so it
        runs the same rules -- not a parallel set that would drift.
        """
        state: State = app.state.bunker
        body = await request.json()
        result = handle_message_send(
            body,
            state.rules,
            state.charter,
            mark_provenance=state.settings.mark_provenance,
        )
        # Carried out of band by handle_message_send so the wire format stays
        # exactly what the specification describes.
        violations = result.pop("_violations", [])
        if violations:
            state.audit(
                [
                    d.as_dict()
                    for d in decisions_for(
                        violations,
                        charter=state.charter.fingerprint if state.charter else "",
                    )
                ]
            )
            osh.info(f"[a2a] screened a peer message; {len(violations)} rule(s) fired.")
        return JSONResponse(result, media_type="application/a2a+json")

    @app.get(
        "/v1/charter",
        operation_id="charter",
        dependencies=[Depends(_authenticate)],
    )
    async def charter() -> dict[str, Any]:
        """The charter's index and what it costs, as served."""
        state: State = app.state.bunker
        return {
            "fingerprint": state.charter.fingerprint,
            "index": build_index(state.charter),
            "operating_rules": state.charter.operating_rules,
            "packs": {k: [p.name for p in v] for k, v in state.charter.packs.items()},
        }

    @app.get(
        "/v1/charter/{ref:path}",
        operation_id="charter_page",
        dependencies=[Depends(_authenticate)],
    )
    async def charter_page(ref: str) -> dict[str, Any]:
        """One page, on demand. The whole point of indexing rather than pasting."""
        state: State = app.state.bunker
        try:
            return {"ref": ref, "content": read_page(state.charter, ref)}
        except AssertionError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    # -- decisions -------------------------------------------------------

    @app.get("/v1/decisions", dependencies=[Depends(_authenticate)])
    async def decisions(limit: int = 50) -> dict[str, Any]:
        """The tail of the audit log.

        Read from disk rather than held in memory: the log is the record, and a
        dashboard showing a different set of decisions than the file does would
        be worse than no dashboard. Bounded by ``limit`` because an operations
        page has no business loading a month of history to show the last hour.
        """
        state: State = app.state.bunker
        path = state.settings.audit_log
        if not path:
            return {
                "decisions": [],
                "total": 0,
                "path": None,
                "note": "No audit_log configured: nothing is being recorded.",
            }
        p = Path(path)
        if not p.exists():
            return {"decisions": [], "total": 0, "path": str(p)}
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Cannot read {p}: {exc}") from exc
        kept: list[dict[str, Any]] = []
        for line in lines[-max(1, min(limit, 500)) :]:
            try:
                kept.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a truncated last line is normal while a write lands
        return {"decisions": kept, "total": len(lines), "path": str(p)}

    @app.get("/v1/breaker", dependencies=[Depends(_authenticate)])
    async def breaker_status() -> dict[str, Any]:
        """Which sessions are currently stopped, and for how long.

        Sessions are named by a short hash, never by the prose they were
        derived from: the identifier ends up in logs and on a dashboard, and
        the user's own first sentence has no business in either.
        """
        state: State = app.state.bunker
        s = state.settings
        return {
            "enabled": state.breaker.enabled,
            "refusals": s.breaker_refusals,
            "window_s": s.breaker_window,
            "open": state.breaker.status(),
        }

    @app.post("/v1/breaker/reset", dependencies=[Depends(_authenticate)])
    async def breaker_reset(session: str = "") -> dict[str, Any]:
        """Close one breaker, or all of them.

        This endpoint exists because the refusal message promises it. A
        breaker whose only cure is waiting, or restarting the gateway, would
        make that message a lie -- and the state is in this process, so no
        command-line tool can reach it any other way.
        """
        state: State = app.state.bunker
        closed = state.breaker.reset(session or None)
        osh.info(f"[gateway] breaker reset by operator: {closed} session(s) closed")
        return {"closed": closed, "open": state.breaker.status()}

    # -- dashboard -------------------------------------------------------

    @app.get("/gui", include_in_schema=False)
    async def gui() -> HTMLResponse:
        """The operations dashboard.

        Deliberately unauthenticated at the HTML level while the data it loads
        is not: the page is a static file with no secrets in it, and gating it
        would mean putting a key in a URL just to see a login prompt. Its
        fetches carry whatever key the operator passed as ``?key=``, and each
        of those endpoints checks it.
        """
        page = Path(__file__).resolve().parent / "static" / "gui.html"
        if not osh.file_exists(str(page)):
            raise HTTPException(status_code=404, detail="The dashboard is not installed.")
        return HTMLResponse(page.read_text(encoding="utf-8"))

    # -- chat ------------------------------------------------------------

    @app.post("/v1/chat/completions", dependencies=[Depends(_authenticate)])
    async def chat(request: Request):
        state: State = app.state.bunker
        s = state.settings
        body = await request.json()
        model = str(body.get("model") or "")
        need = request.headers.get("x-ai-bunker-need", "")

        try:
            upstream, resolved, why = s.route(model, need)
        except AssertionError as exc:
            return _error(400, str(exc), "model_not_found")

        if resolved != model:
            osh.debug(f"[gateway] {model!r} -> {resolved!r} on {upstream.name} ({why})")
            body = {**body, "model": resolved}

        applied = _prepare(state, body, upstream)
        state.audit(applied.audit())

        if s.enforce_budget and not applied.ok:
            assert applied.budget is not None
            biggest = applied.budget.biggest
            # Refused here, with the component named, rather than downstream as
            # a context-length error nobody can act on.
            return _error(
                413,
                "This session has no room to work. " + " ".join(applied.budget.warnings),
                "context_budget_exhausted",
                budget=applied.budget.to_dict(),
                attack_first=biggest.name if biggest else None,
            )

        if upstream.remote:
            # Named with its reason: a request that silently went off-network
            # is the failure that shows up on an invoice rather than in a log.
            osh.warning(
                f"[gateway] {model!r} -> {upstream.name} by {why}; this request "
                "leaves the local network."
            )

        if body.get("stream"):
            return StreamingResponse(
                _stream(state, applied.request, upstream),
                media_type="text/event-stream",
            )

        try:
            response = await _forward(applied.request, upstream, "/chat/completions")
        except httpx.HTTPError as exc:
            return _error(502, f"Upstream {upstream.name} is unreachable: {exc}", "upstream_error")

        if s.enforce_commands:
            outbound = apply_outbound(
                response,
                rules=state.rules,
                charter_fingerprint=state.charter.fingerprint[:16],
                project_root=s.project_root or None,
                check_payments=s.check_payments,
                trust=state.trust(),
                breaker=state.breaker,
                session=session_of(
                    body,
                    header=request.headers.get(SESSION_HEADER, ""),
                    credential=s.api_key,
                ),
            )
            state.audit(outbound.audit())
            if outbound.refusal is not None:
                response = _substitute_refusal(response, outbound.refusal)

        return response

    # -- embeddings ------------------------------------------------------

    @app.post("/v1/embeddings", dependencies=[Depends(_authenticate)])
    async def embeddings(request: Request):
        """Proxied unchanged.

        No charter, no rules, no budget: an embedding request has no system
        prompt to carry a charter, no tool results to screen, and no
        conversation to run out of. Pretending otherwise would be theatre.
        """
        state: State = app.state.bunker
        body = await request.json()
        try:
            upstream = state.settings.upstream_for(str(body.get("model") or ""))
            return await _forward(body, upstream, "/embeddings")
        except AssertionError as exc:
            return _error(400, str(exc), "model_not_found")
        except httpx.HTTPError as exc:
            return _error(502, f"Upstream unreachable: {exc}", "upstream_error")

    _mount_mcp(app)
    return app


def _mount_mcp(app: FastAPI) -> None:
    """Expose the charter as MCP tools, when ``fastapi-mcp`` is available.

    Only the charter, and deliberately so. The reasoning is worth stating
    because the tempting thing is to expose everything:

    - ``/v1/charter`` and ``/v1/charter/{ref}`` are **reads an agent should
      make on its own initiative**. An agent that can fetch the page for the
      domain it is working in, as a tool, is the whole point of indexing
      rather than pasting.
    - ``/v1/chat/completions`` is not exposed. An MCP tool that calls a model
      inside a model's own turn is a recursion with no obvious floor, and the
      host is already talking to this gateway.
    - ``/v1/budget`` is not exposed either. It is an operator's instrument; an
      agent given it would spend tokens measuring how many tokens it has.

    Absent dependency is not an error: the HTTP surface is complete on its
    own, and MCP is an extra way in for hosts that prefer it.

    The import is timed and reported because it is slow: ~24 seconds on a cold
    interpreter, measured here. An operator watching a gateway take half a
    minute to answer deserves to know which optional surface bought that,
    rather than concluding the server is broken.
    """
    if not app.state.bunker.settings.enable_mcp:
        osh.debug("[gateway] MCP disabled in config; no /mcp surface.")
        return

    started = time.time()
    try:
        from fastapi_mcp import FastApiMCP  # optional: the [mcp] extra
    except ImportError:
        osh.debug("[gateway] fastapi-mcp not installed; no /mcp surface.")
        return

    try:
        mcp = FastApiMCP(
            app,
            name="ai-bunker charter",
            description=(
                "This project's standards. Read the index, then the one page for "
                "the domain you are working in."
            ),
            include_operations=["charter", "charter_page"],
        )
        mcp.mount_http()
        elapsed = time.time() - started
        message = f"[gateway] MCP surface mounted at /mcp (charter only) in {elapsed:.1f}s."
        if elapsed > 5:
            osh.info(
                message + " Most of that is importing fastapi-mcp. Set "
                "enforcement.mcp: false if no client here speaks MCP."
            )
        else:
            osh.info(message)
    except Exception as exc:  # a broken optional surface must not stop the gateway
        osh.warning(f"[gateway] could not mount the MCP surface ({exc}).")


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _prepare(state: State, body: dict[str, Any], upstream: Any):
    """Run the inbound pipeline for one request."""
    s = state.settings
    counter = state.counter_for(upstream.name, str(body.get("model") or ""))
    return apply_inbound(
        body,
        charter=state.charter,
        rules=state.rules,
        counter=counter,
        served_context=upstream.served_context,
        compaction_reserve=s.compaction_reserve,
        declared_context=int(upstream.served_context * s.declared_fraction),
        min_working=s.min_working_tokens,
        mark_provenance=s.mark_provenance,
    )


def _headers(upstream: Any) -> dict[str, str]:
    headers = {"content-type": "application/json"}
    if upstream.api_key:
        headers["authorization"] = f"Bearer {upstream.api_key}"
    return headers


async def _forward(body: dict[str, Any], upstream: Any, path: str) -> dict[str, Any]:
    """Send a prepared request to an upstream and return its JSON."""
    url = upstream.base_url.rstrip("/") + path
    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
        response = await client.post(url, json=body, headers=_headers(upstream))
        response.raise_for_status()
        return response.json()


async def _stream(state: State, body: dict[str, Any], upstream: Any):
    """Relay a streaming completion.

    Command screening is **not** applied to a stream, and that is a deliberate
    limitation rather than an oversight. A tool call arrives in fragments
    across many chunks; refusing it would mean buffering the whole response,
    which is the one thing streaming exists to avoid. The honest arrangement:
    a client that wants command enforcement asks for a non-streamed completion
    for tool-calling turns, and `/health` reports which guarantees are live.
    """
    url = upstream.base_url.rstrip("/") + "/chat/completions"
    try:
        async with (
            httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client,
            client.stream("POST", url, json=body, headers=_headers(upstream)) as response,
        ):
            if response.status_code >= 400:
                detail = (await response.aread()).decode("utf-8", "replace")[:500]
                yield _sse({"error": {"message": detail, "code": "upstream_error"}})
                yield "data: [DONE]\n\n"
                return
            async for line in response.aiter_lines():
                if line:
                    yield line + "\n\n"
    except httpx.HTTPError as exc:
        yield _sse(
            {
                "error": {
                    "message": f"Upstream {upstream.name} failed mid-stream: {exc}",
                    "code": "upstream_error",
                }
            }
        )
        yield "data: [DONE]\n\n"


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _substitute_refusal(response: dict[str, Any], rule: Any) -> dict[str, Any]:
    """Replace refused tool calls with the refusal, as a tool result.

    The assistant message keeps its ``tool_calls`` so the conversation stays
    well-formed -- a client that sent a tool call and gets no matching result
    back will usually resend it -- and the refusal arrives as the result of
    that call, which is a shape every agent already knows how to read.
    """
    out = json.loads(json.dumps(response))  # cheap deep copy of plain JSON
    for choice in out.get("choices") or []:
        message = choice.get("message") or {}
        calls = message.get("tool_calls") or []
        if not calls:
            continue
        choice["ai_bunker_refusals"] = [refusal_as_tool_result(call, rule) for call in calls]
        choice["finish_reason"] = "tool_calls"
    out["ai_bunker"] = {"refused_by": rule.id, "reason": rule.description}
    return out


def serve(
    settings: Settings | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Run the gateway.

    Bound to localhost by default. A sovereignty tool that listens on every
    interface the moment it starts has made the decision its user was supposed
    to make.
    """
    import uvicorn

    uvicorn.run(create_app(settings), host=host, port=port, log_level="info")
