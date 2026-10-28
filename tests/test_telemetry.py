"""Exporting the decision log as OpenTelemetry spans.

The decision log is already a trajectory record. These tests hold the exporter
to the one rule it lives under -- **a collector that is down must never affect
serving** -- and to the audit log's own guarantee, that the matched text never
leaves the process.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ai_bunker.telemetry import MAX_QUEUED, Exporter, Span, span_from_decisions

RECORDS = [
    {
        "rule": "global.generic_secret",
        "scope": "output",
        "severity": "BLOCKER",
        "outcome": "redacted",
        "hits": 1,
        "charter": "aa9fcf72",
    },
    {
        "rule": "shell.destructive_rm",
        "scope": "command",
        "severity": "BLOCKER",
        "outcome": "refused",
        "hits": 1,
        "charter": "aa9fcf72",
    },
]


# ---------------------------------------------------------------------------
# The shape, which another vendor's collector has to accept.
# ---------------------------------------------------------------------------


def test_a_turn_becomes_one_span_another_vendors_collector_will_accept():
    """Two requirements at once, and the second is unforgiving.

    A **trajectory is the shape of a turn**: four decisions in one request is
    one thing that happened, and four unrelated spans would lose the ordering
    an evaluator reads. Nothing to report produces no span at all rather than
    an empty one.

    And the **encoding has to be exactly right**, because a collector rejects
    the whole batch when one attribute is wrong: typed key/value objects
    rather than a flat map, identifiers at the widths OTLP expects, absent
    values dropped rather than encoded as null. A refusal carries status OK --
    it is the gateway working, and ERROR would light up every dashboard for a
    guardrail doing its job.
    """
    assert span_from_decisions([]) is None

    span = span_from_decisions(RECORDS)
    assert span is not None
    assert len(span.events) == 2
    assert span.attributes["ai_bunker.decisions"] == 2
    assert span.refused
    assert span.as_otlp()["status"]["code"] == 1, "OK, not ERROR"

    typed = Span(name="t", attributes={"s": "x", "i": 3, "b": True, "f": 1.5}).as_otlp()
    kinds = {a["key"]: next(iter(a["value"])) for a in typed["attributes"]}
    assert kinds == {"s": "stringValue", "i": "intValue", "b": "boolValue", "f": "doubleValue"}

    bare = Span(name="t").as_otlp()
    assert len(bare["traceId"]) == 32
    assert len(bare["spanId"]) == 16

    sparse = Span(name="t", attributes={"present": "x", "absent": None}).as_otlp()
    assert [a["key"] for a in sparse["attributes"]] == ["present"]


# ---------------------------------------------------------------------------
# The guarantee: what leaves the process.
# ---------------------------------------------------------------------------


def test_the_matched_text_never_leaves_the_process():
    """Not an accident of this module: it exports the audit records rather
    than re-deriving them, which is what keeps the guarantee true in both
    places."""
    exporter = Exporter("http://127.0.0.1:9")
    span = span_from_decisions(RECORDS)
    assert span is not None
    body = json.dumps(exporter.payload(span))
    for secret in ("sk_live", "hT3kQm9Zx", "AKIA", "rm -rf /"):
        assert secret not in body


def test_the_service_identifies_itself():
    exporter = Exporter("http://127.0.0.1:9", service_name="gw-paris")
    span = span_from_decisions(RECORDS)
    assert span is not None
    resource = exporter.payload(span)["resourceSpans"][0]["resource"]
    names = {a["key"]: a["value"]["stringValue"] for a in resource["attributes"]}
    assert names["service.name"] == "gw-paris"


def test_the_endpoint_gets_the_otlp_traces_path():
    assert Exporter("http://collector:4318/").url == "http://collector:4318/v1/traces"


# ---------------------------------------------------------------------------
# The rule this module lives under.
# ---------------------------------------------------------------------------


def test_a_collector_that_stopped_answering_costs_the_deployment_nothing():
    """The rule this module lives under. The moment telemetry can delay a
    request it has become part of the request path, and the deployment is
    worse off than with no telemetry at all.

    So against a port where nothing listens: five hundred exports do not
    block, nothing raises, exporting nothing is a no-op, and the queue in
    front of the collector has a ceiling -- an unbounded one is a memory leak
    with a schedule.
    """
    exporter = Exporter("http://127.0.0.1:9")  # nothing listens on port 9

    start = time.perf_counter()
    for _ in range(500):
        exporter.export(span_from_decisions(RECORDS))
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"exporting blocked the caller for {elapsed:.2f}s"

    exporter.export(None)  # must not raise either
    assert MAX_QUEUED > 0
    assert exporter._queue.maxsize == MAX_QUEUED
    time.sleep(0.3)  # let the worker drain before the fixture tears down


# ---------------------------------------------------------------------------
# Against a real collector.
# ---------------------------------------------------------------------------


@pytest.fixture
def collector():
    """A listener that records what it is sent."""
    seen: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            seen.append(json.loads(self.rfile.read(length)))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", seen
    server.shutdown()


def test_a_span_reaches_a_collector(collector):
    endpoint, seen = collector
    exporter = Exporter(endpoint, service_name="under-test")
    exporter.export(span_from_decisions(RECORDS))

    for _ in range(100):
        if seen:
            break
        time.sleep(0.05)

    assert seen, "the collector received nothing"
    span = seen[0]["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert span["name"] == "ai-bunker.turn"
    assert {e["name"] for e in span["events"]} == {
        "global.generic_secret",
        "shell.destructive_rm",
    }


def test_the_gateway_exports_when_an_endpoint_is_configured(collector):
    endpoint, seen = collector
    from ai_bunker.config import Settings, Upstream
    from ai_bunker.gateway import create_app

    app = create_app(
        Settings(
            api_key="",
            upstreams={"local": Upstream(name="local", base_url="http://up.test/v1")},
            default_upstream="local",
            enable_mcp=False,
            telemetry_endpoint=endpoint,
        )
    )
    app.state.bunker.audit(RECORDS)

    for _ in range(100):
        if seen:
            break
        time.sleep(0.05)
    assert seen, "the gateway did not export"


def test_no_endpoint_means_no_exporter():
    from ai_bunker.config import Settings, Upstream
    from ai_bunker.gateway import create_app

    app = create_app(
        Settings(
            api_key="",
            upstreams={"local": Upstream(name="local", base_url="http://up.test/v1")},
            default_upstream="local",
            enable_mcp=False,
        )
    )
    assert app.state.bunker.exporter() is None
    app.state.bunker.audit(RECORDS)  # must not raise
