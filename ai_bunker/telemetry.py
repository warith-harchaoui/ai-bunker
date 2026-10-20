"""Export the decision log as OpenTelemetry spans.

Why this needs no new dependency
--------------------------------
The decision log is already a trajectory record: an ordered account of what an
agent's turn did and what the gateway did about it. Evaluating trajectories is
what OpenTelemetry tooling is for, and the only thing standing between the two
is a wire format.

OTLP over HTTP with a JSON body is that format, and it is small enough to
write. The alternative -- the OpenTelemetry SDK -- pulls a large dependency
tree into a gateway whose whole argument is that it is a thin thing you can
read. A hundred lines here buys interoperability with every collector without
that.

The rule this module lives under
--------------------------------
**A collector that is down must never affect serving.** Telemetry is an
observer; the moment it can refuse a request, or delay one, it has become part
of the request path and the deployment is worse than it was with none. So:
every export runs on a daemon thread, every failure is swallowed after one
warning, and the queue has a ceiling it drops from rather than growing.

What is exported
----------------
Exactly what the audit log holds, which is rules and outcomes and never the
text that matched. That is not an accident of this module; it is the audit
log's own guarantee, and exporting its records rather than re-deriving them is
what keeps the guarantee true in both places.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

import os_helper as osh

from ai_bunker import __version__

#: Dropped rather than queued beyond this. An unbounded queue in front of a
#: collector that stopped answering is a memory leak with a schedule.
MAX_QUEUED = 1000

#: Short on purpose: this runs off the request path, but a thread blocked for
#: a minute per export still piles up.
EXPORT_TIMEOUT = 5.0


def _hex(length: int) -> str:
    """Trace and span ids: random hex of the width OTLP expects."""
    return os.urandom(length // 2).hex()


@dataclass
class Span:
    """One screened turn, with its decisions as events."""

    name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    trace_id: str = ""
    span_id: str = ""
    start_ns: int = 0
    end_ns: int = 0
    refused: bool = False

    def as_otlp(self) -> dict[str, Any]:
        span: dict[str, Any] = {
            "traceId": self.trace_id or _hex(32),
            "spanId": self.span_id or _hex(16),
            "name": self.name,
            "kind": 2,  # SPAN_KIND_SERVER
            "startTimeUnixNano": str(self.start_ns),
            "endTimeUnixNano": str(self.end_ns or self.start_ns),
            "attributes": _attributes(self.attributes),
            "events": [
                {
                    "timeUnixNano": str(event.pop("_at", self.start_ns)),
                    "name": event.pop("_name", "decision"),
                    "attributes": _attributes(event),
                }
                for event in self.events
            ],
        }
        if self.refused:
            # A refusal is not an error in the gateway; it is the gateway
            # working. ERROR here would light up every dashboard for a
            # guardrail doing its job, so it is an attribute, not a status.
            span["status"] = {"code": 1}  # STATUS_CODE_OK
        return span


def _attributes(values: dict[str, Any]) -> list[dict[str, Any]]:
    """OTLP's attribute encoding: a list of typed key/value objects."""
    out = []
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, bool):
            item: dict[str, Any] = {"boolValue": value}
        elif isinstance(value, int):
            item = {"intValue": str(value)}
        elif isinstance(value, float):
            item = {"doubleValue": value}
        else:
            item = {"stringValue": str(value)}
        out.append({"key": key, "value": item})
    return out


def span_from_decisions(
    records: list[dict[str, Any]], *, name: str = "ai-bunker.turn"
) -> Span | None:
    """Turn one batch of audit records into a span with an event per decision.

    A span per turn rather than per decision, because a trajectory is the shape
    of a turn: four decisions in one request is one thing that happened, and
    four unrelated spans would lose exactly the ordering an evaluator reads.
    """
    if not records:
        return None

    now = time.time_ns()
    # A withheld tool sets the span's error status alongside a refusal: both
    # are the gateway stopping something, and a trace that marks only one of
    # them makes the other invisible to whoever is reading the traces.
    refused = any(r.get("outcome") == "refused" for r in records)
    withheld = any(r.get("outcome") == "withheld" for r in records)
    return Span(
        name=name,
        start_ns=now,
        end_ns=now,
        refused=refused or withheld,
        attributes={
            "ai_bunker.decisions": len(records),
            "ai_bunker.refused": refused,
            "ai_bunker.withheld": withheld,
            "ai_bunker.charter": records[0].get("charter", ""),
        },
        events=[
            {
                "_name": str(record.get("rule") or "decision"),
                "_at": now,
                "rule": record.get("rule"),
                "scope": record.get("scope"),
                "severity": record.get("severity"),
                "outcome": record.get("outcome"),
                "hits": record.get("hits"),
            }
            for record in records
        ],
    )


class Exporter:
    """Ships spans to an OTLP/HTTP collector, off the request path.

    Constructed once and shared. `export` returns immediately; a daemon thread
    does the network call and is allowed to fail silently after saying so once,
    because the alternative -- a serving gateway that stops when a telemetry
    collector does -- is strictly worse than no telemetry.
    """

    def __init__(self, endpoint: str, *, service_name: str = "ai-bunker") -> None:
        self.endpoint = endpoint.rstrip("/")
        self.service_name = service_name
        self.dropped = 0
        self.sent = 0
        self._complained = False
        self._queue: queue.Queue[Span] = queue.Queue(maxsize=MAX_QUEUED)
        self._thread = threading.Thread(target=self._drain, daemon=True, name="ai-bunker-otlp")
        self._thread.start()

    @property
    def url(self) -> str:
        return f"{self.endpoint}/v1/traces"

    def export(self, span: Span | None) -> None:
        """Queue a span. Never blocks, never raises."""
        if span is None:
            return
        try:
            self._queue.put_nowait(span)
        except queue.Full:
            self.dropped += 1
            if not self._complained:
                self._complained = True
                osh.warning(
                    f"[telemetry] the collector at {self.endpoint} is not keeping up; "
                    "spans are being dropped. Serving is unaffected."
                )

    def _drain(self) -> None:  # pragma: no cover - exercised via the queue
        while True:
            span = self._queue.get()
            try:
                self._send(span)
                self.sent += 1
            except Exception as exc:
                if not self._complained:
                    self._complained = True
                    osh.warning(
                        f"[telemetry] could not reach the collector at {self.endpoint} "
                        f"({exc}). Serving is unaffected; this is said once."
                    )
            finally:
                self._queue.task_done()

    def payload(self, span: Span) -> dict[str, Any]:
        """The OTLP ExportTraceServiceRequest body."""
        return {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": _attributes(
                            {
                                "service.name": self.service_name,
                                "service.version": __version__,
                            }
                        )
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "ai-bunker", "version": __version__},
                            "spans": [span.as_otlp()],
                        }
                    ],
                }
            ]
        }

    def _send(self, span: Span) -> None:
        body = json.dumps(self.payload(span)).encode()
        request = urllib.request.Request(
            self.url, data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=EXPORT_TIMEOUT) as response:
            response.read()
