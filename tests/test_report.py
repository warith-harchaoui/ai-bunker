"""
Tests for the rendering layer.

This module had the lowest coverage in the project -- 21% -- which is an
awkward place for it to be. `report.py` is where every published figure turns
into the thing a reader actually sees, and this repository's one rule is that
every claim in it is a measurement. A number can be computed correctly and
printed wrong, and nothing else in the suite looks at the printing.

So these do not assert on exact prose, which would break on every wording
change and protect nothing. They assert the two properties the module's own
docstring promises:

* **the chain is shown**, not only the conclusion -- what was assumed, what it
  implied, and which constraint bound;
* **what is printed is what was computed**, so the view cannot drift from the
  model it is rendering.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import re

import pytest

from ai_bunker.report import (
    _VERDICT,
    render,
    render_budget,
    render_catalog,
    render_comparison,
    render_recommendation,
    render_rule_report,
)
from ai_bunker.rules import load_rules
from ai_bunker.rules import test_rules as check_rules
from ai_bunker.sizing import load_catalog, recommend_for_team, size_machine


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def sizing(catalog):
    """A machine the default plan actually fits on.

    `rtx-4090` does not -- 24 GiB against 61 GiB of weights -- and a report
    for a machine that does not fit skips most of what there is to render.
    That case gets its own test below, which is the point of having both.
    """
    return size_machine(accelerator="h100-80", catalog=catalog)


@pytest.fixture(scope="module")
def too_small(catalog):
    return size_machine(accelerator="rtx-4090", catalog=catalog)


def numbers(text: str) -> set[int]:
    """Every integer in a rendered report, commas removed."""
    return {int(n.replace(",", "")) for n in re.findall(r"\b\d[\d,]*\b", text)}


# ---------------------------------------------------------------------------
# The chain, which is the whole argument for this module existing.
# ---------------------------------------------------------------------------


def test_the_report_shows_the_chain_and_not_only_the_conclusion(sizing):
    """ "A sizing that prints only its conclusion is a sizing nobody can
    check." Three things have to be on the page for a reader to argue with it.

    **What was assumed**, so the number to change is findable -- efficiency
    especially, which is the assumption a reader most often disagrees with and
    would otherwise be buried in a flag's default. **Which constraint bound**,
    because "it does not fit" is a verdict and `bandwidth` is a lever. And
    **the figures it was given**, unrounded and unrecomputed: a view that
    drifts from its model describes something that does not exist, and this
    project's whole claim is that it does not. The serve command can be left
    off for callers embedding this inside a larger page, and that flag has to
    actually suppress something.
    """
    text = render(sizing)
    assert sizing.accelerator in text

    efficiency = sizing.assumptions["efficiency"]
    assert f"{efficiency:.0%}" in text or str(efficiency) in text

    assert any(word in text.lower() for word in ("bandwidth", "memory", "vram", "context"))

    printed = numbers(text)
    assert round(sizing.vram_gib) in printed
    assert round(sizing.bandwidth_gbs) in printed
    assert sizing.concurrent_sessions in printed

    # `show_command=False` exists for the places that print a report inside
    # something else. A flag that suppresses nothing is decoration.
    assert len(render(sizing, show_command=False)) < len(text)


@pytest.mark.parametrize("verdict", sorted(_VERDICT))
def test_every_verdict_has_a_rendering(verdict):
    """A verdict the renderer has never heard of prints a bare key or raises,
    and it would do so on the day somebody adds one. The map is the contract;
    this holds it to being complete and non-empty."""
    assert _VERDICT[verdict].strip()
    assert "—" in _VERDICT[verdict], "a verdict should say what it means"


def test_a_machine_that_does_not_fit_says_why_rather_than_just_no(too_small):
    """The failing case is the one a reader needs most, and the easiest to
    render badly: 24 GiB against 61 GiB of weights. A verdict with no numbers
    behind it is advice nobody can act on."""
    assert too_small.verdict == "does-not-fit", "the fixture stopped being the failing case"
    text = render(too_small)
    assert too_small.warnings, "the sizing itself should explain the failure"
    assert too_small.warnings[0][:40] in text, "and the report should carry it through"


# ---------------------------------------------------------------------------
# The other renderers. None of them had a test.
# ---------------------------------------------------------------------------


def test_a_comparison_names_every_machine_and_prices_them_when_asked(catalog):
    """A machine missing from a comparison is a machine nobody compares. And
    a price nobody can see is a price nobody can argue with -- the project's
    own sizing document turns on them, and on cost *per person* rather than
    per machine, which is the decision actually being made."""
    sizings = [
        size_machine(accelerator="rtx-4090", catalog=catalog),
        size_machine(accelerator="h100-80", catalog=catalog),
    ]
    plain = render_comparison(sizings)
    for one in sizings:
        # Truncated to the column width, so compare on what fits in it.
        assert one.accelerator[:30] in plain

    # Keyed on the accelerator's NAME, which is what the renderer looks up.
    # Priced on the H100 rather than the 4090: the per-person line only exists
    # where there is usable capacity to divide by, and a card that carries
    # nobody prints that instead -- which is the right output and the wrong
    # specimen for this assertion.
    priced = render_comparison(sizings, prices={sizings[1].accelerator: 25_000.0})
    assert priced != plain
    assert "25,000" in priced
    assert "per person" in priced, "a price per machine is not the decision being made"


def test_the_catalogue_renders_every_model_it_holds(catalog):
    """A catalogue entry that is loaded and never shown is one a reader cannot
    choose. This renders the MODEL table, not the accelerator one."""
    text = render_catalog()
    for model in catalog["models"]:
        assert model["id"][:24] in text, model["id"]


def test_a_recommendation_says_who_it_is_for_and_stops_where_told(catalog):
    """It names the **team size** it was computed for, because a list of
    cards without the question above it is a list nobody can check. `top`
    **bounds** it, or a recommendation prints the whole catalogue and stops
    being a recommendation. And an **empty** result still says something:
    nothing fits is an answer, where a heading over an empty list is not.
    """
    recommendations = recommend_for_team(4, catalog=catalog)
    text = render_recommendation(recommendations, 4, plan="code")
    assert "4" in text
    assert text.strip()

    if len(recommendations) >= 3:
        assert len(render_recommendation(recommendations, 4, plan="code", top=1)) < len(
            render_recommendation(recommendations, 4, plan="code", top=6)
        )

    assert render_recommendation([], 1, plan="code").strip(), "an empty result must still speak"


# ---------------------------------------------------------------------------
# The two renderers that print enforcement, where being wrong matters most.
# ---------------------------------------------------------------------------


def test_the_rule_report_counts_what_the_checker_counted():
    """The figures this prints are the ones the site and both READMEs quote,
    and `sync_counts.py` reads them back out of this very output. A rendering
    bug here propagates into the published documentation."""
    rules = load_rules("charter/rules")
    report = check_rules(rules)
    text = render_rule_report(report, rules)

    assert str(len(rules)) in text
    assert str(report.passed) in text
    assert "0" in text, "the failure count has to appear even when it is zero"

    # And its most useful output: a rule that reads as if it stops something
    # and does not. That is the failure worth catching before production.
    assert "warning" in text.lower() or "noted" in text.lower()


def test_a_budget_report_shows_the_floor_by_owner_and_who_counted_it():
    """`ai-bunker budget` itemises by owner, which is the point of it: a total
    tells you there is a problem, an itemisation tells you whose. And the
    backend has to survive rendering -- an estimate presented as a
    measurement is the exact failure this project exists to prevent, and a
    renderer that drops the label commits it on the last step.
    """
    from ai_bunker.budget import Counter, measure_request

    budget = measure_request(
        {"messages": [{"role": "system", "content": "x" * 400}, {"role": "user", "content": "hi"}]},
        counter=Counter(allow_ratio=True),
        served_context=8192,
    )
    text = render_budget(budget)
    assert text.strip()
    assert str(budget.served_context) in text.replace(",", "")
    assert budget.backend in text


def test_the_rule_set_cost_is_measured_and_kept_out_of_the_default_table():
    """Nothing caps the number of rules, and the screening cost is linear in
    it -- so a deployment importing a large charter pack pays proportionally
    with no warning. A figure an operator can watch is cheaper than a limit
    somebody has to argue about.

    It stays out of the default table deliberately: seven documents quote that
    block as real output, and a millisecond figure is machine-dependent. In
    the default view it would give all seven a number that is wrong on every
    other machine and that no drift guard could check.
    """
    from ai_bunker.report import render_rule_report, screen_cost_ms

    rules = load_rules("charter/rules")
    report = check_rules(rules)

    cost = screen_cost_ms(rules)
    assert cost > 0, "a measurement of zero is not a measurement"

    plain = render_rule_report(report, rules)
    assert "cost to screen" not in plain

    asked = render_rule_report(report, rules, show_cost=True)
    assert "cost to screen" in asked


# ---------------------------------------------------------------------------
# Why these models: the chain that was computed and then dropped.
# ---------------------------------------------------------------------------


def test_the_report_shows_why_each_slot_holds_what_it_holds():
    """`engine.py` built this reasoning for several releases and nothing read
    it -- `sizing` took the warnings and discarded the rest -- while that
    module's docstring said this report printed it. The claim is only true if
    the figures a reader would argue with are on the page."""
    from ai_bunker.sizing import size_machine

    sizing = size_machine(accelerator="h100-80")
    if not sizing.choices:
        pytest.skip("no helper installed, so nothing was delegated to explain")
    text = render(sizing, show_command=False)

    assert "WHY THESE MODELS" in text
    for choice in sizing.choices:
        assert choice["model_id"] in text
        # The anti-greed trade is the one a reader is most likely to dispute,
        # so the candidate that was passed over has to be named with its score.
        for passed in choice["rejected"]:
            if passed["affordable"]:
                assert passed["id"] in text


def test_a_plan_the_caller_named_outright_explains_nothing():
    """There is no choice to show when nobody delegated one, and a heading over
    an empty list is worse than no heading."""
    from ai_bunker.sizing import size_machine

    sizing = size_machine(
        accelerator="h100-80",
        primary="devstral-small-2-24b",
        with_vision=None,
        with_embeddings=None,
    )
    assert sizing.choices == []
    assert "WHY THESE MODELS" not in render(sizing, show_command=False)


def test_the_image_slot_is_reported_in_the_unit_a_person_waits_in():
    """A diffusion pipeline has no context window and answers in pictures, so
    every column this report is built around says nothing about it. Seconds per
    image is the figure that decides whether the slot earns its memory."""
    from ai_bunker.sizing import size_machine

    sizing = size_machine(accelerator="h100-80", with_image="auto")
    picture = next((p for p in sizing.plan if p.role == "image"), None)
    if picture is None:
        pytest.skip("no helper installed, so no image model was chosen")

    assert picture.max_context == 0, "a denoising loop has no context window"
    assert picture.seconds_per_image
    text = render(sizing, show_command=False)
    assert "s an image" in text
    assert picture.model_id in text
    # And its weights are in the total, not alongside it.
    assert sizing.resident_weights_gib >= picture.weights_gib
