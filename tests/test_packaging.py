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
    # Was "ci" until round 36, which is to say: run only where it has never
    # had anything to report. A guard whose green is indistinguishable from a
    # guard that stopped looking is the shape this repository distrusts, so it
    # is exercised in both directions here now.
    "no_heavy_stack.py": "tests/test_packaging.py",
    "lint_acronyms.py": "tests/test_acronyms.py",
    "lint_claims.py": "tests/test_claims.py",
    "lint_film.py": "tests/test_film.py",
    "lint_handoff.py": "tests/test_handoff.py",
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
    # `measure_type.py` reads per-character widths and ink extents out of
    # Roboto, Helvetica Neue, Helvetica and Arial, so it needs `fontTools` and
    # those four fonts. A lane has none of them and should not: what it
    # writes, `assets/font-metrics.json`, is committed, and that is what
    # `audit_figures.py` reads.
    #
    # The drift this leaves is closed without the fonts.
    # `test_the_advance_table_describes_the_font_stack_the_figures_ask_for`
    # compares the stack recorded in the table against `make_figures.FONT`, so
    # changing the stack turns the suite red and says to re-measure; and the
    # audit reports any character in a committed figure that the table has no
    # width for, rather than falling back to an average.
    "measure_type.py": None,
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


def test_the_floor_guarantees_the_image_picker_and_the_workaround_is_gone(manifest):
    """A workaround and its reason have to live or die together.

    `imagine_rank` and `imagine_pick` are the text-to-image selector this
    project delegates the whole slot to. For several releases they existed
    only on the provider's development branch, so seven tests skipped under
    every published version -- and the lane compensated with two steps that
    `pip install`-ed the helper from git and re-ran two test modules. Those
    steps carried their own instruction: delete them the day `pyproject.toml`
    can floor the helper at a published version that carries the picker.

    1.10.0 publishes it. Verified against the wheel from the package index in
    a clean environment, not against the maintainer's editable checkout, which
    is the distinction that made the old claim wrong for two rounds.

    Three things are asserted, and the third is the one that matters: the
    floor is high enough, the symbols are really there, and the workaround is
    **not**. A raised floor with the git-clone steps still in place would
    install the branch over the release and test something no user has; the
    steps removed with the floor left low would silently stop exercising the
    slot at all. Either half alone is worse than neither.
    """
    floor = next(
        spec for spec in manifest["project"]["dependencies"] if "best-engine-ai-helper" in spec
    )
    major, minor = (int(part) for part in floor.split(">=")[1].split(".")[:2])
    assert (major, minor) >= (1, 10), f"{floor} predates the published image picker"

    helper = pytest.importorskip("best_engine_ai_helper")
    for symbol in ("imagine_rank", "imagine_pick"):
        assert hasattr(helper, symbol), (
            f"the installed helper has no {symbol}; either the floor is wrong or the "
            f"provider removed it"
        )

    workflow = WORKFLOW.read_text(encoding="utf-8")
    runs = "\n".join(re.findall(r"^\s+run:.*(?:\n\s{8,}.*)*", workflow, re.M))
    assert "best-engine-ai-helper @ git+" not in runs, (
        "the floor carries the picker, so the lane must not install the provider's "
        "branch over the release a user gets"
    )


def test_the_gate_marker_runs_somewhere_exactly_once(manifest):
    """A deselection is a way to stop running a check without deleting it.

    `-m "not gate"` on the older leg is how five test modules and two tests in
    a sixth stop being paid for twice, and the failure mode it creates is the
    one this repository has now caught four times: a check that is declared
    and never run. Put `-m "not gate"` on *both* legs and the figure audit,
    the claim linter, the abbreviation catalogue, the film spec and the
    handoff gate all stop running, in silence, with every one of them still
    sitting in `tests/`.

    So: the marker must be registered, and exactly one leg of the matrix must
    deselect it.

    This guard carries no `gate` marker of its own, and that is deliberate
    twice over. It reads two committed files, so by the marker's own
    definition it would qualify. But a guard against over-deselection must not
    be deselectable by the thing it guards: marked `gate`, a second
    `-m "not gate"` would silence the guard in the same breath as the five
    modules it protects, and nothing would be left to notice. It is also not
    among the checks paid for twice, because `manifest` skips wherever
    `tomllib` is not standard library -- every interpreter below 3.11 -- so
    the cost this round is about never applied to it.
    """
    declared = manifest["tool"]["pytest"]["ini_options"].get("markers", [])
    assert any(m.startswith("gate:") for m in declared), (
        "the `gate` marker is used in tests/ and not declared in pyproject.toml"
    )

    workflow = WORKFLOW.read_text(encoding="utf-8")
    legs = re.findall(r"^\s+run:\s*pytest\b.*$", workflow, re.M)
    assert len(legs) == 2, f"the matrix has {len(legs)} suite steps; this test assumes two"

    deselecting = [leg for leg in legs if "not gate" in leg]
    assert len(deselecting) == 1, (
        "exactly one leg may skip the gate-marked tests -- two would mean they "
        f"never run at all: {legs}"
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


def test_the_deep_learning_guard_passes_and_can_still_fail(monkeypatch):
    """The last barrier in `SCRIPT_RUNNERS` with nothing but the lane behind it.

    `no_heavy_stack.py` is the guard that keeps a 196-megabyte torch wheel out
    of a proxy that loads no models, and in the lane it has never once
    reported anything — correctly, because the lane is clean. That is exactly
    the state this repository distrusts everywhere else: a check whose green
    is indistinguishable from a check that stopped looking. Break
    `heavy_imports` — a typo in `HEAVY`, a `find_spec` that returns `None`
    for everything — and torch creeps back into the lane behind a tick.

    So both directions, with the import machinery stubbed rather than the
    environment changed: this machine genuinely has torch installed, which is
    why the script exits 1 here and 0 in the lane, and a test that depended on
    which machine ran it would be the defect it is checking for.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "no_heavy_stack", ROOT / "scripts" / "no_heavy_stack.py"
    )
    guard = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(guard)

    assert guard.HEAVY, "the guard looks for nothing at all"
    assert "torch" in guard.HEAVY, "the wheel this exists to keep out is not in the list"

    found = {"torch": object(), "transformers": None, "diffusers": None}
    monkeypatch.setattr(guard.importlib.util, "find_spec", lambda name: found.get(name))
    assert guard.heavy_imports() == ["torch"]
    assert guard.main() == 1, "torch is installed and the guard said the lane was clean"

    monkeypatch.setattr(guard.importlib.util, "find_spec", lambda name: None)
    assert guard.heavy_imports() == []
    assert guard.main() == 0, "nothing heavy is installed and the guard refused anyway"
