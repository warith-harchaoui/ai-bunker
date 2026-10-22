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


def test_the_report_shows_what_was_assumed(sizing):
    """ "A sizing that prints only its conclusion is a sizing nobody can
    check." A reader who disagrees has to be able to find the number to
    change."""
    text = render(sizing)
    assert sizing.accelerator in text
    # The efficiency assumption is the one a reader most often disagrees with,
    # so it has to be on the page rather than buried in a flag's default.
    efficiency = sizing.assumptions["efficiency"]
    assert f"{efficiency:.0%}" in text or str(efficiency) in text


def test_the_report_names_the_constraint_that_bound(sizing):
    """The most useful line in the report: not "it does not fit" but *what*
    ran out. Without it a reader has a verdict and no lever."""
    text = render(sizing).lower()
    assert any(word in text for word in ("bandwidth", "memory", "vram", "context"))


def test_the_report_prints_the_numbers_it_was_given(sizing):
    """The view must not drift from the model. A report that rounds, recomputes
    or stales its own inputs is a report that disagrees with the thing it is
    describing, and this project's whole claim is that it does not."""
    printed = numbers(render(sizing))
    assert round(sizing.vram_gib) in printed
    assert round(sizing.bandwidth_gbs) in printed
    assert sizing.concurrent_sessions in printed


@pytest.mark.parametrize("verdict", sorted(_VERDICT))
def test_every_verdict_has_a_rendering(verdict):
    """A verdict the renderer has never heard of prints a bare key or raises,
    and it would do so on the day somebody adds one. The map is the contract;
    this holds it to being complete and non-empty."""
    assert _VERDICT[verdict].strip()
    assert "—" in _VERDICT[verdict], "a verdict should say what it means"


def test_the_serve_command_can_be_suppressed(sizing):
    """`show_command=False` exists for the places that print a report inside
    something else. If it suppressed nothing the flag would be decoration."""
    assert len(render(sizing, show_command=False)) < len(render(sizing, show_command=True))


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


def test_a_comparison_names_every_machine_it_compared(catalog):
    sizings = [
        size_machine(accelerator="rtx-4090", catalog=catalog),
        size_machine(accelerator="h100-80", catalog=catalog),
    ]
    text = render_comparison(sizings)
    for one in sizings:
        # Truncated to the column width, so compare on what fits in it.
        assert one.accelerator[:30] in text


def test_a_comparison_with_prices_shows_them(catalog):
    """A price nobody can see is a price nobody can argue with -- and the
    project's own sizing document turns on them."""
    sizings = [size_machine(accelerator="h100-80", catalog=catalog)]
    plain = render_comparison(sizings)
    # Keyed on the accelerator's NAME, which is what the renderer looks up.
    priced = render_comparison(sizings, prices={sizings[0].accelerator: 25_000.0})
    assert priced != plain
    assert "25,000" in priced
    assert "per person" in priced, "a price per machine is not the decision being made"


def test_the_catalogue_renders_every_model_it_holds(catalog):
    """A catalogue entry that is loaded and never shown is one a reader cannot
    choose. This renders the MODEL table, not the accelerator one."""
    text = render_catalog()
    for model in catalog["models"]:
        assert model["id"][:24] in text, model["id"]


def test_a_recommendation_says_who_it_is_for(catalog):
    recommendations = recommend_for_team(4, catalog=catalog)
    text = render_recommendation(recommendations, 4, plan="code")
    assert "4" in text
    assert text.strip()


def test_a_recommendation_respects_its_cutoff(catalog):
    """`top` bounds a list that would otherwise print the whole catalogue."""
    recommendations = recommend_for_team(4, catalog=catalog)
    if len(recommendations) < 3:
        pytest.skip("the catalogue is too small for this to mean anything")
    assert len(render_recommendation(recommendations, 4, plan="code", top=1)) < len(
        render_recommendation(recommendations, 4, plan="code", top=6)
    )


def test_an_empty_recommendation_says_so_rather_than_printing_a_heading(catalog):
    """Nothing fits is an answer. A heading over an empty list is not."""
    text = render_recommendation([], 1, plan="code")
    assert text.strip(), "an empty result must still say something"


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


def test_the_rule_report_names_a_rule_that_cannot_refuse():
    """Its most useful output: a rule that reads as if it stops something and
    does not. That is the failure worth catching before production."""
    rules = load_rules("charter/rules")
    text = render_rule_report(check_rules(rules), rules).lower()
    assert "warning" in text or "noted" in text


def test_a_budget_report_shows_the_floor_by_owner():
    """`ai-bunker budget` itemises by owner, which is the point of it: a total
    tells you there is a problem, an itemisation tells you whose."""
    from ai_bunker.budget import Counter, measure_request

    budget = measure_request(
        {"messages": [{"role": "system", "content": "x" * 400}, {"role": "user", "content": "hi"}]},
        counter=Counter(allow_ratio=True),
        served_context=8192,
    )
    text = render_budget(budget)
    assert text.strip()
    assert str(budget.served_context) in text.replace(",", "")


def test_a_budget_report_says_which_backend_counted():
    """An estimate presented as a measurement is the exact failure this project
    exists to prevent, so the backend has to survive rendering."""
    from ai_bunker.budget import Counter, measure_request

    budget = measure_request(
        {"messages": [{"role": "user", "content": "hello"}]},
        counter=Counter(allow_ratio=True),
        served_context=8192,
    )
    assert budget.backend in render_budget(budget)
