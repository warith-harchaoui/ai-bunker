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
``POST /v1/budget``
    What a session costs before it works. The measurement, as an endpoint.
    A POST because it measures a request body rather than fetching a resource.
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

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import os_helper as osh
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from ai_bunker import __version__, i18n, streaming
from ai_bunker.a2a import agent_card, handle_message_send, too_large_task
from ai_bunker.breaker import SESSION_HEADER, Breaker, session_of
from ai_bunker.budget import CEILING_CHARS_PER_TOKEN, Counter, request_chars
from ai_bunker.charter import build_index, load_charter, read_page
from ai_bunker.config import Settings, load_settings
from ai_bunker.i18n import negotiate
from ai_bunker.mandates import Trust, load_trust
from ai_bunker.pipeline import (
    RequestTooLarge,
    apply_inbound,
    apply_outbound,
    refusal_as_tool_result,
)
from ai_bunker.rules import decisions_for, load_rules
from ai_bunker.telemetry import Exporter, span_from_decisions
from ai_bunker.tools import Pins, approved_fingerprints

#: How long to wait on an upstream. Generous: a 256k prompt on a busy GPU is
#: slow to first token, and a gateway that times out before the model answers
#: is worse than no gateway.
UPSTREAM_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=60.0, pool=10.0)

#: The need ``POST /v1/images/generations`` routes on when a client declares
#: none. A need and not a model name, for the reason every route here gives:
#: a need survives the model being swapped, and which text-to-image model a
#: deployment holds is `ai-bunker sizing --image auto`'s answer, not a client's
#: business.
IMAGE_NEED = "image"


