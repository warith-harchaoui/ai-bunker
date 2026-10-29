"""Shared fixtures: the best-engine-ai-helper double.

Why a double at all
-------------------
The provider owns the diffusion arithmetic -- component footprints, denoising
steps, seconds per image -- and this project owns three things on top of it:
the gigabyte-to-gibibyte conversion, the anti-greed rule, and the refusals.
Those three are this project's code and have to be under test on every
machine, so they are tested against a stub rather than against whatever
best-engine-ai-helper the machine happens to carry.

Why here rather than in `test_engine.py`
----------------------------------------
Because `test_report.py` needs it too. The resident-plan row is assembled in
`sizing.py` and rendered in `report.py`, and the defect that motivated the
move lived in exactly that seam: the row printed a hardcoded `fp16` for every
image model, which is right for four of the provider's five and wrong for
`flux1-schnell`. A test that only ran where an unpublished helper is installed
could not catch it. A second copy of the double in a second file would have
been a second contract to let drift.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import pytest


def make_image_plan(catalog_id: str, score: float, resident_gb: float, **over):
    """One plan in the shape `imagine_rank` actually returns.

    The defaults are copied from a live run against the helper's own
    catalogue rather than invented, so a stub that drifts from the real
    contract is a stub that fails the live tests below first.
    """
    plan = {
        "catalog_id": catalog_id,
        "model": f"stub-org/{catalog_id}",
        "score": score,
        "resident_gb": resident_gb,
        "fits": True,
        "usable": True,
        "steps": 28,
        "size": "1024x1024",
        "seconds_per_image": 3.0,
        "offload": False,
        "blockers": [],
    }
    plan.update(over)
    return plan


@pytest.fixture
def stub_helper(monkeypatch):
    """A helper that answers the image questions, whatever the installed one
    offers.

    `_choose_image` imports `best_engine_ai_helper` inside the function, so
    replacing the entry in `sys.modules` is enough and no import order
    matters. The plan list is mutable: a test reshapes it to pose its own
    question, which is the only way to reach the refusals -- the real
    catalogue has no model that fails to fit a large card.
    """
    import sys
    import types

    module = types.ModuleType("best_engine_ai_helper")
    module.plans = [
        make_image_plan("big", score=88, resident_gb=43.3, steps=4, seconds_per_image=2.0),
        make_image_plan("lean", score=82, resident_gb=28.3),
        make_image_plan("tiny", score=58, resident_gb=2.9, size="512x512", seconds_per_image=0.3),
    ]
    module.asked = []
    # `dtype` lives on the catalogue entry and not on the plan, which is why
    # it has to be looked up rather than read off the answer -- and the two
    # values here mirror the provider's own split: four of its five image
    # models are fp16 and the largest, `flux1-schnell`, is bf16.
    module.entries = [
        {
            "id": p["catalog_id"],
            "kind": "image",
            "dtype": "bf16" if p["catalog_id"] == "big" else "fp16",
        }
        for p in module.plans
    ] + [{"id": "a-language-model", "kind": "llm"}]

    def load_catalog():
        return list(module.entries)

    def imagine_rank(entries, *, budget_gb, bandwidth_gbs=None, **_kw):
        offered = {str(e.get("id")) for e in entries}
        module.asked.append({"ids": offered, "budget_gb": budget_gb, "bandwidth": bandwidth_gbs})
        return [p for p in module.plans if p["catalog_id"] in offered]

    def imagine_pick(plans):
        # The helper's own rule: the best that runs, with no opinion about
        # what it costs. The opinion is `LEAN_TOLERANCE`, and it is ours.
        runnable = [p for p in plans if p.get("fits")]
        return max(runnable, key=lambda p: p["score"]) if runnable else None

    def rank(_hw, catalogue, _kind, *, application="code", **_kw):
        # The language slots go through the same stub, or replacing the module
        # would quietly drop the whole plan to the fallback path and the
        # budget assertions below would be measuring that instead.
        scored = [e for e in catalogue if (e.get("benchmarks") or {}).get(application) is not None]
        return sorted(scored, key=lambda e: -float(e["benchmarks"][application]))

    def parse_task(task):
        return {
            "application": "vision" if "vision-language" in task else "code",
            "vlm_application": "vision",
            "kinds": ["vlm"] if "vision-language" in task else ["llm"],
        }

    module.load_catalog = load_catalog
    module.imagine_rank = imagine_rank
    module.imagine_pick = imagine_pick
    module.rank = rank
    module.parse_task = parse_task
    module.available_memory = lambda: {"vram_gb": 64.0}
    module.compute_profile = lambda: {"bandwidth_gbs": 900.0}
    monkeypatch.setitem(sys.modules, "best_engine_ai_helper", module)
    return module


@pytest.fixture
def image_plan():
    """`make_image_plan`, as a fixture, so a test can reshape the catalogue.

    Handed out rather than imported because `conftest.py` is not importable
    by name from a test module without putting the directory on the path,
    and a fixture is the mechanism pytest already provides for this.
    """
    return make_image_plan
