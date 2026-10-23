"""
The gateway has to keep answering while one request is counting tokens.

Why this exists
---------------
Round 6 of this project's own review found that `Counter` probes each
tokenizer dialect with a synchronous HTTP call inside an asynchronous
handler, so for as long as a stalled engine took to time out, **the gateway
served nobody**. It was bounded at five seconds per dialect, published as a
limitation in both READMEs, and then deferred eight times.

Measured here before the fix, against a real socket that accepts and never
answers: `/health` took **9.73 seconds** -- two dialects at `PROBE_TIMEOUT`
each -- while one completion was being prepared. After it: 0.01 seconds.

What the fix is, and is not
---------------------------
`_prepare` now runs in a worker thread, under a lock. Both halves matter:
moving it off the loop is what frees the gateway, and the lock is what stops
that becoming the first time two requests mutated `counters`, `pins`,
`approved_tools` and the breaker at once -- none of which has ever needed a
lock because nothing was ever concurrent. Trading an availability defect for
a data race is not a fix.

So counting is still serialised, exactly as serialised as when it ran on the
loop. What changed is that the loop is free while it happens.

A real socket rather than `MockTransport`, because `MockTransport` ignores the
client's timeout: round 6's first measurement used one, showed no difference,
and proved nothing.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest

from ai_bunker import budget as budget_module
from ai_bunker.config import Settings, Upstream
from ai_bunker.gateway import create_app

uvicorn = pytest.importorskip("uvicorn", reason="this test needs a real server")

#: Shortened from five seconds so the test costs about two rather than ten.
#: The assertion below is expressed against *this* number rather than against
#: a duration somebody measured on a laptop: round 7 of the review wrote down
#: that a wall-clock assertion is a measurement of a machine, and then this
#: project wrote one anyway two commits later.
PROBE = 1


@pytest.fixture
def deaf_engine():
    """A socket that accepts connections and answers nothing, ever.

    Not a closed port: a refused connection fails instantly and measures
    nothing. The defect needs an engine that is reachable and silent, which is
    what a saturated graphics processing unit looks like from here.
    """
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(64)
    held: list[socket.socket] = []

    def accept_forever():
        while True:
            try:
                held.append(listener.accept()[0])
            except OSError:
                return

    threading.Thread(target=accept_forever, daemon=True).start()
    yield listener.getsockname()[1]
    listener.close()
    for connection in held:
        connection.close()


@pytest.fixture
def served(deaf_engine, monkeypatch):
    """The gateway on a real port, pointed at the silent engine."""
    monkeypatch.setattr(budget_module, "PROBE_TIMEOUT", PROBE)

    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    settings = Settings(
        api_key="",
        charter_dir="charter",
        rules_dir="charter/rules",
        upstreams={
            "local": Upstream(
                name="local",
                base_url=f"http://127.0.0.1:{deaf_engine}/v1",
                served_context=32768,
                model="m",
            )
        },
        default_upstream="local",
        audit_log="",
        enable_mcp=False,
    )
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="critical")
    )
    threading.Thread(target=server.run, daemon=True).start()

    base = f"http://127.0.0.1:{port}"
    for _ in range(200):
        try:
            httpx.get(f"{base}/health", timeout=1.0)
            break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:  # pragma: no cover - the server did not come up
        server.should_exit = True
        pytest.skip("the test server did not start")

    yield base
    server.should_exit = True


def test_a_stalled_tokenizer_does_not_stop_the_gateway_answering(served):
    """The defect, as a property rather than as a duration.

    `/health` reads nothing and counts nothing: it is the cheapest answer this
    gateway gives, so the only reason for it to take time is that the event
    loop is busy. While a request is stuck probing a silent engine, the worst
    `/health` answer must stay **below one probe timeout** -- the thing being
    waited on.

    Before the fix it was about twice that bound, because the probe tries two
    dialects. After it, three orders of magnitude under. No plausible
    difference in machine speed sits between those two readings.
    """
    busy = threading.Thread(
        target=lambda: _ignore_errors(
            httpx.post,
            f"{served}/v1/budget",
            json={"model": "m", "messages": [{"role": "user", "content": "hello " * 200}]},
            timeout=30.0,
        ),
        daemon=True,
    )
    busy.start()
    time.sleep(0.3)  # let it reach the tokenizer

    latencies = []
    for _ in range(5):
        started = time.perf_counter()
        _ignore_errors(httpx.get, f"{served}/health", timeout=30.0)
        latencies.append(time.perf_counter() - started)
        time.sleep(0.1)
    busy.join(timeout=30)

    worst = max(latencies)
    assert worst < PROBE, (
        f"the worst /health answer was {worst:.2f}s against a {PROBE}s probe "
        "timeout: the event loop is blocked while a request counts tokens"
    )


def test_the_pipeline_is_serialised_rather_than_merely_moved(served):
    """The other half, and the reason the lock is there.

    Nothing in `State` has ever needed a lock, because nothing was ever
    concurrent: the pipeline ran on the event loop and therefore ran alone.
    Moving it to a worker thread without one would have made two requests
    mutate `counters`, `pins`, `approved_tools` and the breaker at the same
    time -- an availability fix paid for with a data race.

    Asserted on the object rather than by trying to provoke a race, which no
    test can do reliably: a race that does not reproduce is not absent.
    """
    import asyncio

    from ai_bunker.gateway import create_app as build

    app = build(
        Settings(
            api_key="",
            charter_dir="charter",
            rules_dir="charter/rules",
            upstreams={"local": Upstream(name="local", base_url="http://127.0.0.1:1/v1")},
            default_upstream="local",
            audit_log="",
            enable_mcp=False,
        )
    )
    assert isinstance(app.state.bunker.pipeline, asyncio.Lock)


def _ignore_errors(call, *args, **kwargs):
    try:
        return call(*args, **kwargs)
    except Exception:
        return None


def test_screening_a_peer_message_keeps_the_gateway_answering(served):
    """The same surface neither earlier fix reached, and the honest property.

    `/a2a/v1/message:send` screens text *another agent wrote* with the
    output-scope rules, and it ran them on the event loop with no size
    ceiling: four megabytes from a peer froze the gateway for 7.08 seconds,
    measured, and screening is linear, so forty would have cost seventy.

    **What a worker thread can and cannot buy**, measured rather than assumed:

        work in a thread      worst event-loop stall
        time.sleep(1.0)                      3.4 ms
        re.findall x12                      35.8 ms  (over 0.17s of work)

    `re` does not release the global interpreter lock. So moving screening to
    a thread gives the loop slices between lock hand-offs and does **not**
    free it -- unlike the tokenizer probe, which waits on a socket and whose
    9.73-second freeze really did become 0.01. A ratio assertion here would
    be asserting something false.

    What actually bounds the stall is the **request ceiling**: that is why it
    had to reach this surface, and why its absence here mattered more than it
    looked. So this asserts liveness -- every `/health` answers, none times
    out -- and `test_ceiling.py` asserts the bound.
    """
    big = "x" * 400_000
    body = {"message": {"role": "ROLE_USER", "messageId": "m-1", "parts": [{"text": big}]}}
    answered = []

    def screen():
        _ignore_errors(httpx.post, f"{served}/a2a/v1/message:send", json=body, timeout=60.0)

    worker = threading.Thread(target=screen, daemon=True)
    worker.start()
    while worker.is_alive() and len(answered) < 12:
        response = _ignore_errors(httpx.get, f"{served}/health", timeout=10.0)
        answered.append(response is not None and response.status_code == 200)
    worker.join(timeout=60)

    assert answered, "the screen finished before a single /health went out"
    assert all(answered), (
        f"{answered.count(False)} of {len(answered)} /health calls failed while "
        "a peer message was being screened"
    )


def test_the_audit_tail_agrees_with_reading_the_whole_file(tmp_path):
    """`read_tail` against the thing it replaced, character for character.

    `/v1/decisions` did `read_text().splitlines()` and sliced the end: on a
    200 MiB log that is 1.01 seconds and **470 MiB of peak memory** to return
    fifty lines, and the audit log is published as growing without bound, so
    those numbers are expected rather than exotic. The replacement seeks from
    the end: 0.11 seconds, 2.64 MiB, almost all of it the exact `total`.

    This is a rewrite of the only read path onto the audit record, so the test
    is **differential**: the naive version is written out below and the two
    must agree, on shapes chosen to be awkward rather than representative --
    an empty file, no trailing newline, blank lines, one line longer than the
    seek window, and more lines than any window holds.
    """
    from ai_bunker.gateway import read_tail

    shapes = {
        "empty": "",
        "one line": "a\n",
        "no trailing newline": "a\nb\nc",
        "blank lines": "a\n\n\nb\n",
        "unicode": "héllo\nwörld\n",
        "one line past the window": "x" * 500_000 + "\n",
        "more lines than a window": "".join(f"{n}\n" for n in range(5000)),
        "few, each very long": "".join("y" * 9000 + "\n" for _ in range(40)),
    }
    for label, body in shapes.items():
        path = tmp_path / "decisions.jsonl"
        path.write_text(body, encoding="utf-8")
        for limit in (1, 3, 50, 500):
            naive = body.splitlines()
            expected = naive[-max(1, limit) :] if naive else []
            lines, total = read_tail(path, limit)
            assert lines == expected, f"{label} at limit {limit}"
            assert total == body.count("\n"), f"{label}: total"
