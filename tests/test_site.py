"""
Tests for the website.

The site is written by hand rather than generated from the Markdown, which was
a deliberate choice and carries one cost: the figures quoted on it can drift
from the repository. In three weeks the README says 354 tests and the site says
269, and nothing notices.

So the numbers are asserted against their sources. That keeps the advantage of
hand-written pages without the defect.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import functools
import pathlib
import re
import subprocess
import sys

import pytest

from ai_bunker.adopt import ROOT, site_root
from ai_bunker.charter import load_charter
from ai_bunker.rules import load_rules
from ai_bunker.rules import test_rules as check_rules
from ai_bunker.spec import load as load_scenarios

#: Where the website is, or None when it is not on this machine -- it lives
#: outside this repository now. The tests below split cleanly in two: most of
#: them read the site and skip without it, and five read *this repository's*
#: prose and must keep running, because the figures in the README are still
#: this repository's problem.
WEB = site_root()
PAGES = sorted(WEB.glob("*.html")) + sorted((WEB / "fr").glob("*.html")) if WEB else []

#: Applied to every test that cannot answer its question without the site. A
#: skip states why; a failure would be red on every continuous-integration run
#: for a reason that is not a defect, and a gate that is always red is a gate
#: nobody reads.
needs_site = pytest.mark.skipif(
    WEB is None, reason="the site is not on this machine (set AI_BUNKER_SITE)"
)


@pytest.fixture(scope="module")
def all_text() -> str:
    if WEB is None:
        pytest.skip("the site is not on this machine (set AI_BUNKER_SITE)")
    return "\n".join(p.read_text(encoding="utf-8") for p in PAGES)


#: The prose that quotes the same figures as the site and was not guarded by
#: anything. The site's numbers were corrected when a rule was added; these
#: four files kept the old ones, which is the failure this fixture exists to
#: make impossible.
PROSE = [
    ROOT / "README.md",
    ROOT / "LISEZMOI.md",
    ROOT / "docs" / "RULES.md",
    ROOT / "docs" / "REGLES.md",
    ROOT / "EXAMPLES.md",
    ROOT / "EXEMPLES.md",
]
if WEB is not None:
    PROSE += [WEB / "DEPLOY.md", WEB / "llms.txt"]


@pytest.fixture(scope="module")
def all_prose() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in PROSE if p.exists())


def test_the_documentation_quotes_the_real_rule_counts(all_prose):
    """The site is guarded; the prose was not, and drifted the moment a rule
    was added. Same assertion, applied to the files people actually read
    first.

    Two blind spots closed here, both found by reading what this guard
    actually matched rather than what it was named after:

    * The summary sentence is `N rules, M assertions, S scenarios`, and only
      `N` was captured -- `M` sat inside a non-capturing group and `S` was not
      in the pattern at all. So `224 scenarios` stood unchallenged next to a
      corrected `27 rules, 218 assertions` while the specification had grown
      to 277, and the half of the sentence the generator owned made the other
      half look maintained.
    * Every pattern was English. `LISEZMOI.md` is in `PROSE` and was read on
      every run, but nothing looked for `règles` or `scénarios`, so it quoted
      25 rules and 198 assertions for three sessions. A guard that reads a
      translated file without knowing its words is a guard that reports on a
      file it never checked.
    """
    rules = load_rules(ROOT / "charter" / "rules")
    report = check_rules(rules)
    scenarios = len(load_scenarios(ROOT / "features"))

    for pattern, actual, label in (
        (r"rules loaded\s+(\d+)", len(rules), "rules"),
        (r"\[ok\s*\]\s*(\d+) rules loaded", len(rules), "rules"),
        (r"assertions passed\s+(\d+)", report.passed, "assertions"),
        (r"\[ok\s*\]\s*(\d+) rule assertions pass", report.passed, "assertions"),
        (r"(\d+) rules, (?:\d+) assertions", len(rules), "rules"),
        (r"\d+ rules, (\d+) assertions", report.passed, "assertions"),
        (r"\d+ rules, \d+ assertions, (\d+) scenarios", scenarios, "scenarios"),
        (r"(\d+) règles, (?:\d+) assertions", len(rules), "rules (fr)"),
        (r"\d+ règles, (\d+) assertions", report.passed, "assertions (fr)"),
        (r"\d+ règles, \d+ assertions, (\d+) scénarios", scenarios, "scenarios (fr)"),
    ):
        for n in {int(x) for x in re.findall(pattern, all_prose)}:
            assert n == actual, f"the documentation says {n} {label}; there are {actual}"


@pytest.mark.gate
def test_no_published_figure_is_stale():
    """`sync_counts.py --check`, which nothing had ever run.

    The tests around this one assert specific figures by reading them back out
    of the prose: rules, assertions, scenarios, the test count. They are the
    *read* side. `scripts/sync_counts.py` is the write side, and its
    substitution list is the authoritative inventory of every figure this
    repository publishes -- nineteen patterns across eight files, several of
    which no assertion here has ever looked at.

    Four test modules mention the script in their docstrings. None invoked it.
    So the inventory grew, the generator stayed correct, and whether a figure
    it owns had drifted was answered by whoever last typed the command.

    This runs it in `--check` mode, which changes nothing and returns non-zero
    when a file quotes something the repository no longer says. It costs one
    collection subprocess, the same one the test below already pays for.
    """
    assert _sync_counts().main(["--check"]) == 0, (
        "a published figure has drifted; run sync_counts.py"
    )


@pytest.mark.gate
def test_the_documentation_quotes_the_real_test_count(all_prose):
    """Only claims about the present. A sentence like "the 327 tests of the
    time did not catch it" is a fact about a past moment and must keep its
    number -- updating it would turn a true statement into a false one -- so
    the pattern is anchored on the checklist row, which is a claim about now.

    This carried `@needs_site` and should never have: `all_prose` is the six
    files of *this* repository plus the site's two when the site happens to be
    on the machine, and `sync_counts.py` states in its own comment that the
    site deliberately quotes no test count at all -- "only the READMEs carry
    the number". So the one figure nothing outside this repository states was
    the one whose guard demanded a checkout of something outside this
    repository: green on a laptop with the site beside it, skipped in the lane
    where the README is the only thing there is.
    """
    actual = _collected_tests()
    quoted = {int(x) for x in re.findall(r"\|\s*(\d+) tests, `ruff`", all_prose)}
    assert quoted, "nothing quotes a test count any more; delete this test or the row"
    for n in quoted:
        assert n == actual, f"the documentation says {n} tests; pytest collects {actual}"


@needs_site
def test_the_site_has_both_languages():
    """A correspondence rather than a count. A page written in one language and
    forgotten in the other is the failure worth catching; a hard-coded 4 caught
    it only until the next page was added, and then failed on the language that
    had been done right."""
    pages = WEB / "pages"
    slugs = {p.name.removesuffix(".en.py") for p in pages.glob("*.en.py")}
    assert slugs == {p.name.removesuffix(".fr.py") for p in pages.glob("*.fr.py")}
    assert {p.stem for p in WEB.glob("*.html")} == slugs
    assert {p.stem for p in (WEB / "fr").glob("*.html")} == slugs


# ---------------------------------------------------------------------------
# The numbers on the site are the repository's numbers.
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _sync_counts():
    """`scripts/sync_counts.py`, imported by path and once."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sync_counts", ROOT / "scripts" / "sync_counts.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _collected_tests() -> int:
    """What pytest actually collects, asked of the module that owns the figure.

    This used to run its own `--collect-only` subprocess, beside the one
    `sync_counts.py` runs — two full re-imports of the suite, on both
    interpreters, to learn one number twice. `sync_counts` is the *writer* of
    that figure, so it is the one place that should measure it, and this reads
    it from there.

    The measurement itself is unchanged and its history is worth keeping. It
    used to parse the AST, which expanded `parametrize` by reading the
    decorator and counted anything it could not resolve as one case — so it
    under-counted, the site advertised 383 while pytest printed 394, and the
    guard agreed with the site because it was comparing the site to its own
    estimate. On a project whose claim is that every published number is
    measured, that is the one place an estimate must not be.

    And it counts what a *clone* collects. Twenty-one tests are parametrised
    over the website's pages, so the total was 1,156 here and 1,135 in the
    lane; `adopt.without_site` is what makes the two agree.

    One subprocess, and the cache that makes it one is *not* here: it is the
    `lru_cache` on `sync_counts.collected_tests`. Round 34 wrote that down and
    stopped there, which left the one claim in it that rests on a decorator in
    another file with nothing watching the decorator. Take it off and this
    quietly starts paying for a second full re-import of the suite, beside the
    one `--check` pays for above, and every test here still passes.
    `test_the_collection_subprocess_is_paid_for_once` is the gate that was
    missing.
    """
    return _sync_counts().collected_tests()


