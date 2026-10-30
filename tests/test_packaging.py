"""
What the distribution promises, and what has to be true for it to be honest.

A wheel makes claims that no test in `tests/` was reading. `py.typed` is the
loudest of them: it is a marker file whose entire meaning is *the annotations
in this package are maintained, run your type checker against them*. It
shipped here for months while `mypy ai_bunker` reported twenty-five errors and
no continuous-integration step ran it even once.

That is the same defect this repository has a linter for everywhere else -- a
claim with no gate behind it -- so the gate exists now, and this is the test
that notices if it is ever removed while the marker stays.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def manifest() -> dict:
    """`pyproject.toml`, parsed.

    `tomllib` is standard library from 3.11 and this package supports 3.10, so
    the fixture skips there rather than adding `tomli` as a dependency for one
    test file. Nothing asserted below can differ by interpreter -- a manifest
    is a manifest -- and the lane's `gate` job runs on 3.13, so the checks are
    made once where they can be made.
    """
    tomllib = pytest.importorskip("tomllib", reason="tomllib is stdlib from 3.11")
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_typing_marker_is_backed_by_a_type_check_in_the_lane(manifest):
    """`py.typed` is a promise; the lane is what makes it one.

    Both halves are asserted, in both directions. Shipping the marker without
    the step is the state this test was written to end. Running the step
    without shipping the marker would be harmless but misleading -- the
    annotations would be checked and no downstream project told it could
    rely on them -- so that is reported too.

    The step is matched on the *command*, not on a step name: a `name:` is
    prose and can be reworded, while `mypy` on a `run:` line is the thing
    that actually fails the build.
    """
    shipped = "py.typed" in manifest["tool"]["setuptools"]["package-data"]["ai_bunker"]
    workflow = WORKFLOW.read_text(encoding="utf-8")
    gated = bool(re.search(r"^\s+run:\s*mypy\b", workflow, re.M))

    assert shipped, "ai_bunker stopped shipping py.typed; delete this test or the mypy step"
    assert gated, (
        "pyproject.toml ships py.typed -- a promise that this package's annotations "
        "can be trusted -- and ci.yml has no `run: mypy` step to keep it true"
    )


def test_mypy_is_configured_to_check_this_package_and_name_what_it_skips(manifest):
    """A silence has to be narrow enough to notice when it widens.

    `ignore_missing_imports = true` at the top level would make the lane green
    and make it green for the wrong reason: the next dependency to arrive
    without stubs would be absorbed in silence. So the escape is per-module,
    and this asserts it stays per-module -- the check that keeps the check
    worth running.
    """
    cfg = manifest["tool"]["mypy"]
    assert cfg["files"] == ["ai_bunker"]
    assert not cfg.get("ignore_missing_imports"), (
        "a blanket ignore_missing_imports hides the next untyped dependency; "
        "name the module in [[tool.mypy.overrides]] instead"
    )

    # Named one by one, and the list is short on purpose: each entry is a
    # package that genuinely ships no types, and `tokenizers` is here because
    # it is an *optional extra* -- absent from the lane by design, since the
    # whole point of the extra is that the package works without it.
    silenced = {m for o in cfg["overrides"] for m in o["module"]}
    assert silenced == {
        "os_helper.*",
        "best_engine_ai_helper.*",
        "fastapi_mcp.*",
        "tokenizers.*",
    }

    # And the counter-example, which is what keeps the list from growing by
    # habit: stubs exist for PyYAML, so the answer was to install them rather
    # than to silence four modules. A silence that a real answer could replace
    # is a silence that should not be here.
    assert not any("yaml" in m for m in silenced), "types-PyYAML exists; install it"


#: Every `[dev]` tool, and the command in `ci.yml` that runs it. A tool with
#: no entry here is a failure, not an omission: twice now this repository has
#: declared a quality tool, never run it, and found out rounds later --
#: `mypy` against twenty-five errors and a `py.typed` marker, then
#: `pytest-cov` against a figure nobody had measured.
#:
#: A value of `None` is the honest escape for a tool that is a library rather
#: than a gate, and it has to be argued for in the comment beside it.
DEV_TOOLS = {
    "pytest": "pytest",
    "pytest-cov": "--cov",
    "ruff": "ruff check",
    "mypy": "mypy",
    # Not a gate: `httpx` is what `starlette`'s TestClient drives the gateway
    # with, so it is a test dependency rather than a tool with a verdict.
    "httpx": None,
    # Not a gate either: stubs for PyYAML, so that `mypy` can check the four
    # modules that import it instead of being told to ignore them. A silence
    # that can be replaced by a real answer should be.
    "types-PyYAML": None,
}


def test_every_declared_quality_tool_is_actually_run_in_the_lane(manifest):
    """The class, not the instance.

    `mypy` was declared and never run. So was `pytest-cov`. Both were found by
    reading `pyproject.toml` and noticing a name the workflow never mentions,
    which is a thing a test can do every time instead of a person doing it
    twice a year.

    Matched on the command rather than on a step name: a `name:` is prose and
    can be reworded, while the string on a `run:` line is what fails a build.
    """
    declared = {
        re.split(r"[><=\[]", spec)[0].strip()
        for spec in manifest["project"]["optional-dependencies"]["dev"]
    }
    assert declared == set(DEV_TOOLS), (
        f"a [dev] entry changed; decide whether it is a gate: {declared ^ set(DEV_TOOLS)}"
    )

    workflow = WORKFLOW.read_text(encoding="utf-8")
    runs = "\n".join(re.findall(r"^\s+run:.*(?:\n\s{8,}.*)*", workflow, re.M))
    for tool, command in DEV_TOOLS.items():
        if command is None:
            continue
        assert command in runs, f"{tool} is declared in [dev] and nothing in ci.yml runs it"


#: Every module in `scripts/`, and what runs it. `"ci"` means a `run:` line in
#: the workflow; a `tests/...` path means the suite; `None` is the escape, and
#: it has to be argued for in the comment beside it.
#:
#: The forcing function is the mapping being *exhaustive*. `pyproject.toml`
#: declares its tools, so `test_every_declared_quality_tool_is_actually_run_in
#: _the_lane` can read a list and find a name nothing invokes. A file this
#: repository wrote itself is declared nowhere, and that is exactly how the
#: launch film's claim checker went missing: `video/film.yaml` was verified by
#: a command typed on one laptop, in a directory the suite did not touch, while
#: the film's closing frame promised a test would fail if a number drifted.
#:
#: A mention is not a run, and the two are told apart by *shape*. Four test
#: modules discuss `sync_counts.py` in their prose and, until this round, none
#: of them invoked it -- so a search for the filename would have reported it
#: gated. A suite module that actually runs a script builds a path to it,
#: `ROOT / "scripts" / "name.py"`, which no sentence about it ever does.
#: That still would not catch a module that builds the path and never calls
#: what it loads; the part with real teeth is the mapping being exhaustive.
SCRIPT_RUNNERS = {
    "audit_contrast.py": "ci",
    "audit_figures.py": "ci",
    "lint_a11y.py": "ci",
    "no_heavy_stack.py": "ci",
    "lint_acronyms.py": "tests/test_acronyms.py",
    "lint_claims.py": "tests/test_claims.py",
    "lint_film.py": "tests/test_film.py",
    "make_figures.py": "tests/test_figures.py",
    "measure_overhead.py": "tests/test_budget.py",
    "sync_counts.py": "tests/test_site.py",
    "verify_deployment.py": "tests/test_verify_deployment.py",
    # The two escapes, and they are escapes rather than oversights.
    #
    # `bench_context.py` fits a line through decode time against prompt length,
    # which needs a loaded model on a live engine.
    "bench_context.py": None,
    # `measure_ratio.py --check` re-measures the characters-per-token floor
    # against three real tokenizers, so it wants the `tokenizers` extra -- an
    # extra the lane installs on purpose *not* to have -- and it downloads
    # three vocabularies. Its own docstring says so and says what it is for
    # instead: the thing you run when you change the constant.
    #
    # This entry was `tests/test_budget.py` for the length of one test run.
    # That module talks about the script in two docstrings and has never run
    # it, which is exactly the mistake the shape check above exists to catch,
    # made by the person adding the shape check.
    "measure_ratio.py": None,
    # `measure_advances.py` reads per-character widths out of Roboto,
    # Helvetica Neue, Helvetica and Arial, so it needs `fontTools` and those
    # four fonts. A lane has none of them and should not: what it writes,
    # `assets/font-advances.json`, is committed, and that is what
    # `audit_figures.py` reads.
    #
    # The drift this leaves is closed without the fonts.
    # `test_the_advance_table_describes_the_font_stack_the_figures_ask_for`
    # compares the stack recorded in the table against `make_figures.FONT`, so
    # changing the stack turns the suite red and says to re-measure; and the
    # audit reports any character in a committed figure that the table has no
    # width for, rather than falling back to an average.
    "measure_advances.py": None,
}


def test_every_script_this_repository_wrote_is_run_by_the_lane_or_the_suite():
    """The class, one level above `[dev]`.

    A quality tool arrives declared in a manifest, so a test can read the
    manifest. A gate this repository wrote itself arrives as a file, declared
    nowhere, and the only list of those is the directory listing -- so that is
    what is compared.
    """
    present = {path.name for path in (ROOT / "scripts").glob("*.py")}
    assert present == set(SCRIPT_RUNNERS), (
        "a script in scripts/ has no declared runner; wire it into the lane or "
        f"the suite and say so here: {present ^ set(SCRIPT_RUNNERS)}"
    )

    workflow = WORKFLOW.read_text(encoding="utf-8")
    runs = "\n".join(re.findall(r"^\s+run:.*(?:\n\s{8,}.*)*", workflow, re.M))
    for script, runner in SCRIPT_RUNNERS.items():
        if runner is None:
            continue
        if runner == "ci":
            assert f"scripts/{script}" in runs, f"{script} is declared a lane step and is not one"
        else:
            module = ROOT / runner
            assert module.exists(), f"{script} names {runner}, which does not exist"
            assert f'"scripts" / "{script}"' in module.read_text(encoding="utf-8"), (
                f"{runner} is declared to run {script} and only talks about it"
            )


def test_the_coverage_floor_is_declared_and_defended(manifest):
    """A floor that lives in a workflow argument is a floor one `-p` removes.

    It is in `pyproject.toml`, where `coverage` reads it whoever invokes it --
    the lane, a pre-commit hook, or somebody typing `pytest --cov` on a
    laptop. Asserted to exist and to be a real bar rather than a zero that
    makes the step green.
    """
    floor = manifest["tool"]["coverage"]["report"]["fail_under"]
    assert floor >= 85, f"a {floor}% floor does not defend anything"


def test_mypy_is_clean_on_this_tree():
    """The gate, for a developer who has not run the lane.

    Skipped in continuous integration, and that is the point rather than an
    evasion: the `gate` job runs `mypy` once, and this test runs inside the
    suite, which runs on two interpreters. Leaving it on would pay three times
    for an answer `python_version = "3.10"` pins identical -- which is the
    same argument the workflow already makes for every check below the suite.

    Skipped too when `mypy` is absent: it is a `[dev]` extra, and a developer
    who installed the package without the extra is not looking at a defect.
    """
    if os.environ.get("CI"):
        pytest.skip("the gate job runs mypy once; see the docstring")
    mypy_api = pytest.importorskip("mypy.api", reason="mypy is a [dev] extra")
    out, err, status = mypy_api.run(["--config-file", str(ROOT / "pyproject.toml")])
    assert status == 0, f"mypy is not clean:\n{out}{err}"
