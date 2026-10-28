"""
Tests for the deployment verifier.

No network. `verify_one` takes its fetcher as an argument precisely so these
can hand it a function instead of a server -- a test suite that reaches
production is a test suite that fails when the wifi does, and one that fails
for a reason unrelated to the code is one people learn to re-run rather than
read.

What is actually under test is the part that was wrong when this check was
done by hand: which files it decides to look at, and whether it tells a stale
upload apart from one that never happened.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import importlib.util
import re
import sys
import urllib.error
from pathlib import Path

import pytest

from ai_bunker.adopt import site_root

ROOT = Path(__file__).resolve().parent.parent


#: The tree the byte-comparing tests read from, set by the `vd` fixture. Real
#: when the site is on this machine, synthetic otherwise.
_ROOT: Path | None = None


def _site() -> Path:
    """Whatever tree the current test is reading bytes from."""
    if _ROOT is not None:
        return _ROOT
    root = site_root()
    if root is None:  # pragma: no cover - the `vd` fixture always sets _ROOT
        pytest.skip("the site is not on this machine (set AI_BUNKER_SITE)")
    return root


#: For the five tests that need the *real* tree, because they import
#: `publish.py` out of it and compare against its own `shipped()` and `BASE`.
#: There is no honest synthetic version of "the list this project would
#: upload": a fabricated one would verify this test file's idea of the site.
real_site = pytest.mark.skipif(
    site_root() is None, reason="the real site tree is not on this machine"
)


def _load():
    """Import the script by path; `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location(
        "verify_deployment", ROOT / "scripts" / "verify_deployment.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["verify_deployment"] = module
    spec.loader.exec_module(module)
    return module


# Function-scoped: it needs `tmp_path` and `monkeypatch`, and loading the
# module is one `importlib` call on a single file.
@pytest.fixture
def vd(tmp_path, monkeypatch):
    """The verifier, with a tree to read bytes from.

    It used to skip the whole module when the site was absent, and that was
    far too blunt: **twenty-three of these twenty-eight tests need bytes, not
    this project's pages.** Four verdicts, cache-busting, retry-on-transport,
    the origin re-check, the exit codes -- none of that is about `index.html`
    in particular, and all of it stopped running in continuous integration
    when the site moved out of the repository. That script's subtlest
    behaviour is the Varnish re-check, which exists because its absence sent
    the maintainer to re-upload a file twice for nothing; leaving it untested
    is the worst place to lose coverage.

    So: the real tree when it is here, and a synthetic one with the three
    files these tests actually read when it is not.
    """
    module = _load()
    root = site_root()
    if root is None:
        root = tmp_path / "site"
        (root / "js").mkdir(parents=True)
        # A four-digit run, because one test swaps it to prove that equal
        # byte lengths are still compared by hash.
        (root / "index.html").write_bytes(b"<!doctype html>\n<title>site 1071</title>\n")
        # Carries a version string because one test simulates a stale edge by
        # swapping `0.2` for `0.1`: a fixture has to contain whatever the
        # tests perturb, or it reports "identical" and proves nothing.
        (root / "llms.txt").write_bytes(b"# llms.txt\nversion: 0.2.0\n")
        (root / "js" / "theme.js").write_bytes(b"// theme\n")
        monkeypatch.setattr(module, "WEB", root)
    monkeypatch.setitem(globals(), "_ROOT", root)
    return module


# ---------------------------------------------------------------------------
# What it looks at. This is the half that was wrong by hand.
# ---------------------------------------------------------------------------


@real_site
def test_the_file_list_is_the_one_publish_would_upload(vd):
    """Reusing `publish.shipped()` rather than globbing here is the whole
    design, and this is the assertion that keeps it honest.

    The hand check that prompted this script filtered by extension and was
    wrong in both directions. It **missed** the served JavaScript and the six
    web fonts -- named below so they cannot be lost again by a future change
    to how the list is built. And it **included** build-time files: `_shell/`
    partials, the Tailwind input, the favicon source sizes and the publish
    scripts themselves, none of which are served, so asking production for
    them would report four-oh-fours as missing uploads.

    Two smaller properties ride along because they are preconditions for the
    rest of this file. Every listed path exists locally, since `verify_one`
    reads the local file before asking the network and a path that does not
    exist would be a crash rather than a verdict. And the base URL comes from
    `publish` with no trailing slash, which would otherwise build `//path`.
    """
    sys.path.insert(0, str(_site()))
    import publish

    paths = vd.shipped_files()
    assert paths == [str(p.relative_to(publish.HERE)) for p in publish.shipped()]

    assert "js/theme.js" in paths
    assert "js/nav.js" in paths
    assert len([p for p in paths if p.endswith(".woff2")]) == 6

    assert not [p for p in paths if p.startswith("_shell")]
    assert not [p for p in paths if p.endswith("tailwind-input.css")]
    assert not [p for p in paths if p in {"favicon-16.png", "favicon-32.png", "favicon-48.png"}]
    assert not [p for p in paths if p.endswith(".py")]

    for path in paths:
        assert (_site() / path).is_file(), path

    assert vd.base_url() == publish.BASE.rstrip("/")
    assert not vd.base_url().endswith("/"), "a trailing slash would build //path"


# ---------------------------------------------------------------------------
# The four verdicts, and why they are four rather than two.
# ---------------------------------------------------------------------------


def test_a_comparison_produces_one_of_four_verdicts(vd, monkeypatch):
    """Four rather than two, and the extra two are the ones worth having.

    **identical** and **differs** are the obvious pair. `missing` is separate
    because a 404 is an upload that never happened rather than one that went
    stale, and **unreachable** is separate because a refused connection or a
    timeout means the check did not happen at all -- calling that "missing"
    blames the deployment for the network, which is exactly the wrong
    conclusion to reach at three in the morning.

    The third case here is the first real drift this script caught and the
    reason it hashes rather than compares sizes: a quoted test count went from
    1071 to 1093 -- four characters either way -- so five pages differed at
    *identical* byte lengths. Comparing lengths would have called them the
    same, which is the one failure mode a deployment checker cannot have.
    """
    # The two unreachable cases below retry, and the pause between attempts
    # is somebody else's behaviour -- `RETRY_PAUSE` is exercised where the
    # retry itself is. Waiting it out here buys four seconds of nothing.
    monkeypatch.setattr(vd, "RETRY_PAUSE", 0)
    local = (_site() / "index.html").read_bytes()

    same = vd.verify_one("index.html", "https://example.test", lambda _url: (200, local))
    assert same.verdict == "identical"
    assert same.ok

    stale = vd.verify_one("index.html", "https://example.test", lambda _url: (200, b"old"))
    assert stale.verdict == "differs"
    assert not stale.ok
    assert "bytes local" in stale.detail

    # Any four-digit run, not the count of the day: writing `1071` here would
    # make this pass only until the next test was added, which is the drift it
    # exists to catch, one layer up.
    digits = re.search(rb"\d{4}", local)
    assert digits, "the page no longer quotes a four-digit figure; rework this test"
    swapped = local[: digits.start()] + b"9999" + local[digits.end() :]
    assert len(swapped) == len(local), "the premise: same length, different bytes"
    assert swapped != local
    same_length = vd.verify_one("index.html", "https://example.test", lambda _url: (200, swapped))
    assert same_length.verdict == "differs"
    # Reported by hash, because "28,384 bytes local, 28,384 live" reads as a
    # bug in the script rather than as a stale upload.
    assert "same length" in same_length.detail
    assert "bytes local" not in same_length.detail

    gone = vd.verify_one("index.html", "https://example.test", lambda _url: (404, b""))
    assert gone.verdict == "missing"
    assert "404" in gone.detail

    def refuse(_url):
        raise urllib.error.URLError("connection refused")

    refused = vd.verify_one("index.html", "https://example.test", refuse)
    assert refused.verdict == "unreachable"
    assert refused.verdict != "missing"

    def stall(_url):
        raise TimeoutError("timed out")

    assert vd.verify_one("index.html", "https://example.test", stall).verdict == "unreachable"


def test_a_timeout_is_retried_and_a_status_is_not(vd, monkeypatch):
    """Measured, not guessed. Asking for `no-cache` makes every page an origin
    hit, and against this site that was 25s cold against 2-4s warm -- so the
    first version of this script reported all eight pages unreachable on a
    site that was serving them fine. The cold hit is the slow one and the
    retry is the one that lands.

    It gives up after `RETRIES`, or a site that is genuinely down would be
    retried forever. And a status is an answer: asking again does not change
    a 404, so retrying every missing file would multiply the slowest case --
    a tree that was never uploaded -- by the retry count, for no information.

    The URL it asks for is checked here too, because every assertion above is
    worthless if the script is fetching the wrong path.
    """
    monkeypatch.setattr(vd, "RETRY_PAUSE", 0)
    body = (_site() / "index.html").read_bytes()

    calls: list[str] = []

    def slow_first(url):
        calls.append(url)
        if len(calls) == 1:
            raise TimeoutError("the read operation timed out")
        return 200, body

    assert vd.verify_one("index.html", "https://example.test", slow_first).verdict == "identical"
    assert len(calls) == 2

    failures: list[str] = []

    def always_fail(url):
        failures.append(url)
        raise TimeoutError("timed out")

    assert vd.verify_one("index.html", "https://example.test", always_fail).verdict == "unreachable"
    assert len(failures) == vd.RETRIES + 1

    statuses: list[str] = []

    def not_found(url):
        statuses.append(url)
        return 404, b""

    assert vd.verify_one("index.html", "https://example.test", not_found).verdict == "missing"
    assert len(statuses) == 1

    seen: list[str] = []

    def record(url):
        seen.append(url)
        return 200, (_site() / "js" / "theme.js").read_bytes()

    vd.verify_one("js/theme.js", "https://example.test/ai-bunker", record)
    assert seen == ["https://example.test/ai-bunker/js/theme.js"]


# ---------------------------------------------------------------------------
# The exit code, which is the only part a caller can act on.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("verdict", ["differs", "missing", "unreachable"])
def test_the_exit_code_is_the_verdict_and_the_report_says_why(vd, verdict, capsys):
    """The exit code is the only part a caller can act on, so it carries the
    whole answer: zero when production matches the repository, non-zero on any
    of the three ways it can fail to. A check that reports a failure and exits
    zero is not a check -- the same reason `ai-bunker budget --gate` makes the
    verdict the exit code.

    What is printed alongside it has to be usable. The **drifted file is
    named**. The **limit is stated**: this cannot enumerate the server, so it
    cannot see a superseded file left behind by an earlier upload, and
    somebody reading a failure needs to know the check is one-directional
    rather than read it as a clean bill. `--quiet` prints the drift and not
    the agreement, which is what makes it usable from another script. And the
    summary counts every verdict, because "3 file(s)" with no breakdown is a
    number nobody can act on.
    """
    assert vd.report([vd.Result("index.html", "identical")], "https://example.test") == 0
    assert "production matches the repository" in capsys.readouterr().out

    drifted = [vd.Result("index.html", "identical"), vd.Result("start.html", verdict, "detail")]
    assert vd.report(drifted, "https://example.test") == 1
    out = capsys.readouterr().out
    assert "start.html" in out
    assert "cannot see files on the server" in out

    vd.report(drifted, "https://example.test", quiet=True)
    quiet = capsys.readouterr().out
    assert "start.html" in quiet
    assert "identical    index.html" not in quiet

    vd.report(
        [
            vd.Result("a.html", "identical"),
            vd.Result("b.html", "differs", "x"),
            vd.Result("c.html", "missing", "HTTP 404"),
        ],
        "https://example.test",
        quiet=True,
    )
    counted = capsys.readouterr().out
    assert "3 file(s)" in counted
    for expected in ("1 differs", "1 identical", "1 missing"):
        assert expected in counted


# ---------------------------------------------------------------------------
# The request itself.
# ---------------------------------------------------------------------------


def test_the_request_refuses_a_cached_answer(vd):
    """This site was bitten once by `max-age=604800` without revalidation --
    the reason `dashboard.png` had to be renamed rather than replaced. A
    verifier that accepts a cached body reports success about bytes nobody is
    serving any more.
    """
    source = (ROOT / "scripts" / "verify_deployment.py").read_text(encoding="utf-8")
    assert '"Cache-Control": "no-cache"' in source
    # Unencoded, so the comparison is on the bytes rather than on whatever the
    # transfer layer decided to do with them.
    assert '"Accept-Encoding": "identity"' in source


# ---------------------------------------------------------------------------
# A cache in front of the origin. Found on the real site, the hard way.
# ---------------------------------------------------------------------------


def test_a_stale_cache_is_told_apart_from_a_failed_upload(vd, monkeypatch):
    """The false positive this verdict exists for, reproduced -- and the three
    ways it must not fire.

    `deraison.ai` sits behind Varnish, which ignores a client's
    `Cache-Control` by default, so `no-cache` is a hint and not a guarantee.
    The first version of this script reported `llms.txt` as a stale upload
    immediately after a correct one: right at the origin, 19 minutes old at
    the edge. Telling an operator to re-upload a file they just uploaded
    correctly is how a checker teaches people to ignore it.

    It must not fire on **real drift**: a cache can serve content that is too
    old, it cannot invent content that is too new, so when the origin
    disagrees too it is a genuine stale upload. It must not fire when the
    origin fetch **failed**, because then nothing was learned and the mismatch
    stands. And the origin is only consulted **on a mismatch**, or an ordinary
    run doubles its requests and litters the cache with an entry per file per
    run.
    """
    monkeypatch.setattr(vd, "RETRY_PAUSE", 0)
    local = (_site() / "llms.txt").read_bytes()

    seen: list[str] = []

    def cached_then_origin(url):
        seen.append(url)
        # The edge answers the plain URL with yesterday's copy; the query
        # string changes the cache key and reaches the origin.
        return (200, local) if "ai-bunker-verify=" in url else (200, local.replace(b"0.2", b"0.1"))

    stale = vd.verify_one("llms.txt", "https://example.test", cached_then_origin)
    assert stale.verdict == "edge-stale"
    assert stale.ok, "the upload was correct; only the cache is behind"
    assert len(seen) == 2, "the origin must be consulted before drift is reported"
    assert "ai-bunker-verify=" in seen[1]

    real = vd.verify_one("llms.txt", "https://example.test", lambda _url: (200, b"genuinely old"))
    assert real.verdict == "differs"
    assert not real.ok

    def edge_then_nothing(url):
        if "ai-bunker-verify=" in url:
            raise TimeoutError("timed out")
        return 200, b"old bytes"

    unknown = vd.verify_one("llms.txt", "https://example.test", edge_then_nothing)
    assert unknown.verdict == "differs", "a failed origin check must not excuse drift"

    agreed: list[str] = []

    def agree(url):
        agreed.append(url)
        return 200, local

    assert vd.verify_one("llms.txt", "https://example.test", agree).verdict == "identical"
    assert len(agreed) == 1
    assert "ai-bunker-verify=" not in agreed[0]

    # The busting key keeps the path and is unique per call: a repeated key
    # would be cached exactly like the original URL and prove nothing.
    url = "https://example.test/ai-bunker/llms.txt"
    first, second = vd.bust(url), vd.bust(url)
    assert first.startswith(url + "?ai-bunker-verify=")
    assert first != second
    assert vd.bust(url + "?x=1").startswith(url + "?x=1&ai-bunker-verify=")


def test_edge_stale_alone_exits_zero_and_beside_real_drift_does_not(vd, capsys):
    """The exit code is what a script acts on, and re-uploading is exactly the
    wrong action for a cache that is merely behind -- so a run whose only
    finding is `edge-stale` succeeds and says the upload was correct. One
    genuine drift alongside it and the run fails, telling the operator to
    re-upload the tree, because the cache verdict must never mask the other.
    """
    stale_only = [vd.Result("llms.txt", "edge-stale", "correct at the origin")]
    assert vd.report(stale_only, "https://example.test") == 0
    out = capsys.readouterr().out
    assert "EDGE-STALE" in out
    assert "the upload is correct" in out

    with_drift = [*stale_only, vd.Result("index.html", "differs", "x")]
    assert vd.report(with_drift, "https://example.test") == 1
    out = capsys.readouterr().out
    assert "EDGE-STALE" in out
    assert "re-upload the tree" in out
