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

Requests are sent with `Cache-Control: no-cache` and `Accept-Encoding:
identity`, both deliberately. This site has already been bitten once by
`max-age=604800` without revalidation -- that is why `dashboard.png` had to be
renamed rather than replaced -- and a verifier that accepts a cached answer
reports success about bytes nobody is serving any more. Asking for an
unencoded body keeps the comparison on the bytes themselves rather than on
whatever the transfer layer decided to do with them.

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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

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
    #: ``identical``, ``differs``, ``missing`` or ``unreachable``.
    verdict: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.verdict == "identical"


def shipped_files() -> list[str]:
    """The paths `publish.py` would upload, relative to the site root."""
    sys.path.insert(0, str(WEB))
    import publish

    return [str(p.relative_to(publish.HERE)) for p in publish.shipped()]


def base_url() -> str:
    """Where `publish.py` says the site lives."""
    sys.path.insert(0, str(WEB))
    import publish

    return str(publish.BASE).rstrip("/")


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

    Non-zero on any drift. A check that reports a failure and exits zero is not
    a check -- the same reason `ai-bunker budget --gate` makes the verdict the
    exit code.
    """
    drift = [r for r in results if not r.ok]

    if not quiet:
        for result in results:
            if result.ok:
                print(f"  identical    {result.path}")

    for result in drift:
        print(f"  {result.verdict.upper():<12} {result.path}  ({result.detail})")

    counts = {v: sum(1 for r in results if r.verdict == v) for v in {r.verdict for r in results}}
    summary = ", ".join(f"{n} {verdict}" for verdict, n in sorted(counts.items()))
    print(f"\n{len(results)} file(s) at {base}: {summary}")

    if not drift:
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

    base = (args.base_url or base_url()).rstrip("/")
    paths = shipped_files()
    if not paths:
        print("publish.py lists nothing to ship; check web/ is intact")
        return 1

    return report(verify(paths, base), base, quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