def test_the_collection_subprocess_is_paid_for_once():
    """Two callers in one process want the same number; one subprocess answers.

    `collected_tests` re-imports the whole suite in a subprocess to get it, and
    what makes that one subprocess rather than two is an `lru_cache` in
    `scripts/sync_counts.py` -- a different file from the caller that depends
    on it. `_collected_tests` above reads the figure from there precisely so it
    does not measure it a second time.

    Round 34 built that arrangement, wrote in both docstrings that it rests on
    a decorator somewhere else, and gated none of it. Take the decorator off
    and every other test in this file still passes while the suite silently
    goes back to two full re-imports, on both interpreters. That is the shape
    of defect this repository keeps finding -- a claim with nothing behind it
    -- so the claim here is the one thing a stopwatch cannot argue with: the
    number of subprocesses.

    Loaded as its own module instance rather than through `_sync_counts()`, so
    that the cache this fills with a fake count is not the one the rest of the
    file reads.
    """
    import importlib.util
    import types

    spec = importlib.util.spec_from_file_location(
        "sync_counts_probe", ROOT / "scripts" / "sync_counts.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    started = []

    def fake_run(argv, **kwargs):
        started.append(argv)
        return types.SimpleNamespace(stdout="tests/test_one.py: 7\ntests/test_two.py: 5\n")

    module.subprocess = types.SimpleNamespace(run=fake_run)

    first = module.collected_tests()
    assert first == 12, "the per-file counts are summed, not re-read"
    assert [module.collected_tests() for _ in range(3)] == [first] * 3

    assert len(started) == 1, (
        f"{len(started)} subprocesses for one number -- the `lru_cache` on "
        "sync_counts.collected_tests is gone, and nothing else would have said so"
    )
    assert "--collect-only" in started[0], "this is no longer a collection subprocess"


def test_the_site_quotes_no_test_count(all_text):
    """Inverted on purpose, rather than deleted.

    The site used to quote the exact number of tests. It changes on every
    commit that adds one, so the deployed site went stale after every commit
    and the operator paid an upload to correct a figure no reader acts on --
    "a green CI gate" is the claim, and it does not rot.

    This asserts the number stays off the site, because the natural thing for
    someone to do when writing a new page is to put it back.
    """
    quoted = re.findall(r"\b\d{3,} tests\b", all_text)
    assert not quoted, f"the site quotes a test count again: {quoted[:3]}"


def test_the_quoted_rule_counts_are_real(all_text):
    rules = load_rules(ROOT / "charter" / "rules")
    report = check_rules(rules)

    for pattern, actual, label in (
        (r"rules loaded\s+(\d+)", len(rules), "rules"),
        (r"assertions passed\s+(\d+)", report.passed, "assertions"),
    ):
        quoted = {int(n) for n in re.findall(pattern, all_text)}
        assert quoted, f"the site no longer quotes {label}"
        for n in quoted:
            assert n == actual, f"the site says {n} {label}; the repository has {actual}"


def test_the_quoted_coverage_is_real(all_text):
    report = check_rules(load_rules(ROOT / "charter" / "rules"))
    quoted = {int(n) for n in re.findall(r"rules carrying evidence\s+(\d+)%", all_text)}
    assert quoted
    for n in quoted:
        assert n == round(report.coverage * 100)


def test_the_quoted_charter_figures_are_real(all_text):
    """607 tokens of floor, 2,608 characters not loaded — both on the site."""
    charter = load_charter(ROOT / "charter")
    pages = sum(p.chars for p in charter.pages)
    for n in {int(n.replace(",", "")) for n in re.findall(r"([\d,]{3,}) characters", all_text)}:
        assert n == pages, f"the site says {n:,} characters of pages; the charter has {pages:,}"


def test_the_quoted_charter_floor_is_real(all_prose):
    """The figure that drifted without anybody noticing.

    `CHARS_PER_TOKEN` was corrected from 4.0 to 2.5 and the charter's floor
    moved from 607 to 972 tokens -- 60% -- while eight documents went on
    quoting 607 as real command output. `sync_counts` did not own the figure
    and `lint_claims` guards sentences rather than numbers, so it fell exactly
    between the two guards built to prevent this.
    """
    from ai_bunker.budget import Counter
    from ai_bunker.charter import system_blocks

    counter = Counter(allow_ratio=True)
    charter = load_charter(ROOT / "charter")
    actual = sum(counter.count(block) for block in system_blocks(charter))

    quoted = {
        int(n.replace(",", "")) for n in re.findall(r"floor cost\s+([\d,]+) tokens", all_prose)
    }
    assert quoted, "no document quotes the charter floor any more; drop this test too"
    for n in quoted:
        assert n == actual, f"the documentation says a floor of {n}; it is {actual}"


def test_the_quoted_version_is_real(all_text):
    from ai_bunker import __version__

    quoted = set(re.findall(r"(\d+\.\d+\.\d+)-alpha", all_text))
    assert quoted
    for v in quoted:
        assert v == __version__


# ---------------------------------------------------------------------------
# What the site must not do.
# ---------------------------------------------------------------------------


def test_no_page_fetches_from_a_third_party_or_carries_a_tracker(all_text):
    """The site makes the sovereignty claim; it cannot contradict it on load.

    Two halves of one promise, and the second is the one that creeps back in:
    a content delivery network arrives in a stylesheet and is visible in a
    diff, where an analytics snippet arrives in a footer somebody pasted and
    is not.
    """
    for host in (
        "cdn.tailwindcss.com",
        "googleapis.com",
        "jsdelivr",
        "unpkg",
        "cdnjs",
        "fonts.gstatic",
        "google-analytics",
        "googletagmanager",
    ):
        assert host not in all_text, f"a page reaches out to {host}"

    for tracker in ("gtag(", "_paq", "fbq(", "plausible", "analytics"):
        assert tracker not in all_text.lower(), f"found {tracker}"


@needs_site
def test_every_image_has_an_alt_that_is_not_the_caption():
    """An alt repeating the caption tells a screen-reader user nothing new."""
    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        for img in re.findall(r"<img[^>]+>", text):
            if 'alt=""' in img:
                continue  # decorative, correctly marked
            alt = re.search(r'alt="([^"]*)"', img)
            assert alt and alt.group(1).strip(), f"{page.name}: <img> with no alt"
            assert len(alt.group(1)) > 40, (
                f"{page.name}: alt is too short to describe a figure: {alt.group(1)!r}"
            )


# ---------------------------------------------------------------------------
# The gates the deploy depends on.
# ---------------------------------------------------------------------------


@needs_site
def test_the_publish_checker_passes():
    result = subprocess.run(
        [sys.executable, str(WEB / "publish.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
        cwd=WEB,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("page", [p.relative_to(WEB).as_posix() for p in PAGES])
def test_every_page_passes_the_accessibility_lint(page):
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "lint_a11y.py"), page],
        capture_output=True,
        text=True,
        check=False,
        cwd=WEB,
    )
    assert result.returncode == 0, result.stdout


@needs_site
def test_the_stylesheet_is_built_and_committed():
    """Deployment is a file upload; a missing stylesheet means a Node toolchain
    on the far end, which the person who owns the site should not need."""
    css = WEB / "css" / "app.css"
    assert css.exists() and css.stat().st_size > 5000
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", str(css)], cwd=ROOT, check=False
    ).returncode
    assert ignored != 0, "app.css is gitignored; it must ship"


