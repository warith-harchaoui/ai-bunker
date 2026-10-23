#!/usr/bin/env python3
"""
Compare the repository against what the server is actually serving.

Why
---
Three checks already guard this site and none of them look at production.
`tests/test_site.py` holds the repository's pages to the repository's own
figures. `web/publish.py --check` holds the tree to its internal consistency --
every link resolves, nothing unreferenced would be uploaded. Both pass happily
while the deployed site is a month old, because the site is uploaded by hand
over SFTP and nothing closes the loop between "the tree is right" and "the tree
is up there".

This closes it, and it is the only check here that can tell you the upload did
not happen.

    python3 scripts/verify_deployment.py           # verify against production
    python3 scripts/verify_deployment.py --quiet   # only the drift
    python3 scripts/verify_deployment.py --base-url http://localhost:8080

What it reuses, and why that is the point
-----------------------------------------
The file list comes from `web/publish.py`'s own `shipped()`, and the base URL
from its `BASE`. Not from a glob written here.

That is not tidiness, it is the bug this script exists to avoid repeating. The
hand check that prompted it was written with an extension filter -- `.html`,
`.css`, `.txt`, `.xml`, `.png`, `.svg` -- and it was wrong in both directions:
it missed `js/theme.js`, `js/nav.js` and six `.woff2` fonts, which are served,
and it included five `_shell/` partials, a Tailwind input file and three
favicon source sizes, which are not. It reported "39 files identical" about a
set that shared 31 members with reality. A verifier with its own idea of what
ships verifies its own idea.

What it cannot do
-----------------
**It cannot find files on the server that are not in the repository.** HTTP
offers no way to list a directory, so a superseded image left behind by an
earlier upload is invisible here -- `img/dashboard.png` was found by
remembering it existed, which does not scale and is not a check. The honest
statement of scope is: everything the repository declares is live, reachable,
and byte-for-byte what the repository holds.

Caches, and why asking nicely is not enough
-------------------------------------------
Requests carry `Cache-Control: no-cache` and `Accept-Encoding: identity`. The
second keeps the comparison on the bytes themselves. The first is a **hint,
and this site proved it is only a hint**: `deraison.ai` sits behind Varnish,
which ignores a client's `Cache-Control` by default -- deliberately, because
honouring it would let anyone force origin traffic at will.

So the first version of this script reported `llms.txt` as a stale upload
immediately after a correct one. The file was right at the origin and the edge
was serving a copy 19 minutes old. Telling an operator to re-upload a file
they had just uploaded correctly is the failure mode that teaches people to
ignore a checker, which is the same reason `global.generic_secret` carries an
allow-list for the word `example`.

The fix uses the one thing a cache cannot do. **A cache can serve content that
is too old; it cannot invent content that is too new.** So a mismatch is never
reported on its own: it is re-fetched with a unique query string, which changes
the cache key and reaches the origin. If the origin agrees with the repository,
the upload was fine and the edge is merely behind -- a different fact, with a
different name (`edge-stale`) and a different exit code.

The busting fetch runs **only** on a mismatch, so an ordinary verification is
still cache-friendly and does not litter the cache with one entry per file per
run.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ai_bunker.adopt import site_root

ROOT = Path(__file__).resolve().parent.parent

#: The site's tree, which carries `publish.py` and therefore the file list
#: this script compares against production. Without it there is no list, so
#: this script says so and stops -- it cannot guess what the server should
#: hold.
WEB = site_root()

#: Polite but identifiable. A request with urllib's default agent is refused by
#: enough front-ends that a 403 here would read as a missing file.
AGENT = "ai-bunker-verify-deployment/1.0 (+https://deraison.ai/ai-bunker)"

#: Concurrency, timeout and retries, all three set from measurement rather than
#: taste -- and the measurement is a consequence of asking for `no-cache`.
#:
#: Refusing a cached answer means every page is an origin hit. Timed against
#: this site: a static asset answers in 0.1s, a page served from cache in 1.0s,
#: and the same page with `no-cache` in 2-4s warm and **25s cold**. Eight of
#: those at once queued behind each other and blew a 20-second timeout, so the
#: first version of this script reported all eight pages unreachable on a site
#: that was serving them perfectly.
#:
#: Fewer workers so the cold hits do not queue, a timeout above the cold figure
#: with room to spare, and one retry because the cold hit is the slow one -- the
#: second request for the same page was consistently five to ten times faster.
WORKERS = 4
TIMEOUT = 45
RETRIES = 1
RETRY_PAUSE = 2.0


@dataclass(frozen=True)
class Result:
    """One file, and whether production agrees with the repository."""

    path: str
    #: ``identical``, ``edge-stale``, ``differs``, ``missing`` or
    #: ``unreachable``.
    verdict: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        """Whether the upload is correct.

        ``edge-stale`` counts as correct, and that is the judgement call this
        type exists to record. The operator uploaded the right bytes; a cache
        in front of them is serving an older copy and will stop on its own.
        Calling that a failed deployment would be false, and would send someone
        to re-upload a file that is already right.
        """
        return self.verdict in {"identical", "edge-stale"}


class SiteNotHere(RuntimeError):
    """The site's tree is not on this machine, so there is no file list.

    Raised rather than guessed. This script's whole value is that its list
    comes from `publish.py`'s own `shipped()` rather than from a glob written
    here -- a comparison against a list this script invented would report
    "production matches the repository" about files it chose, which is the
    reassuring half of a wrong answer.
    """


def shipped_files() -> list[str]:
    """The paths `publish.py` would upload, relative to the site root."""
    if WEB is None:
        raise SiteNotHere("the site is not on this machine; set AI_BUNKER_SITE to its directory")
    sys.path.insert(0, str(WEB))
    import publish

    return [str(p.relative_to(publish.HERE)) for p in publish.shipped()]


def base_url() -> str:
    """Where `publish.py` says the site lives."""
    if WEB is None:
        raise SiteNotHere("the site is not on this machine; set AI_BUNKER_SITE to its directory")
    sys.path.insert(0, str(WEB))
    import publish

    return str(publish.BASE).rstrip("/")


def bust(url: str) -> str:
    """The same URL with a unique query string, to reach past a cache.

    The query string is part of the cache key, so this is the one request a
    shared cache has to pass through. The value only has to be unlikely to
    repeat within a cache's lifetime; it is not a secret and it is never
    compared.
    """
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}ai-bunker-verify={uuid.uuid4().hex[:12]}"


def _fetch(url: str) -> tuple[int, bytes]:
    """The status and body at ``url``, or a raised `URLError`.

    A 404 is a result rather than an error -- it is the answer when an upload
    was never done -- so it comes back as a status to report. A refused
    connection is not: it means the check itself did not happen, and saying
    "missing" would blame the deployment for the network.
    """
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": AGENT,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Accept-Encoding": "identity",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), b""


def verify_one(path: str, base: str, fetch=_fetch) -> Result:
    """Compare one file. ``fetch`` is injectable so the tests need no network.

    Retried only on a transport failure, never on a status. A 404 is an answer
    and asking again does not change it; a timed-out origin hit is not an
    answer, and the second attempt is the one that lands because the first
    warmed whatever was cold.
    """
    if WEB is None:
        raise SiteNotHere("the site is not on this machine")
    local = (WEB / path).read_bytes()
    url = f"{base}/{path}"

    last = ""
    for attempt in range(RETRIES + 1):
        try:
            status, body = fetch(url)
            break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = str(exc)
            if attempt < RETRIES:
                time.sleep(RETRY_PAUSE)
    else:
        return Result(path, "unreachable", last)

    if status != 200:
        return Result(path, "missing", f"HTTP {status}")

    here, there = hashlib.sha256(local).hexdigest(), hashlib.sha256(body).hexdigest()
    if here == there:
        return Result(path, "identical")

    # A mismatch is never reported on the strength of one request. A cache can
    # serve content that is too old; it cannot invent content that is too new
    # -- so a second fetch that reaches the origin settles which of the two
    # this is. Only on a mismatch, so an ordinary run stays cache-friendly.
    try:
        origin_status, origin_body = fetch(bust(url))
    except (urllib.error.URLError, TimeoutError, OSError):
        origin_status, origin_body = 0, b""
    if origin_status == 200 and hashlib.sha256(origin_body).hexdigest() == here:
        return Result(path, "edge-stale", "correct at the origin, cache serving an older copy")

    # Compared by hash, and reported by hash when the lengths agree -- which
    # they usually do, and that is the point. The first real drift this script
    # caught was a quoted test count going from 1071 to 1093: four characters
    # either way, so five files differed at **identical** byte lengths. A
    # size check would have called them the same, and a report that printed
    # "28,384 bytes local, 28,384 live" would have read as a bug in the script.
    if len(local) == len(body):
        return Result(path, "differs", f"same length, content differs: {here[:8]} vs {there[:8]}")
    return Result(path, "differs", f"{len(local):,} bytes local, {len(body):,} live")


def verify(paths: list[str], base: str, fetch=_fetch) -> list[Result]:
    """Compare every path, concurrently, in the order given."""
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        return list(pool.map(lambda p: verify_one(p, base, fetch), paths))


def report(results: list[Result], base: str, *, quiet: bool = False) -> int:
    """Print the verdict and return the exit code.

    Non-zero on anything the operator has to act on. A check that reports a
    failure and exits zero is not a check -- the same reason
    `ai-bunker budget --gate` makes the verdict the exit code. The corollary
    matters just as much here: a check that reports a failure the operator has
    already fixed is one they learn to ignore, which is why `edge-stale` exits
    zero.
    """
    drift = [r for r in results if not r.ok]
    stale = [r for r in results if r.verdict == "edge-stale"]

    if not quiet:
        for result in results:
            if result.verdict == "identical":
                print(f"  identical    {result.path}")

    for result in stale:
        print(f"  EDGE-STALE   {result.path}  ({result.detail})")

    for result in drift:
        print(f"  {result.verdict.upper():<12} {result.path}  ({result.detail})")

    counts = {v: sum(1 for r in results if r.verdict == v) for v in {r.verdict for r in results}}
    summary = ", ".join(f"{n} {verdict}" for verdict, n in sorted(counts.items()))
    print(f"\n{len(results)} file(s) at {base}: {summary}")

    if not drift:
        if stale:
            print(
                "the upload is correct; a cache in front of it is still serving older\n"
                "copies of the file(s) above, and will stop when they expire"
            )
        else:
            print("production matches the repository")
        return 0

    # Named rather than counted, because the three mean different things to
    # whoever is reading: a differing file is a stale upload, a missing one is
    # an upload that never happened, and an unreachable one is this check
    # failing rather than the deployment.
    if any(r.verdict == "unreachable" for r in drift):
        print("some files could not be checked; this is not a verdict on the deployment")
    if any(r.verdict == "missing" for r in drift):
        print("missing files were never uploaded, or were uploaded somewhere else")
    if any(r.verdict == "differs" for r in drift):
        print("differing files are a stale upload: re-upload the tree")
    print("\nnote: this cannot see files on the server that the repository does not list")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("Why")[0].strip())
    parser.add_argument(
        "--base-url",
        default="",
        help="Site root to check against. Default: what web/publish.py declares.",
    )
    parser.add_argument("--quiet", action="store_true", help="Print only the drift.")
    args = parser.parse_args(argv)

    try:
        base = (args.base_url or base_url()).rstrip("/")
        paths = shipped_files()
    except SiteNotHere as exc:
        # Exit 0: nothing is wrong with the deployment, this machine simply
        # does not carry the site. A red gate here would be red on every
        # continuous-integration run forever, and a gate that is always red
        # is a gate nobody reads.
        print(f"{exc}")
        return 0
    if not paths:
        print("publish.py lists nothing to ship; check the site tree is intact")
        return 1

    return report(verify(paths, base), base, quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
