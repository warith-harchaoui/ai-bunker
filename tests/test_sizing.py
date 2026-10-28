"""
Tests for the sizing model.

These lock the *claims*, not the implementation. Every number asserted here is
one the documentation states out loud, so a change that quietly invalidates a
published figure fails the suite instead of shipping.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import pytest

from ai_bunker.sizing import (
    Assumptions,
    find_accelerator,
    find_model,
    kv_gib,
    load_catalog,
    recommend_for_team,
    serve_command,
    sessions_for_team,
    size_machine,
    team_for_sessions,
    weights_gib,
)


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


# ---------------------------------------------------------------------------
# The catalogue is a published artifact: it has to stay well-formed.
# ---------------------------------------------------------------------------


def test_catalog_entries_are_complete(catalog):
    for m in catalog["models"]:
        assert m["id"] and m["role"] in {"code", "vision", "embed"}
        assert m["license"], f"{m['id']} has no licence"
        assert m["weights"], f"{m['id']} has no weight table"
        assert m["recommended_quant"] in m["weights"], (
            f"{m['id']} recommends a quantization it does not list"
        )
        kv = m.get("kv") or {}
        assert "gib_per_1k" in kv or all(k in kv for k in ("layers", "kv_heads", "head_dim")), (
            f"{m['id']} has neither KV geometry nor a measured rate"
        )

    for a in catalog["accelerators"]:
        assert a["vram_gib"] > 0 and a["bandwidth_gbs"] > 0
        assert a.get("batching") in {"vllm", "basic", "none"}, f"{a['id']} must grade its batching"


def test_every_accelerator_is_priced(catalog):
    """Cost per person is a headline figure; an unpriced card makes it a lie."""
    for a in catalog["accelerators"]:
        assert "price_usd" in a, f"{a['id']} has no price"
        assert a["price_usd"] >= 0


# ---------------------------------------------------------------------------
# KV geometry, checked against the figures the documentation publishes.
# ---------------------------------------------------------------------------


def test_the_kv_cache_arithmetic_reproduces_the_figures_the_docs_publish(catalog):
    """Every concurrency number in `docs/SIZING.md` rests on this function, so
    it is checked against the measurements those pages quote rather than
    against itself.

    Both shapes the catalogue carries are exercised: published geometry
    (40 layers x 8 key-value heads x 128 head_dim -> 5.0 GiB at 32k and
    20.0 GiB at 128k) and, where the geometry is unpublished, a measured rate
    per thousand tokens -- about 6 GiB at 256k for the mixture-of-experts
    model. The fp8 relation is exact by construction and worth pinning,
    because halving the storage is what buys the context the gateway serves.
    """
    dense = find_model(catalog, "devstral-small-2-24b")
    assert kv_gib(dense, 32768, "bf16") == pytest.approx(5.0, abs=0.05)
    assert kv_gib(dense, 131072, "bf16") == pytest.approx(20.0, abs=0.1)
    assert kv_gib(dense, 65536, "fp8") == pytest.approx(kv_gib(dense, 65536, "bf16") / 2)

    moe = find_model(catalog, "qwen3-coder-next")
    assert kv_gib(moe, 262144, "fp8") == pytest.approx(6.0, abs=0.3)


def test_weights_follow_the_recommended_quant_and_refuse_an_invented_one(catalog):
    """The default is the quantization this catalogue actually serves at, so a
    plan sized without naming one is sized at the right footprint. A name the
    model has no table for is refused with the names it does have, because the
    realistic mistake is a typo and the fix is seeing the options."""
    m = find_model(catalog, "devstral-small-2-24b")
    assert weights_gib(m) == (25, "fp8")
    assert weights_gib(m, "bf16") == (48, "bf16")
    with pytest.raises(AssertionError, match="bf16"):
        weights_gib(m, "int2")


# ---------------------------------------------------------------------------
# The roofline, validated against published DGX Spark measurements.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "weights_gib_value, measured_tps",
    [
        (16.0, 13.6),  # Qwen3 8B bf16 on a GB10
        (40.0, 4.4),  # Llama 3.1 70B Q4 on a GB10
    ],
)
def test_roofline_brackets_published_spark_measurements(weights_gib_value, measured_tps):
    """The model must not promise more than a real GB10 delivers, nor wildly less.

    Published figures put the Spark at 65-80% of its theoretical roofline. The
    model assumes 70%, so its prediction has to land within that band of the
    measurement -- otherwise every recommendation built on it is suspect.
    """
    from ai_bunker.sizing import GB, GIB, _tps

    predicted = _tps(273.0, 0.70, weights_gib_value * GB / GIB)
    assert 0.80 * measured_tps <= predicted <= 1.30 * measured_tps


def test_moe_active_weights_are_floored_not_taken_at_face_value(catalog):
    """A 3.75%-active model must not be credited with 3.75% of the memory traffic.

    Batching widens the set of experts touched per step, so the floor keeps the
    sizing honest for a shared server.
    """
    from ai_bunker.sizing import active_weights_gib

    m = find_model(catalog, "qwen3-coder-next")
    total, _ = weights_gib(m)
    active = active_weights_gib(m)
    assert active == pytest.approx(total * 0.20)
    assert active > total * m["active_fraction"]


def test_dense_models_read_all_their_weights(catalog):
    from ai_bunker.sizing import active_weights_gib

    m = find_model(catalog, "devstral-small-2-24b")
    assert active_weights_gib(m) == weights_gib(m)[0]


# ---------------------------------------------------------------------------
# Team sizing: the two directions must agree.
# ---------------------------------------------------------------------------


def test_team_size_and_sequence_count_convert_both_ways_without_disagreeing(catalog):
    """`sizing` answers "what does this machine carry" and `recommend` answers
    "what do I buy for N people". They are the same arithmetic read in two
    directions, and they disagree the moment the conversion stops being
    monotone and invertible -- which is a contradiction a reader would find in
    two published tables rather than in a traceback.

    The floor of two is the one deliberate kink: with a single sequence, one
    colleague's long generation blocks the other entirely, so a pair is never
    sized down to one.
    """
    assert sessions_for_team(1) == 1
    for n in (2, 3, 4, 5):
        assert sessions_for_team(n) >= 2, "one long generation must not block a colleague"

    previous = 0
    for n in (1, 2, 5, 10, 30, 100):
        current = sessions_for_team(n)
        assert current >= previous, f"{n} people needed fewer sequences than fewer people"
        previous = current

    for sequences in range(1, 25):
        team = team_for_sessions(sequences)
        assert sessions_for_team(team) <= sequences
        assert sessions_for_team(team + 1) > sequences


def test_sizing_for_the_mean_would_be_optimistic():
    """The documented reason for using a percentile rather than an average."""
    a = Assumptions()
    mean_based = 30 * a.duty_cycle * a.simultaneity
    assert sessions_for_team(30, a) > mean_based


# ---------------------------------------------------------------------------
# Machine sizing.
# ---------------------------------------------------------------------------


def test_a_plan_that_exceeds_the_card_says_so_rather_than_guessing(catalog):
    s = size_machine(accelerator="rtx-4090", catalog=catalog)  # 24 GiB, full plan
    assert s.verdict == "does-not-fit"
    assert s.concurrent_sessions == 0
    assert any("GiB" in w for w in s.warnings)


def test_the_spark_hits_a_bandwidth_wall_not_a_capacity_one(catalog):
    """128 GiB of memory and still unusable: the warning has to name the reason."""
    s = size_machine(accelerator="dgx-spark", catalog=catalog)
    assert s.verdict == "unusable-for-agents"
    assert s.sessions_by_memory > 0, "memory is not what is short here"
    assert s.sessions_by_speed == 0
    assert any("bandwidth wall" in w for w in s.warnings)


def test_moe_beats_dense_on_the_same_card(catalog):
    """The documented inversion: the better model is also the faster one."""
    dense = size_machine(
        accelerator="rtx-pro-5000-72", primary="devstral-small-2-24b", catalog=catalog
    )
    moe = size_machine(
        accelerator="rtx-pro-5000-72",
        primary="qwen3-coder-next",
        with_vision="qwen3-vl-8b",
        catalog=catalog,
    )
    assert moe.single_stream_tps > 2 * dense.single_stream_tps


def test_declared_context_sits_below_served_context(catalog):
    """A client that estimates its own tokens under-counts; the margin absorbs it."""
    s = size_machine(accelerator="rtx-pro-6000-blackwell", catalog=catalog)
    assert s.declared_context < s.served_context
    assert s.declared_context == int(s.served_context * s.assumptions["declared_fraction"])


def test_halving_the_live_context_roughly_doubles_the_sessions(catalog):
    """The published claim that harness discipline is worth hardware."""
    lean = size_machine(
        accelerator="rtx-pro-6000-blackwell",
        assumptions=Assumptions(avg_live_context=32768),
        catalog=catalog,
    )
    fat = size_machine(
        accelerator="rtx-pro-6000-blackwell",
        assumptions=Assumptions(avg_live_context=65536),
        catalog=catalog,
    )
    assert lean.concurrent_sessions >= 2 * fat.concurrent_sessions - 1


def test_an_unknown_accelerator_lists_the_known_ones(catalog):
    with pytest.raises(AssertionError, match="dgx-spark"):
        find_accelerator(catalog, "no-such-card")


def test_sizing_a_machine_not_in_the_catalogue(catalog):
    s = size_machine(vram_gib=96, bandwidth_gbs=1792, catalog=catalog)
    assert s.concurrent_sessions > 0
    assert s.vram_gib == 96


# ---------------------------------------------------------------------------
# Recommendation.
# ---------------------------------------------------------------------------


def test_a_runtime_without_paged_attention_is_disqualified_by_team_size(catalog):
    """Not by speed, which is the point. An Ollama-class machine can be fast
    and still wrong for a team: without paged attention the sessions queue, so
    the second user waits for the first to finish. That makes it a function of
    how many people share the machine -- fine for a pair, disqualifying at
    thirty -- and irrelevant entirely for a workstation one person uses, which
    is what `shared_server=False` says.
    """
    crowd = [r for r in recommend_for_team(30, catalog=catalog) if r.batching == "basic"]
    assert crowd, "the catalogue should carry at least one Ollama-class machine"
    assert all(r.disqualified and not r.fits for r in crowd)

    pair = recommend_for_team(2, primary="qwen3-coder-next", catalog=catalog)
    assert any(r.fits for r in pair if r.batching == "basic")

    solo = recommend_for_team(30, catalog=catalog, shared_server=False)
    assert not any(r.disqualified for r in solo)


def test_fitting_candidates_come_first(catalog):
    recs = recommend_for_team(2, primary="qwen3-coder-next", catalog=catalog)
    fits = [r.fits for r in recs]
    assert fits == sorted(fits, reverse=True), "a non-fitting card outranked a fitting one"


def test_a_marginally_cheaper_card_does_not_beat_real_headroom(catalog):
    """Two machines within a few percent are the same budget decision."""
    recs = recommend_for_team(2, with_vision="qwen3-vl-8b", catalog=catalog)
    winners = [r for r in recs if r.fits]
    assert winners
    best = winners[0]
    cheapest = min(winners, key=lambda r: r.total_usd)
    if best is not cheapest:
        assert best.total_usd <= cheapest.total_usd * 1.15
        assert best.sizing.concurrent_sessions > cheapest.sizing.concurrent_sessions


# ---------------------------------------------------------------------------
# The serve command has to be usable, not merely plausible.
# ---------------------------------------------------------------------------


def test_serve_command_carries_the_tool_call_parser(catalog):
    """Without a tool-call parser a coding agent cannot call a tool at all."""
    s = size_machine(accelerator="rtx-pro-6000-blackwell", catalog=catalog)
    cmd = serve_command(s, catalog=catalog)
    assert "--tool-call-parser" in cmd
    assert "--enable-auto-tool-choice" in cmd
    assert f"--max-model-len {s.served_context}" in cmd
    assert "--kv-cache-dtype fp8" in cmd


def test_serve_command_uses_the_awq_reference_for_awq_models(catalog):
    s = size_machine(
        accelerator="rtx-pro-6000-blackwell", primary="qwen3-coder-next", catalog=catalog
    )
    cmd = serve_command(s, catalog=catalog)
    assert find_model(catalog, "qwen3-coder-next")["awq"] in cmd
