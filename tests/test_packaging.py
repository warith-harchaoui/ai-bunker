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

import re
from pathlib import Path

import pytest
import tomllib

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def manifest() -> dict:
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

    silenced = {m for o in cfg["overrides"] for m in o["module"]}
    assert silenced == {"os_helper.*", "best_engine_ai_helper.*", "fastapi_mcp.*"}


def test_mypy_is_clean_on_this_tree():
    """The gate, run here as well as in the lane.

    Skipped rather than failed when `mypy` is not installed: it is a `[dev]`
    extra, and a developer who installed the package without the extra is not
    looking at a defect. In the lane the extra is always present, so the step
    there is unconditional and this is the second pair of eyes.
    """
    mypy_api = pytest.importorskip("mypy.api", reason="mypy is a [dev] extra")
    out, err, status = mypy_api.run(["--config-file", str(ROOT / "pyproject.toml")])
    assert status == 0, f"mypy is not clean:\n{out}{err}"
