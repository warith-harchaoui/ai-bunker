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

import contextlib
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


def test_the_pipeline_lock_survives_a_cancelled_request():
    """Why the lock is a `threading` one, which cost a day to learn.

    Round 15 wrote `async with state.pipeline: await run_in_threadpool(...)`
    and this test asserted `isinstance(..., asyncio.Lock)`, which was the
    right assertion about the wrong design. Uvicorn cancels the handler the
    moment a client disconnects; the `async with` then exits and **releases
    the lock**, while the worker thread runs on, because a thread cannot be
    cancelled. The next request takes the lock and starts its own `_prepare`
    beside the first.

    Measured over the exact shape the gateway used, counting how many bodies
    were inside the critical section at once:

        async lock around the await        peak 2
        threading lock inside the worker   peak 1

    An asynchronous lock cannot guard work that outlives the await. The lock
    belongs to whoever is doing the work.
    """
    import asyncio
    import threading as threads

    from fastapi.concurrency import run_in_threadpool

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
    lock = app.state.bunker.pipeline
    assert isinstance(lock, type(threads.Lock())), (
        "an asyncio.Lock here is released by the cancellation that a "
        "disconnecting client triggers, while the worker it was guarding runs on"
    )

    # And the property itself, over the gateway's own lock.
    inside: list[str] = []
    peak = 0

    def work(tag: str, seconds: float) -> None:
        nonlocal peak
        with lock:
            inside.append(tag)
            peak = max(peak, len(inside))
            time.sleep(seconds)
            inside.remove(tag)

    async def exercise() -> None:
        first = asyncio.create_task(run_in_threadpool(work, "A", 0.6))
        await asyncio.sleep(0.15)
        first.cancel()  # the client walked away
        with contextlib.suppress(asyncio.CancelledError):
            await first
        assert inside == ["A"], "the cancelled request's own work must still be running"
        await run_in_threadpool(work, "B", 0.05)

    asyncio.run(exercise())
    assert peak == 1, f"{peak} requests were inside the pipeline at once"


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


@pytest.fixture
def slow_engine():
    """An engine that answers `/tokenize` at once and a completion slowly.

    The probe has to be fast or it spends `PROBE_TIMEOUT` before the forward
    even starts -- which is how the first version of this measurement
    concluded "the engine kept working" while watching the *tokenizer's*
    connection and never seeing the completion reach the upstream at all.
    """
    answer_after = 20.0
    seen: dict[str, float | None] = {}

    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)

    def handle(conn: socket.socket) -> None:
        request = conn.recv(65536).decode("latin1", "replace")
        path = request.split(" ")[1] if " " in request else "?"
        if "tokenize" in path:
            conn.sendall(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n")
            conn.close()
            return
        started = time.perf_counter()
        conn.settimeout(0.1)
        hung_up = None
        while time.perf_counter() - started < answer_after:
            try:
                if conn.recv(1) == b"":
                    hung_up = time.perf_counter() - started
                    break
            except TimeoutError:
                continue
            except OSError:
                hung_up = time.perf_counter() - started
                break
        seen[path] = hung_up
        conn.close()

    def serve() -> None:
        while True:
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            threading.Thread(target=handle, args=(connection,), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    yield listener.getsockname()[1], seen, answer_after
    listener.close()


def test_a_client_that_gives_up_stops_the_engine(slow_engine, monkeypatch):
    """The defect this project's own thesis makes expensive.

    `/v1/chat/completions` without `stream` awaited the upstream and watched
    nothing. Measured: a client that gave up after **one second** left the
    engine free to generate for **twenty**, and the upstream never saw the
    connection close. On one graphics processor -- which is the deployment
    this project is about -- that processor is then spending itself on an
    answer nobody will read, and serving nobody else while it does.

    Reported against several gateways with the same shape: streaming cancels
    on its own, because closing the response generator closes the socket; the
    awaited call is the one that keeps the engine busy until generation
    completes.

    Asserted on what the *engine* can act on -- whether its connection closed
    -- rather than on what the gateway logged. vLLM aborts a request whose
    HTTP connection goes away; a gateway that merely stops waiting has
    cancelled nothing.
    """
    port, seen, answer_after = slow_engine
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    local = probe.getsockname()[1]
    probe.close()

    settings = Settings(
        api_key="",
        charter_dir="charter",
        rules_dir="charter/rules",
        upstreams={
            "local": Upstream(
                name="local",
                base_url=f"http://127.0.0.1:{port}/v1",
                served_context=32768,
                model="m",
            )
        },
        default_upstream="local",
        audit_log="",
        enable_mcp=False,
    )
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=local, log_level="critical")
    )
    threading.Thread(target=server.run, daemon=True).start()
    base = f"http://127.0.0.1:{local}"
    for _ in range(200):
        try:
            httpx.get(f"{base}/health", timeout=1.0)
            break
        except httpx.HTTPError:
            time.sleep(0.05)

    _ignore_errors(
        httpx.post,
        f"{base}/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        timeout=1.0,
    )
    deadline = time.perf_counter() + answer_after + 2
    while time.perf_counter() < deadline and "/v1/chat/completions" not in seen:
        time.sleep(0.1)
    server.should_exit = True

    assert "/v1/chat/completions" in seen, "the completion never reached the upstream"
    hung_up = seen["/v1/chat/completions"]
    assert hung_up is not None, (
        f"the upstream never saw the connection close: it was free to generate "
        f"for the full {answer_after:.0f}s for a client that left after 1s"
    )
    assert hung_up < answer_after / 4, (
        f"the upstream kept the request for {hung_up:.1f}s after a client that left at 1s"
    )