class State:
    """Everything loaded once at startup.

    The charter and the rules are read at startup rather than per request, and
    the counter's backend is resolved once. Re-reading a charter on every
    request would change the system prompt's bytes under a prefix cache that
    only helps while they are identical.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        # The charter's language is the deployment's, fixed here at startup.
        # Not the per-request locale `negotiate()` returns further down: that
        # one may come from `Accept-Language`, and a client must not be able to
        # choose the language an agent is instructed in.
        self.charter = load_charter(settings.charter_dir, locale=settings.language)
        self.rules = load_rules(settings.rules_dir)
        self.counters: dict[tuple[str, str], Counter] = {}
        #: Serialises the inbound pipeline, which is now run off the event
        #: loop. The two halves of that sentence belong together: moving
        #: `_prepare` to a worker thread is what stops a stalled tokenizer
        #: freezing the whole gateway, and it would also be the first time two
        #: requests ran it *at once* -- over `counters`, `pins`,
        #: `approved_tools` and the breaker, none of which has ever needed a
        #: lock because nothing was ever concurrent. Trading an availability
        #: defect for a data race is not a fix.
        #:
        #: So the pipeline stays serialised, exactly as serialised as it was
        #: when it ran on the loop, and what changes is that the loop is free
        #: while it runs: `/health`, `/v1/models`, the dashboard and every
        #: stream already in flight keep answering.
        #: A **threading** lock, not an `asyncio` one, and the difference is a
        #: defect this project shipped for a day. `async with lock: await
        #: run_in_threadpool(...)` releases the lock when the await is
        #: cancelled -- which uvicorn does the moment a client disconnects --
        #: while the worker thread runs on, because a thread cannot be
        #: cancelled. The next request then takes the lock and starts its own
        #: `_prepare` beside the first. Measured: two concurrent, over exactly
        #: the state the lock exists to protect.
        #:
        #: An asynchronous lock cannot guard work that outlives the await. So
        #: the lock is taken *inside* the worker, by whoever is actually doing
        #: the work, and a cancelled caller leaves it held until that work
        #: finishes.
        self.pipeline = threading.Lock()
        self.breaker = Breaker(threshold=settings.breaker_refusals, window=settings.breaker_window)
        self.pins = Pins()
        self.approved_tools = (
            approved_fingerprints(settings.tools_lock) if settings.tools_lock else {}
        )
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
            counter = Counter(
                base_url=up.base_url,
                model=model,
                tokenizer=getattr(up, "tokenizer", "") or "",
                allow_ratio=True,
            )
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
            # Published because the two tiers are a real difference in what
            # this deployment does, not a preference: `neutralise: false` means
            # untrusted output still fetches itself when a client renders it,
            # and the gateway only says so. A reader must be able to tell which
            # of those they are getting without reading the configuration file.
            "render": {
                "beacons": "neutralised" if s.render_neutralise else "noted",
                "allow_hosts": list(s.render_allow_hosts),
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
        try:
            applied = await run_in_threadpool(
                _prepare_serialised, state, {**body, "model": resolved}, upstream
            )
        except RequestTooLarge as exc:
            # This endpoint's whole promise is to answer without sending
            # anything anywhere, and it kept that promise by reading 40 MB for
            # several minutes. Refused here too, with the ceiling named so a
            # client can act on it rather than guess.
            raise HTTPException(
                status_code=413,
                detail={
                    "message": str(exc),
                    "type": "invalid_request_error",
                    "code": "request_too_large",
                    "characters": exc.chars,
                    "ceiling": exc.ceiling,
                },
            ) from exc
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

        # The same ceiling `/v1/chat/completions` has had since round 10, and
        # the same worker thread it got in round 15. Neither reached here, and
        # this is the surface that takes text another agent wrote: four
        # megabytes from a peer froze the gateway for 7.08 seconds, measured.
        ceiling = state.settings.default_served_context * CEILING_CHARS_PER_TOKEN
        size = request_chars(body)
        if size > ceiling:
            return JSONResponse(
                too_large_task(size, ceiling, str(body.get("contextId") or "")),
                status_code=413,
                media_type="application/a2a+json",
            )

        # Under the pipeline lock, like the other screening path: the rules and
        # the charter are read-only here, so this is for consistency rather
        # than for safety -- one screen at a time, wherever it is started from.
        result = await run_in_threadpool(_screen_peer_serialised, state, body)
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
        wanted = max(1, min(limit, 500))
        try:
            # In a worker thread, and this one really does free the loop:
            # file reads release the global interpreter lock, unlike the
            # pattern matching in the screening path.
            lines, total = await run_in_threadpool(read_tail, p, wanted)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Cannot read {p}: {exc}") from exc
        kept: list[dict[str, Any]] = []
        for line in lines:
            try:
                kept.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a truncated last line is normal while a write lands
        return {"decisions": kept, "total": total, "path": str(p)}

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

    @app.get("/gui/i18n", include_in_schema=False)
    async def dashboard_messages(locale: str = "") -> dict[str, Any]:
        """The dashboard's own words, from the same catalogue the rules use.

        Unauthenticated, like the page that fetches it and for the same
        reason: there are no secrets in a list of column headings, and gating
        it would leave an operator looking at a page labelled `gui.stat.floor`
        until they pasted a key.

        Only the `gui.` keys are served. The rest of the catalogue is what the
        gateway says to agents, and a dashboard has no business shipping it to
        a browser.
        """
        state: State = app.state.bunker
        chosen = i18n.negotiate(configured=locale) if locale else state.settings.language
        chosen = i18n.translator(chosen).locale
        catalogue = i18n.translator(chosen)
        base = i18n._load(chosen)
        fallback = i18n._load(i18n.DEFAULT_LOCALE)
        messages = {
            key.removeprefix("gui."): base.get(key, fallback[key])
            for key in fallback
            if key.startswith("gui.")
        }
        return {"locale": catalogue.locale, "messages": messages}

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

        locale = negotiate(request.headers.get("accept-language", ""), s.language)
        # One session identity for the whole turn: the tool pins taken on the
        # way in and the breaker counted on the way out have to agree about
        # which conversation this is.
        session = session_of(
            body, header=request.headers.get(SESSION_HEADER, ""), credential=s.api_key
        )
        try:
            applied = await run_in_threadpool(
                _prepare_serialised, state, body, upstream, locale=locale, session=session
            )
        except RequestTooLarge as exc:
            # Refused unread. Nothing is audited, because nothing was
            # screened and an audit line claiming otherwise would be the lie
            # this gateway exists to avoid.
            return _error(
                413,
                str(exc),
                "request_too_large",
                characters=exc.chars,
                ceiling=exc.ceiling,
            )
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
                _stream(state, applied.request, upstream, locale=locale, session=session),
                media_type="text/event-stream",
            )

        try:
            response = await _forward(applied.request, upstream, "/chat/completions", request)
        except ClientGone:
            return _error(
                499,
                "The client disconnected before the engine answered; the upstream "
                "call was cancelled.",
                "client_disconnected",
            )
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
                locale=locale,
                breaker=state.breaker,
                session=session,
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
        # Nothing here is screened, so the thread pool would buy nothing. The
        # ceiling still applies: a body no engine could accept should be
        # refused rather than parsed, held in memory and forwarded.
        ceiling = state.settings.default_served_context * CEILING_CHARS_PER_TOKEN
        size = request_chars(body)
        if size > ceiling:
            return _error(
                413,
                f"This request carries {size:,} characters and this gateway reads "
                f"at most {ceiling:,}.",
                "request_too_large",
                characters=size,
                ceiling=ceiling,
            )
        try:
            upstream = state.settings.upstream_for(str(body.get("model") or ""))
            return await _forward(body, upstream, "/embeddings", request)
        except ClientGone:
            return _error(
                499,
                "The client disconnected before the engine answered; the upstream "
                "call was cancelled.",
                "client_disconnected",
            )
        except AssertionError as exc:
            return _error(400, str(exc), "model_not_found")
        except httpx.HTTPError as exc:
            return _error(502, f"Upstream unreachable: {exc}", "upstream_error")

    # -- images ----------------------------------------------------------

    @app.post("/v1/images/generations", dependencies=[Depends(_authenticate)])
    async def images(request: Request):
        """Proxied to an upstream that can actually answer, or refused saying so.

        Same treatment as ``/v1/embeddings`` and for the same reason: no
        charter, no rules, no budget. A prompt for a picture has no system
        prompt to carry a charter, no tool results to screen, and no
        conversation to run out of; a budget counted in tokens against a served
        context says nothing about a model whose cost is denoising steps.

        **One thing is different, and it is why this route exists separately
        rather than falling through the default.** A language engine cannot
        answer this request. Every other route here degrades gracefully when a
        model is unknown -- the default upstream takes it, which is exactly
        what lets a client hardcoded to somebody else's model name work
        unchanged. Do that here and the operator gets a 502 from a vLLM that
        has no such endpoint, which is a true statement about a socket and a
        useless one about the deployment. So an image route has to be
        configured on purpose, and when it is not, this says which line to
        write.

        The upstream that answers it is `best-engine-ai-helper serve`, whose
        OpenAI-compatible surface carries ``/v1/images/generations`` over
        ``diffusers`` -- the same package ``ai-bunker sizing --image auto``
        asks which model to put there.
        """
        state: State = app.state.bunker
        s = state.settings
        body = await request.json()
        model = str(body.get("model") or "")
        need = request.headers.get("x-ai-bunker-need", "") or IMAGE_NEED

        # The ceiling still applies. A prompt is text and a body no engine
        # could accept should be refused rather than parsed, held in memory
        # and forwarded.
        ceiling = s.default_served_context * CEILING_CHARS_PER_TOKEN
        size = request_chars(body)
        if size > ceiling:
            return _error(
                413,
                f"This request carries {size:,} characters and this gateway reads "
                f"at most {ceiling:,}.",
                "request_too_large",
                characters=size,
                ceiling=ceiling,
            )

        if need not in s.needs and model not in s.routes:
            return _error(
                501,
                "This gateway has no text-to-image route. A language engine cannot answer "
                f"{request.url.path}, so there is no sensible default to fall through to. "
                f"Add an upstream that serves images and point the {IMAGE_NEED!r} need at it "
                "(`best-engine-ai-helper serve` carries this endpoint); "
                "`ai-bunker sizing --image auto` says which model it should hold.",
                "image_route_not_configured",
                need=IMAGE_NEED,
                configured_needs=sorted(s.needs),
            )

        try:
            upstream, resolved, why = s.route(model, need)
        except AssertionError as exc:
            return _error(400, str(exc), "model_not_found")
        if resolved != model:
            osh.debug(f"[gateway] {model!r} -> {resolved!r} on {upstream.name} ({why})")
            body = {**body, "model": resolved}

        try:
            return await _forward(body, upstream, "/images/generations", request)
        except ClientGone:
            return _error(
                499,
                "The client disconnected before the engine answered; the upstream "
                "call was cancelled.",
                "client_disconnected",
            )
        except httpx.HTTPError as exc:
            return _error(502, f"Upstream {upstream.name} is unreachable: {exc}", "upstream_error")

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
        from fastapi_mcp import AuthConfig

        mcp = FastApiMCP(
            app,
            # The same key `/v1/charter` demands, on the surface that mirrors
            # it. `/mcp` was open: an unauthenticated caller got a 200 on
            # `initialize`, a session allocated server-side, and a
            # `tools/list` enumerating `charter` and `charter_page`.
            #
            # The charter itself never leaked -- `tools/call` is proxied to the
            # HTTP route and came back 401, which is the same structural
            # property that makes CVE-2026-48710 inapplicable here: this
            # gateway attaches authentication to the *route* rather than
            # matching paths in middleware, so nothing that rewrites a path
            # can shake the dependency loose. But disclosing the inventory and
            # allocating state for an unauthenticated caller is not what the
            # route next door does, and two answers to "is the charter behind
            # a key" is one too many.
            auth_config=AuthConfig(dependencies=[Depends(_authenticate)]),
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


def _prepare_serialised(
    state: State, body: dict[str, Any], upstream: Any, *, locale: str = "en", session: str = ""
):
    """`_prepare`, one at a time, with the lock held by the thread doing it.

    See `State.pipeline`: the lock has to be acquired here rather than around
    the `await`, or a cancelled request releases it while its own screening is
    still running.
    """
    with state.pipeline:
        return _prepare(state, body, upstream, locale=locale, session=session)


def _screen_peer_serialised(state: State, body: dict[str, Any]) -> dict[str, Any]:
    """`handle_message_send`, under the same lock and for the same reason."""
    with state.pipeline:
        return handle_message_send(
            body,
            state.rules,
            state.charter,
            mark_provenance=state.settings.mark_provenance,
        )


def _prepare(
    state: State, body: dict[str, Any], upstream: Any, *, locale: str = "en", session: str = ""
):
    """Run the inbound pipeline for one request."""
    s = state.settings
    counter = state.counter_for(upstream.name, str(body.get("model") or ""))
    return apply_inbound(
        body,
        locale=locale,
        pins=state.pins,
        session=session,
        approved_tools=state.approved_tools,
        charter=state.charter,
        rules=state.rules,
        counter=counter,
        served_context=upstream.served_context,
        compaction_reserve=s.compaction_reserve,
        declared_context=int(upstream.served_context * s.declared_fraction),
        min_working=s.min_working_tokens,
        mark_provenance=s.mark_provenance,
        allow_hosts=s.render_allow_hosts,
        neutralise=s.render_neutralise,
    )


def _headers(upstream: Any) -> dict[str, str]:
    headers = {"content-type": "application/json"}
    if upstream.api_key:
        headers["authorization"] = f"Bearer {upstream.api_key}"
    return headers


#: How much of the audit log's end to read for one page of decisions. A
#: decision is a few hundred bytes, so this holds thousands of them -- far
#: more than the 500 the endpoint will ever return -- and the window grows if
#: it somehow does not.
TAIL_BYTES = 256 * 1024


def read_tail(path: Path, limit: int) -> tuple[list[str], int]:
    """The last ``limit`` lines of a file, and how many lines it has.

    `/v1/decisions` used to do ``read_text().splitlines()`` and slice the end
    of the result: the whole month in memory to show the last hour, which is
    the exact thing its own docstring said an operations page has no business
    doing. Measured on a 200 MiB log, to return fifty lines:

        read_text().splitlines()      1.01 s      470 MiB peak
        this                          0.11 s     2.64 MiB peak

    Linear in the file, so a gateway that has run for months reaches numbers
    that stop being a latency problem and start being an out-of-memory one --
    and the audit log is published as growing without bound, so those numbers
    are expected rather than exotic.

    **Essentially all of the remaining 0.11 s is `total`**, which is counted by
    a buffered scan holding one block at a time. The tail itself is two seeks.
    Keeping the count exact is a deliberate trade: it is a number an operator
    reads next to the lines, this module's whole subject is the difference
    between a number and a guess, and the scan is bounded in memory and runs
    in a worker thread where file reads release the global interpreter lock.
    An estimate would be faster and would be the wrong kind of cheap.
    """
    size = path.stat().st_size
    window = TAIL_BYTES
    with path.open("rb") as handle:
        while True:
            start = max(0, size - window)
            handle.seek(start)
            chunk = handle.read(size - start)
            lines = chunk.split(b"\n")
            if start > 0:
                # The first line is probably cut in half by the seek.
                lines = lines[1:]
            if lines and lines[-1] == b"":
                lines = lines[:-1]
            if len(lines) > limit or start == 0 or window >= size:
                break
            window *= 4

        total = 0
        handle.seek(0)
        while block := handle.read(1024 * 1024):
            total += block.count(b"\n")

    text = [line.decode("utf-8", "replace") for line in lines[-limit:]]
    return text, total


class ClientGone(Exception):
    """The client disconnected before the upstream answered.

    Not an error to report -- there is nobody left to report it to. It exists
    so the handler can stop instead of finishing work for an absent reader.
    """


#: How often to ask whether the client is still there, while an upstream call
#: is in flight. A tenth of a second is far below any generation worth
#: cancelling and far above the cost of asking.
DISCONNECT_POLL = 0.1


async def _client_left(request: Request) -> None:
    """Return once the client has disconnected."""
    while not await request.is_disconnected():
        await asyncio.sleep(DISCONNECT_POLL)


async def _forward(
    body: dict[str, Any], upstream: Any, path: str, request: Request | None = None
) -> dict[str, Any]:
    """Send a prepared request to an upstream and return its JSON.

    Cancelled when the client goes away, which on a single-graphics-processor
    deployment is the whole point. Measured before this existed: a client that
    gave up after one second left the engine free to generate for twenty, and
    the upstream never saw the connection close. That engine is the one this
    project exists to protect -- "one GPU, one charter" -- and it was being
    spent on an answer nobody would read.

    The streaming path already behaves: when the client disconnects, the
    response generator is closed, `client.stream(...)` exits and the socket
    goes with it. Only the awaited call needed watching, which is also what
    the reports against other gateways say -- streaming cancels, the
    non-streaming case keeps the engine busy until generation completes.
    """
    url = upstream.base_url.rstrip("/") + path
    async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT) as client:
        call = asyncio.create_task(client.post(url, json=body, headers=_headers(upstream)))
        if request is None:
            response = await call
        else:
            watch = asyncio.create_task(_client_left(request))
            done, _pending = await asyncio.wait({call, watch}, return_when=asyncio.FIRST_COMPLETED)
            watch.cancel()
            if call not in done:
                # Cancelling the task closes the connection, which is the only
                # thing the engine can act on: vLLM aborts a request whose
                # HTTP connection goes away.
                call.cancel()
                osh.info("[gateway] client disconnected; upstream call cancelled.")
                raise ClientGone
            response = call.result()
        response.raise_for_status()
        return response.json()


async def _stream(
    state: State,
    body: dict[str, Any],
    upstream: Any,
    *,
    locale: str = "en",
    session: str = "",
):
    """Relay a streaming completion, screening the tool calls inside it.

    Screening used to be skipped here, on the argument that a tool call
    arrives in fragments and refusing one would mean buffering the whole
    answer. The first half is true; the second does not follow, because **no
    client can act on half a tool call**. So content deltas stream through
    untouched and only the tool-call fragments are held, assembled, judged
    when the message ends, and then released. The reader sees the answer
    appear exactly as before; what they do not see is a refused command
    reaching their client.

    The assembled calls are screened by `apply_outbound`, the same function
    the non-streamed path uses, so `stream: true` and `stream: false` cannot
    drift into two different enforcement behaviours.
    """
    s = state.settings
    assembler = streaming.Assembler()
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
                if not line:
                    continue
                if line.strip() == "data: [DONE]":
                    break
                if not assembler.feed(line):
                    yield line + "\n\n"
                    continue
                # A frame that carried text beside the tool call: the text is
                # released now, the call waits for its verdict.
                while assembler.spoken:
                    yield assembler.spoken.pop(0) + "\n\n"

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
        return

    # Nothing was held, so there is nothing to judge.
    if not assembler.has_calls:
        yield "data: [DONE]\n\n"
        return

    if assembler.overflowed:
        # A call too large to assemble is a call too large to judge, and
        # releasing an unjudged one is exactly the bypass this path closed.
        # Refused rather than truncated: screening a prefix of a command
        # decides the wrong question confidently.
        osh.warning(
            "[gateway] a streamed tool call exceeded "
            f"{streaming.MAX_ASSEMBLED_CHARS:,} characters and was refused "
            "without being assembled."
        )
        yield _sse(
            {
                "id": assembler.response_id or "chatcmpl-stream",
                "object": "chat.completion.chunk",
                "created": assembler.created or 0,
                "model": assembler.model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                "ai_bunker": {
                    "refused_by": "stream.oversized_tool_call",
                    "reason": (
                        "A tool call arrived larger than "
                        f"{streaming.MAX_ASSEMBLED_CHARS:,} characters. It was not "
                        "assembled and not forwarded: a call too large to screen "
                        "cannot be allowed to run. Ask for a narrower command."
                    ),
                },
            }
        )
        yield "data: [DONE]\n\n"
        return

    if assembler.incomplete:
        # The upstream stream ended mid-arguments. The same argument as the
        # branch above, about the other way a call becomes a prefix -- and
        # here it is not only unjudgeable but dangerous to relay: `rm -rf /`
        # is refused, and cut to `{"command": "rm -rf` it matches nothing,
        # because the rule needs a target. Passing that on with a normal close
        # tells a client a truncated call was screened and is fine.
        osh.warning(
            "[gateway] a streamed tool call ended mid-arguments and was "
            "refused rather than relayed: a verdict on a prefix is not a "
            "verdict on the call."
        )
        yield _sse(
            {
                "id": assembler.response_id or "chatcmpl-stream",
                "object": "chat.completion.chunk",
                "created": assembler.created or 0,
                "model": assembler.model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}],
                "ai_bunker": {
                    "refused_by": "stream.truncated_tool_call",
                    "reason": (
                        "The upstream stream ended before this tool call was "
                        "complete, so its arguments do not parse. It was not "
                        "forwarded: screening a prefix of a command answers the "
                        "wrong question. Ask again."
                    ),
                },
            }
        )
        yield "data: [DONE]\n\n"
        return

    if not s.enforce_commands:
        for held in assembler.held:
            yield held + "\n\n"
        yield "data: [DONE]\n\n"
        return

    outbound = apply_outbound(
        assembler.as_response(),
        rules=state.rules,
        charter_fingerprint=state.charter.fingerprint[:16],
        project_root=s.project_root or None,
        check_payments=s.check_payments,
        trust=state.trust(),
        locale=locale,
        breaker=state.breaker,
        session=session,
    )
    state.audit(outbound.audit())

    # Released either way, so the conversation stays well-formed -- the same
    # arrangement the non-streamed path makes, where the assistant message
    # keeps its `tool_calls` and the refusal travels beside them.
    for held in assembler.held:
        yield held + "\n\n"

    if outbound.refusal is not None:
        refusals = [
            refusal_as_tool_result(call, outbound.refusal) for call in assembler.tool_calls()
        ]
        for frame in streaming.refusal_frames(assembler, outbound.refusal, refusals):
            yield frame

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
