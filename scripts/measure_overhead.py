#!/usr/bin/env python3
"""What a turn costs crossing this gateway, in milliseconds and in tokens.

Why this exists
---------------
`LANDSCAPE.md` says, under *Where this project is behind*:

    **Throughput: Bifrost.** Written in Go specifically to get out from under
    Python's global interpreter lock [...] This is Python in the request path,
    and honest about it.

Honest, and unquantified. Two measurement scripts already live here and both
measure the **model**: `bench_context.py` fits decode time against prompt
length, `measure_ratio.py` replaced a folklore constant with a measured floor.
Neither measures **this project**, so the one cost ai-bunker imposes on every
user of it was the one figure it estimated by saying nothing.

A proxy that cannot state its own overhead is asking to be trusted rather than
read, which is the posture this repository exists to refuse.

What it measures
----------------
`apply_inbound` -- the whole inbound pipeline, which is stages 01 to 03 of the
figure in README: screen the tool declarations, screen the inbound tool
results, inject the charter, measure the budget. No network, no engine, no
model. That is deliberate: the engine's own time is the thing being added to,
and mixing them produces a ratio that says more about the hardware than about
the code.

Two costs, because they are not the same kind of thing:

**Milliseconds**, which a user waits for once per turn. Reported as a median
and a 95th percentile over repeated runs, because a mean hides exactly the
tail a request path is judged on.

**Tokens**, which a user pays for on every turn for the rest of the session.
The charter and the knowledge index are injected into the system prompt, so
they are not a one-off -- they are rent.

What it cannot do
-----------------
It measures this machine. A figure from a laptop is not a figure from the
server, and the script prints the processor it ran on rather than letting the
number travel without it.

It measures with the **ratio** counter unless a tokenizer is reachable, and
says which. A tokenizer call is a network round trip to the engine, which
would swamp everything else here and is reported separately when present.

And it is not a benchmark of the gateway as a whole: `apply_inbound` is the
work, but a real request also pays FastAPI's routing, JSON parsing and the
thread hop. Those are bounded by the request ceiling and are not where the
interesting cost is; this measures the part that scales with what arrives.

    python scripts/measure_overhead.py
    python scripts/measure_overhead.py --repeats 50 --json

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ai_bunker.budget import Counter  # noqa: E402
from ai_bunker.charter import load_charter  # noqa: E402
from ai_bunker.pipeline import apply_inbound  # noqa: E402
from ai_bunker.rules import load_rules  # noqa: E402

#: The served context the measurement assumes. It only affects the ceiling and
#: the verdict, not the work, but a figure measured against an unstated
#: configuration is a figure nobody can reproduce.
SERVED_CONTEXT = 32_768

#: Request shapes, smallest first. Each is one turn as a client actually sends
#: it, and the point of having three is that the cost is not one number: a
#: turn carrying a 40-kilobyte tool result pays for screening it, and a turn
#: carrying none does not.
SHAPES: dict[str, dict] = {
    "bare": {
        "model": "m",
        "messages": [{"role": "user", "content": "add a test for the parser"}],
    },
    "with tools": {
        "model": "m",
        "messages": [{"role": "user", "content": "add a test for the parser"}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": f"tool_{i}",
                    "description": "Does a thing to a file and returns what it did. " * 4,
                    "parameters": {
                        "type": "object",
                        "properties": {"path": {"type": "string"}, "body": {"type": "string"}},
                    },
                },
            }
            for i in range(12)
        ],
    },
    "with a 40 kB tool result": {
        "model": "m",
        "messages": [
            {"role": "user", "content": "what does the log say"},
            {"role": "tool", "content": "2026-10-29 INFO handled request id=0\n" * 1400},
        ],
    },
}


def _kwargs() -> dict:
    return {
        "charter": load_charter(str(ROOT / "charter")),
        "rules": load_rules(str(ROOT / "charter" / "rules")),
        "counter": Counter(allow_ratio=True),
        "served_context": SERVED_CONTEXT,
    }


def measure(name: str, body: dict, repeats: int) -> dict:
    """One shape, timed, with the token rent it adds reported beside it."""
    kwargs = _kwargs()

    # One untimed pass: the charter is read from disk and the rules compile
    # their patterns on first use, and charging a per-request figure for work
    # that happens once per process would be the kind of number this script
    # exists to stop being quoted.
    first = apply_inbound(body, **kwargs)

    timings = []
    for _ in range(repeats):
        start = time.perf_counter()
        apply_inbound(body, **kwargs)
        timings.append((time.perf_counter() - start) * 1000)

    ours = sum(i.tokens for i in first.budget.items if i.owner != "client") if first.budget else 0
    floor = first.budget.floor_tokens if first.budget else 0
    return {
        "shape": name,
        "characters_in": len(json.dumps(body)),
        "median_ms": round(statistics.median(timings), 2),
        "p95_ms": round(sorted(timings)[int(len(timings) * 0.95) - 1], 2),
        "tokens_added": ours,
        "floor_tokens": floor,
        "share_of_context": round(ours / SERVED_CONTEXT * 100, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=30, help="timed passes per shape")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    rows = [measure(name, body, args.repeats) for name, body in SHAPES.items()]
    counter = Counter(allow_ratio=True)

    if args.json:
        print(
            json.dumps(
                {
                    "machine": platform.processor() or platform.machine(),
                    "python": platform.python_version(),
                    "served_context": SERVED_CONTEXT,
                    "counter": counter.backend,
                    "repeats": args.repeats,
                    "shapes": rows,
                },
                indent=2,
            )
        )
        return 0

    print(f"\n  ai-bunker inbound pipeline, {args.repeats} passes per shape")
    print(f"  {platform.processor() or platform.machine()}, Python {platform.python_version()}")
    print(f"  counted by: {counter.backend}; served context {SERVED_CONTEXT:,}\n")
    print(f"  {'SHAPE':<28}{'CHARS':>9}{'MEDIAN':>10}{'P95':>9}{'OUR TOKENS':>12}{'OF CTX':>8}")
    print(f"  {'-' * 76}")
    for r in rows:
        print(
            f"  {r['shape']:<28}{r['characters_in']:>9,}{r['median_ms']:>9.2f}ms"
            f"{r['p95_ms']:>8.2f}ms{r['tokens_added']:>12,}{r['share_of_context']:>7.1f}%"
        )
    print()
    print("  Milliseconds are waited once per turn. Tokens are paid on every turn")
    print("  for the rest of the session -- the charter and the index are rent, not")
    print("  a one-off, which is why the claim they cost under 5% of the window is")
    print("  the column on the right rather than a sentence in the README.")
    print("\n  Measured on this machine. A figure from a laptop is not a figure from")
    print("  the server; re-run it there before quoting it there.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