@needs_site
def test_the_figures_meet_their_contrast_floor_on_both_schemes():
    """The figures' text sits on tints of the brand colours themselves, so a
    token that passes against white can still fail against its own card --
    which is why they get their own auditor rather than riding on the page's.

    Three things, and the first alone would not be worth much. The shipped
    figures **pass**. The auditor **can fail**: an auditor nobody has seen
    fail is an auditor nobody should trust, and the figures once shipped a
    fixed `#8A8A92` that scored 5.74:1 on the dark page and 3.43:1 on white,
    so restoring it must put the audit back in the red. And the figures carry
    **no hard-coded colour** at all, because a literal hex cannot know which
    scheme it is on -- the greys were fixed values tuned for dark, and the
    light scheme inherited them silently.
    """
    import importlib.util

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "audit_figures.py")],
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "every pair meets" in result.stdout

    spec = importlib.util.spec_from_file_location(
        "audit_figures", ROOT / "scripts" / "audit_figures.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The grey as it was, against the page it was never checked on.
    assert module.contrast((0x8A, 0x8A, 0x92), (255, 255, 255)) < module.FLOOR
    # And the replacement, against the darkest surface it actually lands on.
    assert module.contrast((0x65, 0x65, 0x69), (255, 255, 255)) >= module.FLOOR

    source = (WEB / "pages" / "_figures.py").read_text(encoding="utf-8")
    literals = re.findall(r'(?:fill|stroke)="(#[0-9A-Fa-f]{3,8})"', source)
    assert not literals, f"figures carry hard-coded colours: {sorted(set(literals))}"


@needs_site
def test_nothing_unreferenced_would_be_uploaded():
    """The dead-link check runs one way: every reference resolves to a file.
    This runs the other way, and only one of the two shows a symptom. An
    orphan costs an SFTP upload and nothing else, so it accumulates quietly --
    three superseded logo exports and a replaced chart, 765 KB, were sitting in
    ``img/`` when this was written."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("publish", WEB / "publish.py")
    publish = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publish)

    assert publish.orphans() == []

    # And it has to be able to see one, or it is not checking anything.
    stray = WEB / "img" / "_orphan_probe.png"
    stray.write_bytes(b"\x89PNG\r\n\x1a\n")
    try:
        found = publish.orphans()
        assert any("_orphan_probe.png" in p for p in found), found
    finally:
        stray.unlink()


@needs_site
def test_no_page_loads_a_script_twice():
    """A script included twice runs twice, and every listener it registers
    fires twice per event. The footer shell and the page template both emitted
    js/theme.js, so each click on the theme toggle flipped the scheme and then
    flipped it back: a control that was present, wired, silent, and dead, on
    all eight pages in production."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("publish", WEB / "publish.py")
    publish = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publish)
    assert publish.double_loads() == []


