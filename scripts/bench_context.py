"""Measure what context costs in decode throughput, on this machine.

Why
---
Every sizing figure this repository publishes is arithmetic: a memory roofline
over a catalogue. The argument for context discipline is made the same way --
a bigger KV cache means fewer concurrent sessions. That is true, and it is also
only half the cost. The other half is that the KV cache is **read on every
decoded token**, so a long context does not merely fill the machine, it slows
it down, and no amount of VRAM fixes that.

This measures the slope directly. Decode time per token should behave as

    ms/token = fixed overhead + (weights + kv(context)) / bandwidth

so sweeping the prompt length and fitting a line separates the context term
from everything that does not depend on it.

What it cannot do
-----------------
One model gives one weight figure, so the intercept conflates fixed overhead
with the weight read and cannot be split. Charging the whole intercept to
bandwidth yields a **lower bound** on efficiency, never a measurement of it.
The script says so in its output rather than letting the number be quoted as
if it settled the question.

Usage
-----
    python scripts/bench_context.py                      # against Ollama
    python scripts/bench_context.py --model qwen3-vl:4b --repeats 3
    python scripts/bench_context.py --base-url http://127.0.0.1:11434

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import urllib.error
import urllib.request

#: Ordinary prose, so the tokenizer sees a realistic ratio rather than filler.
FILLER = (
    "The gateway counts the context budget with the server's own tokenizer "
    "rather than trusting the client's estimate. "
)

#: Repetitions of FILLER, chosen to land near 0.2k, 3k, 12k, 22k and 32k tokens.
POINTS = (10, 150, 600, 1100, 1600)

#: Spread above this fraction of the median means the machine was doing
#: something else. A laptop that is also running an editor is the normal case,
#: not the exception, so the script says so rather than printing the number.
NOISE_FRACTION = 0.15


def decode(base_url: str, model: str, reps: int, predict: int) -> tuple[int, float]:
    """Return (prompt tokens, decode tokens/second) for one generation."""
    body = {
        "model": model,
        "prompt": FILLER * reps + "\nReply with one word.",
        "stream": False,
        "options": {"num_predict": predict, "temperature": 0, "num_ctx": 32768},
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        payload = json.load(response)
    seconds = payload["eval_duration"] / 1e9
    if seconds <= 0 or not payload.get("eval_count"):
        raise SystemExit("the engine decoded nothing; is the model loaded?")
    return payload["prompt_eval_count"], payload["eval_count"] / seconds


def fit(rows: list[tuple[int, float]]) -> tuple[float, float]:
    """Least squares on (context, ms/token). Returns (intercept, slope)."""
    n = len(rows)
    xs = [r[0] for r in rows]
    ys = [1000 / r[1] for r in rows]
    sx, sy = sum(xs), sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys, strict=True))
    slope = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    return (sy - slope * sx) / n, slope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3-vl:4b")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--predict", type=int, default=128)
    args = parser.parse_args(argv)

    try:
        # The first call of a session pays the model load. Measuring it would
        # measure the disk.
        decode(args.base_url, args.model, 10, 8)
    except (urllib.error.URLError, OSError) as exc:
        print(f"no engine at {args.base_url}: {exc}", file=sys.stderr)
        return 2

    print(
        f"{args.model} via {args.base_url}, {args.predict} tokens decoded, median of {args.repeats}"
    )
    print(f"{'prompt tokens':>14} {'tok/s':>8} {'spread':>8}")

    rows: list[tuple[int, float]] = []
    noisy: list[str] = []
    for reps in POINTS:
        observations = [
            decode(args.base_url, args.model, reps, args.predict) for _ in range(args.repeats)
        ]
        context = int(statistics.median(o[0] for o in observations))
        rates = [o[1] for o in observations]
        median = statistics.median(rates)
        spread = max(rates) - min(rates)
        rows.append((context, median))
        flag = ""
        if args.repeats > 1 and spread > NOISE_FRACTION * median:
            flag = "  <- noisy"
            noisy.append(f"{context} tokens: {spread / median * 100:.0f}% spread")
        print(f"{context:>14} {median:>8.1f} {spread:>8.1f}{flag}", flush=True)

    # A point that is faster than the one before it means something other than
    # context moved the result.
    inversions = [
        f"{rows[i][0]} -> {rows[i + 1][0]}"
        for i in range(len(rows) - 1)
        if rows[i + 1][1] > rows[i][1] * 1.02
    ]

    intercept, slope = fit(rows)
    print()
    print(f"ms/token = {intercept:.1f} + {slope * 1000:.2f} per 1k context tokens")
    print(
        f"throughput falls {rows[0][1] / rows[-1][1]:.2f}x "
        f"between {rows[0][0]} and {rows[-1][0]} prompt tokens"
    )

    if noisy or inversions:
        print()
        print("This machine was busy while measuring, so the absolute numbers")
        print("are not trustworthy; run it again on an idle machine.")
        for line in noisy:
            print(f"  wide spread at {line}")
        if inversions:
            print(f"  throughput rose with context at: {', '.join(inversions)}")
        print("The slope survives this better than the intercept does -- under")
        print("load one run here gave half the absolute rate and a slope within")
        print("6% -- but the table should not be published.")

    print()
    print("The slope is the cost of context, and it is paid on every token.")
    print("The intercept mixes fixed overhead with the weight read and cannot")
    print("be split with one model, so it bounds efficiency rather than")
    print("measuring it. Do not quote it as a bandwidth figure.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
