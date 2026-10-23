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
    wrong in both directions: it missed the served JavaScript and fonts, and
    it included build-time partials. A verifier with its own idea of what
    ships verifies its own idea.
    """
    sys.path.insert(0, str(_site()))
    import publish

    assert vd.shipped_files() == [str(p.relative_to(publish.HERE)) for p in publish.shipped()]


@real_site
def test_the_served_javascript_and_fonts_are_checked(vd):
    """The eight files the hand check missed, named so they cannot be lost
    again by a future change to how the list is built."""
    paths = vd.shipped_files()
    assert "js/theme.js" in paths
    assert "js/nav.js" in paths
    assert len([p for p in paths if p.endswith(".woff2")]) == 6


@real_site
def test_build_time_files_are_not_checked(vd):
    """`_shell/` partials, the Tailwind input and the favicon source sizes are
    not served, so asking production for them would report four-oh-fours as
    missing uploads."""
    paths = vd.shipped_files()
    assert not [p for p in paths if p.startswith("_shell")]
    assert not [p for p in paths if p.endswith("tailwind-input.css")]
    assert not [p for p in paths if p in {"favicon-16.png", "favicon-32.png", "favicon-48.png"}]
    assert not [p for p in paths if p.endswith(".py")]


@real_site
def test_every_listed_file_exists_locally(vd):
    """`verify_one` reads the local file before asking the network, so a path
    that does not exist would be a crash rather than a verdict."""
    for path in vd.shipped_files():
        assert (_site() / path).is_file(), path


@real_site
def test_the_base_url_comes_from_publish(vd):
    sys.path.insert(0, str(_site()))
    import publish

    assert vd.base_url() == publish.BASE.rstrip("/")
    assert not vd.base_url().endswith("/"), "a trailing slash would build //path"


# ---------------------------------------------------------------------------
# The four verdicts, and why they are four rather than two.
# ---------------------------------------------------------------------------


def test_matching_bytes_are_identical(vd):
    local = (_site() / "index.html").read_bytes()
    result = vd.verify_one("index.html", "https://example.test", lambda _url: (200, local))
    assert result.verdict == "identical"
    assert result.ok


def test_different_bytes_are_a_stale_upload(vd):
    result = vd.verify_one("index.html", "https://example.test", lambda _url: (200, b"old"))
    assert result.verdict == "differs"
    assert not result.ok
    assert "bytes local" in result.detail


def test_drift_at_the_same_byte_length_is_still_drift(vd):
    """The first real drift this script caught, and the reason it hashes.

    A quoted test count went from 1071 to 1093 -- four characters either way --
    so five pages differed at **identical** byte lengths. Comparing sizes would
    have called them the same, which is the failure mode a deployment checker
    cannot have.
    """
    local = (_site() / "index.html").read_bytes()
    # Any four-digit run, not the count of the day: writing `1071` here would
    # make this test pass only until the next test was added, which is the
    # drift it exists to catch, one layer up.
    digits = re.search(rb"\d{4}", local)
    assert digits, "the page no longer quotes a four-digit figure; rework this test"
    swapped = local[: digits.start()] + b"9999" + local[digits.end() :]
    assert len(swapped) == len(local), "the premise: same length, different bytes"
    assert swapped != local

    result = vd.verify_one("index.html", "https://example.test", lambda _url: (200, swapped))
    assert result.verdict == "differs"
    # Reported by hash, because "28,384 bytes local, 28,384 live" reads as a
    # bug in the script rather than as a stale upload.
    assert "same length" in result.detail
    assert "bytes local" not in result.detail


def test_a_404_is_an_upload_that_never_happened(vd):
    result = vd.verify_one("index.html", "https://example.test", lambda _url: (404, b""))
    assert result.verdict == "missing"
    assert "404" in result.detail


def test_a_network_failure_is_not_a_verdict_on_the_deployment(vd):
    """The distinction that matters when it is three in the morning: a refused
    connection means the check did not happen, and calling that "missing"
    would blame the deployment for the network."""

    def refuse(_url):
        raise urllib.error.URLError("connection refused")

    result = vd.verify_one("index.html", "https://example.test", refuse)
    assert result.verdict == "unreachable"
    assert result.verdict != "missing"


def test_a_timeout_is_unreachable_rather_than_a_crash(vd):
    def stall(_url):
        raise TimeoutError("timed out")

    assert vd.verify_one("index.html", "https://example.test", stall).verdict == "unreachable"


def test_a_transient_timeout_is_retried(vd, monkeypatch):
    """Measured, not guessed. Asking for `no-cache` makes every page an origin
    hit, and against this site that was 25s cold against 2-4s warm -- so the
    first version reported all eight pages unreachable on a site that was
    serving them fine. The cold hit is the slow one, and the retry is the one
    that lands.
    """
    monkeypatch.setattr(vd, "RETRY_PAUSE", 0)
    calls: list[str] = []
    body = (_site() / "index.html").read_bytes()

    def slow_first(url):
        calls.append(url)
        if len(calls) == 1:
            raise TimeoutError("the read operation timed out")
        return 200, body

    assert vd.verify_one("index.html", "https://example.test", slow_first).verdict == "identical"
    assert len(calls) == 2


def test_a_retry_that_also_fails_is_unreachable(vd, monkeypatch):
    monkeypatch.setattr(vd, "RETRY_PAUSE", 0)
    calls: list[str] = []

    def always_fail(url):
        calls.append(url)
        raise TimeoutError("timed out")

    result = vd.verify_one("index.html", "https://example.test", always_fail)
    assert result.verdict == "unreachable"
    assert len(calls) == vd.RETRIES + 1


def test_a_404_is_not_retried(vd, monkeypatch):
    """A status is an answer and asking again does not change it. Retrying
    every missing file would multiply the slowest case -- a tree that was never
    uploaded -- by the retry count for no information."""
    monkeypatch.setattr(vd, "RETRY_PAUSE", 0)
    calls: list[str] = []

    def not_found(url):
        calls.append(url)
        return 404, b""

    assert vd.verify_one("index.html", "https://example.test", not_found).verdict == "missing"
    assert len(calls) == 1


def test_the_url_is_built_from_the_base_and_the_path(vd):
    seen: list[str] = []

    def record(url):
        seen.append(url)
        return 200, (_site() / "js" / "theme.js").read_bytes()

    vd.verify_one("js/theme.js", "https://example.test/ai-bunker", record)
    assert seen == ["https://example.test/ai-bunker/js/theme.js"]


# ---------------------------------------------------------------------------
# The exit code, which is the only part a caller can act on.
# ---------------------------------------------------------------------------


def test_agreement_exits_zero(vd, capsys):
    results = [vd.Result("index.html", "identical")]
    assert vd.report(results, "https://example.test") == 0
    assert "production matches the repository" in capsys.readouterr().out


@pytest.mark.parametrize("verdict", ["differs", "missing", "unreachable"])
def test_any_drift_exits_non_zero(vd, verdict, capsys):
    """A check that reports a failure and exits zero is not a check -- the same
    reason `ai-bunker budget --gate` makes the verdict the exit code."""
    results = [vd.Result("index.html", "identical"), vd.Result("start.html", verdict, "detail")]
    assert vd.report(results, "https://example.test") == 1
    assert "start.html" in capsys.readouterr().out


def test_the_limit_is_stated_when_there_is_drift(vd, capsys):
    """It cannot enumerate the server, so it cannot see a superseded file left
    behind by an earlier upload. Somebody reading a failure needs to know the
    check is one-directional rather than assume a clean bill."""
    vd.report([vd.Result("index.html", "differs", "x")], "https://example.test")
    assert "cannot see files on the server" in capsys.readouterr().out


def test_quiet_prints_the_drift_and_not_the_agreement(vd, capsys):
    results = [vd.Result("index.html", "identical"), vd.Result("start.html", "differs", "x")]
    vd.report(results, "https://example.test", quiet=True)
    out = capsys.readouterr().out
    assert "start.html" in out
    assert "identical    index.html" not in out


def test_the_summary_counts_every_verdict(vd, capsys):
    results = [
        vd.Result("a.html", "identical"),
        vd.Result("b.html", "differs", "x"),
        vd.Result("c.html", "missing", "HTTP 404"),
    ]
    vd.report(results, "https://example.test", quiet=True)
    out = capsys.readouterr().out
    assert "3 file(s)" in out
    for expected in ("1 differs", "1 identical", "1 missing"):
        assert expected in out


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


def test_a_stale_cache_is_not_a_failed_upload(vd):
    """The false positive this verdict exists for, reproduced.

    `deraison.ai` sits behind Varnish, which ignores a client's
    `Cache-Control` by default -- so `no-cache` is a hint, not a guarantee.
    The first version reported `llms.txt` as a stale upload immediately after
    a correct one: right at the origin, 19 minutes old at the edge.

    Telling an operator to re-upload a file they just uploaded correctly is
    how a checker teaches people to ignore it.
    """
    local = (_site() / "llms.txt").read_bytes()
    seen: list[str] = []

    def cached_then_origin(url):
        seen.append(url)
        # The edge answers the plain URL with yesterday's copy; the query
        # string changes the cache key and reaches the origin.
        return (200, local) if "ai-bunker-verify=" in url else (200, local.replace(b"0.2", b"0.1"))

    result = vd.verify_one("llms.txt", "https://example.test", cached_then_origin)
    assert result.verdict == "edge-stale"
    assert result.ok, "the upload was correct; only the cache is behind"
    assert len(seen) == 2, "the origin must be consulted before drift is reported"
    assert "ai-bunker-verify=" in seen[1]


def test_real_drift_survives_the_origin_check(vd):
    """A cache can serve content that is too old; it cannot invent content
    that is too new. So when the origin disagrees too, it is a real stale
    upload and must still be reported."""
    result = vd.verify_one("llms.txt", "https://example.test", lambda _url: (200, b"genuinely old"))
    assert result.verdict == "differs"
    assert not result.ok


def test_the_origin_check_runs_only_on_a_mismatch(vd):
    """Otherwise an ordinary run doubles its requests and litters the cache
    with one entry per file per run."""
    local = (_site() / "llms.txt").read_bytes()
    seen: list[str] = []

    def agree(url):
        seen.append(url)
        return 200, local

    assert vd.verify_one("llms.txt", "https://example.test", agree).verdict == "identical"
    assert len(seen) == 1
    assert "ai-bunker-verify=" not in seen[0]


def test_an_unreachable_origin_does_not_promote_drift_to_stale(vd, monkeypatch):
    """If the busting fetch fails, nothing was learned, so the mismatch stands
    as drift. Silently calling it a cache would hide a real stale upload."""
    monkeypatch.setattr(vd, "RETRY_PAUSE", 0)

    def edge_then_nothing(url):
        if "ai-bunker-verify=" in url:
            raise TimeoutError("timed out")
        return 200, b"old bytes"

    assert vd.verify_one("llms.txt", "https://example.test", edge_then_nothing).verdict == "differs"


def test_bust_keeps_the_path_and_adds_a_unique_key(vd):
    url = "https://example.test/ai-bunker/llms.txt"
    first, second = vd.bust(url), vd.bust(url)
    assert first.startswith(url + "?ai-bunker-verify=")
    assert first != second, "a repeated key would be cached like the original"
    assert vd.bust(url + "?x=1").startswith(url + "?x=1&ai-bunker-verify=")


def test_edge_stale_exits_zero_and_says_the_upload_was_fine(vd, capsys):
    """The exit code is what a script acts on, and re-uploading is exactly the
    wrong action here."""
    results = [vd.Result("llms.txt", "edge-stale", "correct at the origin")]
    assert vd.report(results, "https://example.test") == 0
    out = capsys.readouterr().out
    assert "EDGE-STALE" in out
    assert "the upload is correct" in out


def test_edge_stale_beside_real_drift_still_exits_non_zero(vd, capsys):
    results = [
        vd.Result("llms.txt", "edge-stale", "correct at the origin"),
        vd.Result("index.html", "differs", "x"),
    ]
    assert vd.report(results, "https://example.test") == 1
    out = capsys.readouterr().out
    assert "EDGE-STALE" in out
    assert "re-upload the tree" in out