@pytest.mark.parametrize("page", [p.relative_to(WEB).as_posix() for p in PAGES])
def test_the_theme_toggle_is_wired_exactly_once(page):
    """The guard above is static. This one reads the markup the way the
    browser does: one button, one script that wires it."""
    text = (WEB / page).read_text(encoding="utf-8")
    assert text.count('id="theme-toggle"') == 1, "more than one element claims the id"
    assert len(re.findall(r'<script[^>]+src="[^"]*js/theme\.js"', text)) == 1


@pytest.mark.parametrize("page", [p.relative_to(WEB).as_posix() for p in PAGES])
def test_the_language_toggle_goes_to_the_same_page_in_the_other_language(page):
    """The flag must not cost the reader their place.

    It was written into the shared header as the other language's homepage,
    which is correct on `index.html` and wrong on the six other pages: a
    reader half-way down "Sizing" who clicked 🇫🇷 landed on the French front
    page and had to find their way back. Every counterpart has existed the
    whole time, and the `hreflang` links in the same `<head>` have always
    named the right one -- so the crawler was told more than the reader.

    Asserted per page, and the target is asserted to exist: a toggle pointing
    at a 404 is worse than one pointing at the homepage.
    """
    text = (WEB / page).read_text(encoding="utf-8")
    label = "English version" if page.startswith("fr/") else "Version française"
    found = re.search(rf'href="([^"]+)"[^>]*aria-label="{label}"', text)
    assert found, f"{page} has no language toggle labelled {label!r}"

    href = found.group(1)
    target = (WEB / page).parent / href
    assert target.resolve().is_file(), f"{page} sends the reader to {href}, which is not a page"

    slug = pathlib.Path(page).name
    assert pathlib.Path(href).name == slug, (
        f"{page} sends the reader to {href} instead of the same page in the other language"
    )


