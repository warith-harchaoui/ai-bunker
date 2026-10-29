#!/usr/bin/env python3
"""Refuse a lane that has quietly grown a deep-learning stack.

Why this exists
---------------
ai-bunker is a proxy. It counts tokens, screens commands, publishes a charter
and sizes machines; it never loads a model. So `torch`, `transformers` and
`diffusers` have no business in its environment, and if one of them appears it
is because a dependency started asking for it -- which is a decision somebody
should make deliberately rather than discover as a lane that grew by gigabytes.

It replaces a workaround rather than adding one. Continuous integration used to
pre-install the processor-only build of torch from PyTorch's own index, with a
comment calling the line "a no-op while the published helper has no torch in
its base dependencies". It was not a no-op: ``pip install torch`` installs
torch whether or not anything wants it. Every leg downloaded a 196-megabyte
wheel and spent twenty-one seconds unpacking it, for nothing.

The reason behind the old line still stands, so it is kept as a check. The
Linux torch wheel on the package index is the build for NVIDIA's Compute
Unified Device Architecture -- gigabytes of ``nvidia-*`` payload for a runner
with no graphics processor. This fails the day that arrives, loudly, naming
the two ways out.

    python scripts/no_heavy_stack.py

Exit status is 0 when the environment is clean and 1 when it is not, so it can
be run as a gate. It is run twice in the lane: once after the ordinary install,
and again after the text-to-image contract step swaps the provider for its
development head, because that is exactly where a new extra would slip in.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import importlib.util
import sys

#: Packages that mean "something here intends to run a model". Deliberately
#: short: a long list of near-misses turns into a list nobody maintains, and
#: these three are what the suite's upstreams would actually pull in.
HEAVY = ("torch", "transformers", "diffusers")

ADVICE = """\
{found} was pulled into this lane. Nothing here loads a model, so either drop
the dependency that asks for it, or pre-install the processor-only build first:

  pip install --index-url https://download.pytorch.org/whl/cpu torch

(--index-url, not --extra-index-url: with two indexes offering the same
version, which one pip picks is not a documented guarantee.)"""


def heavy_imports() -> list[str]:
    """Which of :data:`HEAVY` are importable here.

    ``find_spec`` rather than ``import``: the question is whether the wheel is
    installed, and importing torch to find out would cost most of what the
    check exists to avoid.
    """
    return [name for name in HEAVY if importlib.util.find_spec(name)]


def main() -> int:
    found = heavy_imports()
    if found:
        print(ADVICE.format(found=", ".join(found)), file=sys.stderr)
        return 1
    print(f"no deep-learning stack in this environment ({', '.join(HEAVY)} absent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
