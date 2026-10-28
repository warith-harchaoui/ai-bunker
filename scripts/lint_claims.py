#!/usr/bin/env python3
"""
Hold one load-bearing claim to one answer, across every file that states it.

Why
---
`scripts/sync_counts.py` rewrites every quoted **figure** from the repository
that produced it, and `tests/test_site.py` refuses to pass when one has
drifted. Nothing did that for **claims**, and the asymmetry is indefensible: a
stale test count is cosmetic, a stale security claim is the product lying about
itself.

The cost was paid rather than theorised. "Command screening does not apply to a
stream" lived in eight places -- both READMEs, `llms.txt`, the changelog,
`CONTRIBUTING.md`, two page sources and a docstring. When the limitation was
closed, seven were corrected and the two site pages were missed, so the
published website advertised a hole that no longer existed until a later sweep
caught it. Three more of the same shape turned up the same week: a docstring
saying the dashboard was untranslated, a warning saying an estimate could not
gate while the gateway refused requests on it, and a module docstring
advertising `GET` against a `POST` route.

Every one of those is a sentence that was true and stopped being true, with
nothing to notice.

How
---
A claim is a **phrase that must not appear**, a **phrase that must**, or both,
over a named set of files. That is deliberately cruder than parsing prose: a
check that tries to understand sentences fails in ways nobody can debug, while
a check on a literal phrase fails in exactly one way and says which file.

    python3 scripts/lint_claims.py            # report
    python3 scripts/lint_claims.py --list     # what is being guarded, and why

Registering a claim is the price of closing a limitation, and it is a line in
`CLAIMS` below. The rule for what belongs here: a sentence a reader would act
on, which is now false. Not style, not wording, not anything a rewrite should
have to negotiate with.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ai_bunker.adopt import site_file

ROOT = Path(__file__).resolve().parent.parent

#: Everywhere a claim about behaviour can be stated. The site's built pages are
#: included as well as their sources: a page source can be corrected and the
#: `.html` left stale, which is a separate failure with the same symptom.
#:
#: `CHANGELOG.md` is deliberately absent, for the same reason it is absent from
#: `sync_counts.SOURCES`: it records what was true on the day it was written.
#: Rewriting a released entry would turn a record into a false statement, which
#: is a worse failure than the one this script exists to catch.
PROSE = (
    "README.md",
    "LISEZMOI.md",
    "CONTRIBUTING.md",
    "docs/RULES.md",
    "docs/REGLES.md",
    "docs/SIZING.md",
    "EXAMPLES.md",
    "EXEMPLES.md",
    "LANDSCAPE.md",
    "PAYSAGE.md",
    "clients/README.md",
    "web/DEPLOY.md",
    "web/llms.txt",
)

SITE = (
    "web/index.html",
    "web/start.html",
    "web/landscape.html",
    "web/sizing.html",
    "web/fr/index.html",
    "web/fr/start.html",
    "web/fr/landscape.html",
    "web/fr/sizing.html",
    "web/pages/index.en.py",
    "web/pages/index.fr.py",
    "web/pages/start.en.py",
    "web/pages/start.fr.py",
)

#: `required_somewhere` is satisfied by a single match anywhere in `files`, so
#: a claim that must hold in *both* languages has to be registered twice, over
#: the halves. The alternative -- one claim naming an English phrase and a
#: French one -- passes while either half is missing, which is exactly the
#: failure mode this file exists to stop.
#:
#: And the halves are the **built pages only**, not their sources. The first
#: version of this included `pages/*.py`, and deleting the sentence from the
#: shipped `.html` left it in the source, satisfied the claim, and reported
#: green -- a guard that passes while the published page has lost the thing it
#: guards. Checking the artefact the reader is served covers both directions,
#: because a source that drops the sentence drops it from the page at the next
#: build.
_BUILT = tuple(f for f in SITE if f.endswith(".html"))
SITE_EN = tuple(f for f in _BUILT if "/fr/" not in f)
SITE_FR = tuple(f for f in _BUILT if "/fr/" in f)

CODE = tuple(f"ai_bunker/{p.name}" for p in sorted((ROOT / "ai_bunker").glob("*.py")))


@dataclass(frozen=True)
class Claim:
    """One fact, and the phrases that would contradict it."""

    name: str
    #: Why this one is registered: what went wrong, or would.
    because: str
    #: Phrases that must appear nowhere in ``files``.
    forbidden: tuple[str, ...] = ()
    #: Phrases of which at least one must appear somewhere in ``files``.
    required_somewhere: tuple[str, ...] = ()
    files: tuple[str, ...] = field(default_factory=lambda: PROSE + SITE + CODE)


CLAIMS: tuple[Claim, ...] = (
    Claim(
        name="streaming-is-screened",
        because=(
            "The limitation was closed in 0.2.0 and eight files stated it. Two "
            "were missed, so the published site advertised a hole that no "
            "longer existed. This is the claim that produced this script."
        ),
        forbidden=(
            "Command screening does not apply",
            "command screening does not apply",
            "Le filtrage des commandes ne\n  s'applique pas",
            "filtrage des commandes ne s'applique pas",
            "screening is **not** applied to a stream",
            "screening is not applied to a stream",
        ),
        required_somewhere=(
            "screening applies to streamed",
            "applies to\n          streamed completions",
            "s'applique au streaming",
        ),
    ),
    Claim(
        name="the-estimate-gates",
        because=(
            "The budget warned that a ratio count 'cannot gate a deployment' "
            "while the gateway returned 413 on its verdict. A module whose "
            "subject is honesty about measurement cannot contradict its own "
            "code."
        ),
        # The whole sentence, not the fragment. `budget.py` quotes the old
        # wording in the comment that explains the fix -- "It said 'cannot
        # gate a deployment', and it gates" -- which is a reference to the
        # claim and not the claim. A phrase too short to tell those apart
        # flags the explanation along with the error.
        forbidden=("This figure cannot gate a deployment",),
    ),
    Claim(
        name="no-model-hub-at-runtime",
        because=(
            "Counting must not depend on an outbound call to a third party: "
            "the gateway's whole claim is that nothing leaves the local "
            "network. An intermediate version resolved a Hugging Face "
            "repository id, which worked and was wrong."
        ),
        forbidden=("from_pretrained",),
        files=CODE,
    ),
    Claim(
        name="the-model-choice-is-delegated",
        because=(
            "Both READMEs said 'ai-bunker describes its needs in a brief and "
            "lets the helper choose; it never hardcodes a model name' while "
            "six literals in `sizing.py` and `cli.py` did exactly that, and "
            "`best_engine_ai_helper` was a declared dependency with no import "
            "anywhere in the package. The sentence is true now; this is what "
            "notices if either half drifts back."
        ),
        required_somewhere=("best_engine_ai_helper",),
        files=("ai_bunker/engine.py", "ai_bunker/sizing.py"),
    ),
    Claim(
        name="the-image-slot-is-delegated-whole",
        because=(
            "Both READMEs say this project keeps no text-to-image catalogue "
            "and asks the helper for the entries as well as the order. The "
            "temptation when the helper is slow to install, or when one entry "
            "looks wrong, is to paste a model name into `engine.py` -- which "
            "is exactly how the three language slots acquired six literals "
            "the prose spent several releases denying."
        ),
        required_somewhere=("imagine_rank",),
        files=("ai_bunker/engine.py",),
    ),
    Claim(
        name="the-image-route-refuses-rather-than-falls-through",
        because=(
            "Both READMEs say an unconfigured image route answers 501 naming "
            "the line to write, rather than handing the request to a language "
            "engine with no such endpoint. Deleting the guard would restore "
            "the default fall-through and turn a sentence about the "
            "deployment back into a 502 about a socket, with nothing in the "
            "prose changing to say so."
        ),
        required_somewhere=("image_route_not_configured",),
        files=("ai_bunker/gateway.py",),
    ),
    Claim(
        name="the-dashboard-is-translated",
        because=(
            "`i18n.py` listed the dashboard under 'what is deliberately NOT "
            "translated' for three sessions after it was translated, sending "
            "the next reader to look for work already finished."
        ),
        forbidden=("**The dashboard**, for now",),
        files=CODE,
    ),
    Claim(
        name="the-site-publishes-its-open-limitations-en",
        because=(
            "The README stated five limitations and the website stated none, for "
            "every release so far. That is this script's own defect running in "
            "the other direction: the site once advertised a hole that no longer "
            "existed, and it then advertised no holes that did. The reader "
            "deciding whether to deploy reads the site, not the README."
        ),
        # Flipped when the limitation was closed. The phrase this used to
        # require -- "bounded rather than removed" -- became false the moment
        # `_prepare` moved to a worker thread, and this guard would have held
        # the site to stating it: the same shape as the defect that produced
        # this file, where the site advertised a hole that no longer existed.
        # A `required_somewhere` claim is a claim about *today*, so closing a
        # limitation means editing the claim, not only the prose.
        forbidden=("bounded rather than removed", "is not done"),
        required_somewhere=("availability fix paid for with a data race",),
        files=SITE_EN,
    ),
    Claim(
        name="the-site-publishes-its-open-limitations-fr",
        because=(
            "The French half of the claim above. Registered separately because "
            "one phrase matching anywhere would let either language lose its "
            "limitations silently -- and the French site is not a translation "
            "nobody reads, it is the half this project's author writes in."
        ),
        forbidden=("C'est born\u00e9, pas supprim\u00e9", "il n'est pas fait"),
        required_somewhere=("pay\u00e9 par une course de donn\u00e9es n'est pas un correctif",),
        files=SITE_FR,
    ),
    Claim(
        name="personal-data-is-out-of-scope-and-said-so",
        because=(
            "The 27 rules cover credentials, injection, shell commands and "
            "tool descriptions, and nothing else. Personal data appeared in "
            "this repository exactly once -- in LANDSCAPE.md, describing what "
            "*other* projects do better -- while the README talks about "
            "decision logs and audit trails. A reader can hear 'governance' "
            "and assume coverage that does not exist, and this project's own "
            "rule is that a limitation nobody publishes is one somebody "
            "discovers."
        ),
        required_somewhere=("Personal data is not",),
        files=SITE_EN,
    ),
    Claim(
        name="personal-data-is-out-of-scope-and-said-so-fr",
        because="The French half of the claim above, for the reason the other pairs are split.",
        required_somewhere=("Les donn\u00e9es personnelles ne",),
        files=SITE_FR,
    ),
    Claim(
        name="the-budget-endpoint-is-a-post",
        because=(
            "`gateway.py`'s module docstring advertised `GET /v1/budget` "
            "against a `POST` route -- found by an integration test, not by a "
            "reader."
        ),
        forbidden=("``GET /v1/budget``",),
        files=CODE,
    ),
)


#: ``~~like this~~``: a claim a document withdraws in front of its reader.
_STRUCK = re.compile(r"~~.+?~~", re.DOTALL)


def _read(relative: str) -> str | None:
    """A file's text, with withdrawn claims removed.

    A struck-through sentence is not a stale claim, it is a record of one --
    "~~Command screening does not apply to a stream.~~ **Closed in 0.2.0.**"
    tells a reader more than silence would, and the strikethrough is the
    withdrawal. The first version of this script flagged all three of those
    and had a 100% false-positive rate on its first run, which is how a
    checker teaches people to ignore it.
    """
    path = site_file(relative) if relative.startswith("web/") else ROOT / relative
    if path is None or not path.is_file():
        return None
    return _STRUCK.sub(" ", path.read_text(encoding="utf-8"))


def check() -> list[str]:
    """Every contradiction found, as a line a reader can act on."""
    problems: list[str] = []
    for claim in CLAIMS:
        seen_required = False
        reachable = 0
        for relative in claim.files:
            text = _read(relative)
            if text is None:
                continue
            reachable += 1
            for phrase in claim.forbidden:
                if phrase in text:
                    problems.append(
                        f"{relative}: states {phrase!r}, which contradicts '{claim.name}'"
                    )
            if any(phrase in text for phrase in claim.required_somewhere):
                seen_required = True
        # A claim whose files are all absent is not a stale claim, it is an
        # unaskable question. The site left this repository, so the two claims
        # over its built pages have nothing to read on a machine that does not
        # carry it -- and reporting "nothing states the current position"
        # there would make the gate permanently red for a reason that is not a
        # defect. The distinction matters: a claim with *some* files present
        # and the phrase missing from all of them is still a failure.
        if claim.required_somewhere and not seen_required and reachable:
            problems.append(
                f"'{claim.name}': nothing states the current position. One of "
                f"{list(claim.required_somewhere)} must appear somewhere -- a "
                "claim nobody makes is one a reader cannot check."
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("Why")[0].strip())
    parser.add_argument("--list", action="store_true", help="Print what is guarded, and why.")
    args = parser.parse_args(argv)

    if args.list:
        for claim in CLAIMS:
            print(f"  {claim.name}")
            print(f"      {claim.because}")
            print(f"      across {len(claim.files)} file(s)")
        return 0

    problems = check()
    for line in problems:
        print(f"  {line}")
    if problems:
        print(f"\n{len(problems)} stale claim(s). A sentence that stopped being true.")
        return 1
    print(f"every one of the {len(CLAIMS)} guarded claims is stated consistently")
    return 0


if __name__ == "__main__":
    sys.exit(main())