@needs_site
def test_out_refuses_a_destination_it_did_not_produce(tmp_path):
    """`--out` deletes its destination, so this guard is the only thing
    between a mistyped path and somebody's work.

    It was written once as "refuse when the destination is this tree, or
    contains it, or is inside it". That is necessary and nowhere near
    sufficient: a sibling directory is none of those three. Pointed at one, the
    command removed forty-three entries belonging to another project -- no
    Time Machine, no snapshot, `rmtree` does not use the Trash.

    The test that would have caught it does not ask where the destination sits.
    It asks **what is in it**: an assembled tree holds only names this tree
    produces, so anything else means the path is not an output directory and
    never was.

    Checked as a pure function against fabricated directories. A destructive
    guard verified by running the destruction is not verified, it is used.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("publish", WEB / "publish.py")
    publish = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publish)

    # The shape of the directory that was destroyed: somebody else's web root.
    victim = tmp_path / "another-project"
    victim.mkdir()
    for name in ("4ml", "assets", "includes"):
        (victim / name).mkdir()
    for name in ("index.php", "config.php", "book.pdf"):
        (victim / name).write_text("x", encoding="utf-8")
    assert publish.why_not_replaceable(victim), (
        "a directory holding files this tree never produces must be refused"
    )

    # A tree `--out` really did produce: only names it ships.
    produced = tmp_path / "a-previous-out"
    produced.mkdir()
    for entry in publish.HERE.iterdir():
        if entry.name in publish.EXCLUDE:
            continue
        if entry.is_dir():
            (produced / entry.name).mkdir()
        else:
            (produced / entry.name).write_text("x", encoding="utf-8")
    assert publish.why_not_replaceable(produced) is None, "its own output must be replaceable"

    # Absent and empty are both fine; a file is not a destination.
    assert publish.why_not_replaceable(tmp_path / "absent") is None
    empty = tmp_path / "empty"
    empty.mkdir()
    assert publish.why_not_replaceable(empty) is None
    plain = tmp_path / "a-file"
    plain.write_text("x", encoding="utf-8")
    assert publish.why_not_replaceable(plain)

    # And the three that were already guarded, which still have to hold.
    here = publish.HERE.resolve()
    for target in (here, here.parent, here / "css"):
        assert publish.why_not_replaceable(target), f"{target} must be refused"
