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

ROOT = Path(__file__).resolve().parent.parent


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


@pytest.fixture(scope="module")
def vd():
    return _load()


# ---------------------------------------------------------------------------
# What it looks at. This is the half that was wrong by hand.
# ---------------------------------------------------------------------------


def test_the_file_list_is_the_one_publish_would_upload(vd):
    """Reusing `publish.shipped()` rather than globbing here is the whole
    design, and this is the assertion that keeps it honest.

    The hand check that prompted this script filtered by extension and was
    wrong in both directions: it missed the served JavaScript and fonts, and
    it included build-time partials. A verifier with its own idea of what
    ships verifies its own idea.
    """
    sys.path.insert(0, str(ROOT / "web"))
    import publish

    assert vd.shipped_files() == [str(p.relative_to(publish.HERE)) for p in publish.shipped()]


def test_the_served_javascript_and_fonts_are_checked(vd):
    """The eight files the hand check missed, named so they cannot be lost
    again by a future change to how the list is built."""
    paths = vd.shipped_files()
    assert "js/theme.js" in paths
    assert "js/nav.js" in paths
    assert len([p for p in paths if p.endswith(".woff2")]) == 6


def test_build_time_files_are_not_checked(vd):
    """`_shell/` partials, the Tailwind input and the favicon source sizes are
    not served, so asking production for them would report four-oh-fours as
    missing uploads."""
    paths = vd.shipped_files()
    assert not [p for p in paths if p.startswith("_shell")]
    assert not [p for p in paths if p.endswith("tailwind-input.css")]
    assert not [p for p in paths if p in {"favicon-16.png", "favicon-32.png", "favicon-48.png"}]
    assert not [p for p in paths if p.endswith(".py")]


def test_every_listed_file_exists_locally(vd):
    """`verify_one` reads the local file before asking the network, so a path
    that does not exist would be a crash rather than a verdict."""
    for path in vd.shipped_files():
        assert (ROOT / "web" / path).is_file(), path


def test_the_base_url_comes_from_publish(vd):
    sys.path.insert(0, str(ROOT / "web"))
    import publish

    assert vd.base_url() == publish.BASE.rstrip("/")
    assert not vd.base_url().endswith("/"), "a trailing slash would build //path"


# ---------------------------------------------------------------------------
# The four verdicts, and why they are four rather than two.
# ---------------------------------------------------------------------------


def test_matching_bytes_are_identical(vd):
    local = (ROOT / "web" / "index.html").read_bytes()
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
    local = (ROOT / "web" / "index.html").read_bytes()
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
    body = (ROOT / "web" / "index.html").read_bytes()

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
        return 200, (ROOT / "web" / "js" / "theme.js").read_bytes()

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
