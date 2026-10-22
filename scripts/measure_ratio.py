#!/usr/bin/env python3
"""
Measure the characters-per-token ratio the estimate falls back on.

Why this exists
---------------
`budget.CHARS_PER_TOKEN` is the one number in this project that was folklore.
Its comment said "measured on French and English technical prose with a
Mistral-family tokenizer", and that was probably true once, but the
measurement was not reproducible and the figure was a single constant for all
content. In a repository whose one rule is that every claim is a measurement,
that was the wrong place for an unverifiable one.

Measured here, it turns out 4.0 was not merely imprecise, it was
**unsafe**: the true ratio runs from about 2.5 to 4.2 across real content, so
4.0 UNDER-counted on most of it, by up to a third on markup. Under-counting is
the failure this project was founded on -- a client that estimated and sent
40,433 tokens to a 32,768-token server.

And the estimate can refuse a request: `Budget.verdict` is computed whatever
the backend, and the gateway returns 413 on `unusable`. So the constant has to
be chosen so the estimate is never *optimistic*, which means taking the
MINIMUM ratio observed, not the mean.

    python3 scripts/measure_ratio.py            # the table and the verdict
    python3 scripts/measure_ratio.py --check    # fail if the constant is unsafe

`--check` is the part worth automating: it re-measures and exits non-zero if
`CHARS_PER_TOKEN` would under-count any sample. It needs the `tokenizers`
extra and the network, so it is not a continuous-integration gate -- it is
what you run when you change the constant or add a tokenizer family.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

#: Tokenizers to measure against: the families this project names, plus the
#: ones its catalogue recommends. A ratio safe for one vocabulary is not
#: automatically safe for another, so the floor is taken across all of them.
TOKENIZERS = {
    "qwen2.5": "Qwen/Qwen2.5-7B",
    "qwen3-vl": "Qwen/Qwen3-VL-8B-Instruct",
    "devstral": "mistralai/Devstral-Small-2-24B-Instruct-2512",
}

#: Real files from this repository, chosen to span what actually reaches a
#: context window: prose in both languages, source, configuration, markup.
#: Not synthetic text -- the point is the content an agent is handed.
CORPUS = {
    "prose (en)": "README.md",
    "prose (fr)": "LISEZMOI.md",
    "charter (en)": "charter/AGENTS.md",
    "charter (fr)": "charter/AGENTS.fr.md",
    "python": "ai_bunker/rules.py",
    "yaml": "charter/rules/shell.yaml",
    "markdown": "docs/RULES.md",
    "html": "web/index.html",
    "xml": "web/sitemap.xml",
    "gherkin": "features/shell.feature",
    "css": "web/css/app.css",
    "javascript": "web/js/theme.js",
    "plain text": "web/llms.txt",
}


def measure() -> tuple[dict[str, dict[str, float]], float]:
    """Ratios per sample per tokenizer, and the floor across all of them."""
    from tokenizers import Tokenizer

    loaded = {}
    for name, repo in TOKENIZERS.items():
        try:
            loaded[name] = Tokenizer.from_pretrained(repo)
        except Exception as exc:
            print(f"  (skipping {name}: {type(exc).__name__}: {str(exc)[:60]})")
    if not loaded:
        raise SystemExit("no tokenizer could be loaded; check the network")

    table: dict[str, dict[str, float]] = {}
    floor = float("inf")
    for label, relative in CORPUS.items():
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if not text:
            continue
        row = {}
        for name, tokenizer in loaded.items():
            count = len(tokenizer.encode(text).ids)
            if count:
                row[name] = len(text) / count
        if row:
            table[label] = row
            floor = min(floor, min(row.values()))
    return table, floor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("Why")[0].strip())
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if CHARS_PER_TOKEN would under-count any sample.",
    )
    args = parser.parse_args(argv)

    from ai_bunker.budget import CHARS_PER_TOKEN

    table, floor = measure()
    names = sorted({n for row in table.values() for n in row})

    header = f"  {'sample':<14}" + "".join(f"{n:>11}" for n in names) + f"{'min':>8}"
    print(header)
    print("  " + "─" * (len(header) - 2))
    for label, row in table.items():
        cells = "".join(f"{row.get(n, float('nan')):>11.2f}" for n in names)
        print(f"  {label:<14}{cells}{min(row.values()):>8.2f}")

    print()
    print(f"  lowest ratio observed      {floor:.2f} chars/token")
    print(f"  CHARS_PER_TOKEN in use     {CHARS_PER_TOKEN:.2f}")

    # The estimate divides by this constant, so a LARGER constant yields a
    # SMALLER token count. Safety therefore means being at or below the floor.
    if floor < CHARS_PER_TOKEN:
        shortfall = 1 - (floor / CHARS_PER_TOKEN)
        print()
        print(
            f"  UNSAFE: the constant under-counts the worst sample by "
            f"{shortfall:.0%}.\n"
            f"  An estimate can refuse a request, so it must never be "
            f"optimistic.\n"
            f"  Set CHARS_PER_TOKEN to {floor:.2f} or below."
        )
        return 1 if args.check else 0

    # The cost, which is the figure an operator actually feels: the LOOSEST
    # sample is the one over-counted hardest. Reporting headroom against the
    # floor instead would print a reassuring 0% and say nothing.
    loosest = max(max(row.values()) for row in table.values())
    print(
        f"  SAFE: never under-counts.\n"
        f"  Cost: it over-counts the loosest sample by "
        f"{loosest / CHARS_PER_TOKEN - 1:+.0%} "
        f"({loosest:.2f} chars/token measured).\n"
        f"  That is the recoverable direction, and `local` now covers every "
        f"family\n  the catalogue knows, so this path is the rare one."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
