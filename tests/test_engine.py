"""
Tests for delegating the model choice to best-engine-ai-helper.

The claim under test is one this repository published for several releases and
did not honour: *ai-bunker describes its needs in a brief and lets the helper
choose; it never hardcodes a model name.* It was false in six places. These
lock the version that is true, and they lock the three things that make the
delegation worth anything rather than a wrapper:

1. **The task description is an input, not a comment.** The helper parses it to
   pick a scoring axis, so a rewrite that reads better and ranks worse has to
   fail here.
2. **The choice moves with the machine**, and reproduces the published study:
   the 72 GiB card holds the 80B, the 48 GiB one does not.
3. **The plan is chosen against a running budget.** Three models that each fit
   the card do not necessarily fit it together, and asking per-slot is how the
   cheapest card that holds the best model became `does-not-fit`.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import pytest

from ai_bunker.engine import (
    ASK,
    LEAN_TOLERANCE,
    OVERHEAD_GIB,
    ROLE_KINDS,
    TASK,
    VISION_TASK,
    as_helper_entries,
    choose,
    resolve_plan,
)
from ai_bunker.sizing import find_model, load_catalog, size_machine


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


@pytest.fixture(scope="module")
def helper():
    return pytest.importorskip("best_engine_ai_helper")


# ---------------------------------------------------------------------------
# No literals left.
# ---------------------------------------------------------------------------


def test_no_model_name_is_hardcoded_in_the_package():
    """The defect this module exists to remove, asserted over the source.

    Six literals across `sizing.py` and `cli.py` used to contradict the
    README's own sentence. The catalogue is data and `engine.py` names models
    in its prose, so both are exempt; everything else must ask.
    """

    from ai_bunker.adopt import ROOT

    offenders: list[str] = []
    for path in sorted((ROOT / "ai_bunker").glob("*.py")):
        if path.name == "engine.py":  # its docstring explains the literals it removed
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if "default=" not in code and ": str = " not in code and "str | None = " not in code:
                continue
            for model in load_catalog()["models"]:
                if f'"{model["id"]}"' in code:
                    offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert offenders == [], "a model name is hardcoded as a default:\n" + "\n".join(offenders)


def test_the_sentinel_is_a_word_because_none_already_means_something():
    """`None` means "leave this model out of the plan", and it has to keep
    meaning that -- so "ask the helper" needs its own spelling."""
    assert ASK == "auto"
    code, vision, embed, made = resolve_plan(
        primary=ASK, with_vision=None, with_embeddings=None, vram_gib=96
    )
    assert code
    assert vision is None and embed is None
    assert [c.role for c in made] == ["code"]


# ---------------------------------------------------------------------------
# The task description is an input.
# ---------------------------------------------------------------------------


def test_the_task_description_selects_the_code_axis(helper):
    """This is the sentence ai-bunker uses to describe itself to another
    program, and the parse decides which benchmark the ranking reads. Phrase it
    loosely and the helper ranks on its general axis, which would recommend a
    good conversationalist to a machine that has to emit patches."""
    parsed = helper.parse_task(TASK)
    assert parsed["application"] == "code"
    assert parsed["kinds"] == ["llm"]


def test_the_vision_task_asks_for_vision_and_not_for_text_recognition(helper):
    """An earlier phrasing said "scanned documents" and the helper answered
    `ocr`, which is a different axis and a different model. This project's
    vision slot is for looking at a running application and returning a
    schema."""
    parsed = helper.parse_task(VISION_TASK)
    assert parsed["vlm_application"] == "vision"
    assert "vlm" in parsed["kinds"]


def test_the_task_describes_this_project_rather_than_a_generic_model():
    """A description that would fit any project would rank for any project."""
    for word in ("coding", "tool", "schema", "context"):
        assert word in TASK.lower(), f"the task description never mentions {word}"


# ---------------------------------------------------------------------------
# Translating the catalogue.
# ---------------------------------------------------------------------------


def test_every_catalogue_model_survives_the_translation(catalog):
    entries = as_helper_entries(catalog)
    assert len(entries) == len(catalog["models"])
    for entry in entries:
        assert entry["id"] and entry["kind"] in set(ROLE_KINDS.values())
        assert entry["weights_gib"] > 0, entry["id"]
        assert entry["ram_gb"] >= entry["weights_gib"], "GiB must convert up to GB"


def test_the_vision_benchmark_is_mapped_onto_the_axis_the_helper_reads(catalog):
    """The bug this catches: `openvlm_average` is what this catalogue records
    and `vision` is what the helper scores, so until they were joined the
    vision slot was ordered by accident."""
    by_id = {e["id"]: e for e in as_helper_entries(catalog)}
    assert by_id["qwen3-vl-32b"]["benchmarks"]["vision"] == 87
    assert by_id["qwen3-vl-8b"]["benchmarks"]["vision"] == 80


def test_the_code_benchmark_is_mapped_too(catalog):
    by_id = {e["id"]: e for e in as_helper_entries(catalog)}
    assert by_id["qwen3-coder-next"]["benchmarks"]["code"] == 70.6
    assert by_id["devstral-small-2-24b"]["benchmarks"]["code"] == 68.0


def test_structured_output_is_read_from_the_tool_call_flags(catalog):
    """A coding agent's tool call is constrained decoding, and a model served
    without a tool-call parser cannot emit one whatever its weights can do.
    Inferred from the flags so there is one source of truth, not two."""
    by_id = {e["id"]: e for e in as_helper_entries(catalog)}
    assert by_id["devstral-small-2-24b"]["structured_output"] is True
    assert by_id["qwen3-coder-next"]["structured_output"] is True
    assert by_id["bge-m3"]["structured_output"] is False


def test_the_hugging_face_reference_is_the_join_between_the_two_catalogues(catalog):
    """`vllm_id` is the field the helper's own catalogue carries, and `hf` is
    what this one calls the same thing. Without the join the two worlds cannot
    refer to one model."""
    by_id = {e["id"]: e for e in as_helper_entries(catalog)}
    assert (
        by_id["devstral-small-2-24b"]["vllm_id"]
        == find_model(catalog, "devstral-small-2-24b")["hf"]
    )


# ---------------------------------------------------------------------------
# The choice moves with the machine.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "vram_gib,expected",
    [
        (96, "qwen3-coder-next"),
        (72, "qwen3-coder-next"),
        (48, "devstral-small-2-24b"),
    ],
)
def test_the_choice_follows_the_target_machine(helper, vram_gib, expected):
    """And it reproduces `docs/SIZING.md` without being told to: the 72 GiB
    card is the cheapest NVIDIA one that holds the best coder, and the 48 GiB
    card cannot. That study was argued by hand; this derives it."""
    choice = choose("code", vram_gib=vram_gib)
    assert choice.asked is True
    assert choice.model_id == expected


def test_a_machine_too_small_for_anything_says_so_rather_than_guessing(helper):
    """A silent fallback to a literal is the defect this module removes, so
    replacing one silent literal with another would be no improvement."""
    choice = choose("code", vram_gib=8)
    assert choice.asked is False
    assert "fits" in choice.reason
    assert choice.warnings and "nothing fits" in choice.warnings[0]


def test_the_budget_leaves_room_for_the_cache_the_machine_is_for(helper):
    """Weights that exactly fill a card leave nowhere for the key-value cache,
    which is the thing that makes the machine serve anybody."""
    entries = {e["id"]: e for e in as_helper_entries()}
    biggest = max(entries.values(), key=lambda e: e["weights_gib"])
    just_short = biggest["weights_gib"] + OVERHEAD_GIB - 0.1
    choice = choose("code", vram_gib=just_short)
    assert choice.model_id != biggest["id"] or choice.asked is False


# ---------------------------------------------------------------------------
# The anti-greed rule on the co-resident slots.
# ---------------------------------------------------------------------------


def test_the_vision_slot_takes_the_lean_model_so_the_coder_can_be_good(helper):
    """The helper's own `pick` names this the anti-greed rule, and gives the
    reason this project needs it: footprint "is paid on every run and competes
    with the caller's own workload". Here it competes with the coder."""
    choice = choose("vision", vram_gib=96)
    assert choice.model_id == "qwen3-vl-8b"
    entries = {e["id"]: e for e in as_helper_entries()}
    lean, greedy = entries["qwen3-vl-8b"], entries["qwen3-vl-32b"]
    # The lean one is genuinely worse, and within tolerance of the better one.
    assert lean["benchmarks"]["vision"] < greedy["benchmarks"]["vision"]
    assert greedy["benchmarks"]["vision"] - lean["benchmarks"]["vision"] <= LEAN_TOLERANCE


def test_the_code_slot_does_not_apply_it(helper):
    """`docs/SIZING.md` spends a section arguing that spare memory should buy a
    better coder. The coder is therefore the one slot that takes the best."""
    assert choose("code", vram_gib=96, lean=False).model_id == "qwen3-coder-next"
    assert choose("code", vram_gib=96).model_id == "qwen3-coder-next"


def test_the_embedder_is_answered_without_a_ranking_of_one(catalog):
    """There is one embedder in the catalogue, the helper ranks `llm` and
    `vlm` kinds, and an embedder is neither."""
    choice = choose("embed", vram_gib=96, catalog=catalog)
    assert choice.model_id == "bge-m3"
    assert choice.asked is False
    assert "theatre" in choice.reason


# ---------------------------------------------------------------------------
# The running budget.
# ---------------------------------------------------------------------------


def test_the_plan_is_resolved_against_what_is_left_not_the_whole_card(helper):
    """The regression that produced this function's docstring: on a 72 GiB card
    the best coder, the vision model and the embedder each fit alone and did
    not fit together, so the cheapest card that holds the best model reported
    `does-not-fit`."""
    sizing = size_machine(accelerator="rtx-pro-5000-72")
    assert sizing.verdict != "does-not-fit"
    assert sizing.primary == "qwen3-coder-next"
    assert sizing.resident_weights_gib <= 72 - OVERHEAD_GIB


def test_the_coder_gets_the_remainder_not_the_first_claim(helper):
    """Cheapest first, so the slot spare memory is meant for receives it."""
    code, vision, embed, made = resolve_plan(vram_gib=72)
    assert (code, vision, embed) == ("qwen3-coder-next", "qwen3-vl-8b", "bge-m3")
    assert [c.role for c in made] == ["embed", "vision", "code"]


def test_a_named_model_still_spends_the_budget(helper, catalog):
    """A slot the caller pinned is not free, and treating it as free would size
    the remaining slots against memory that is already committed."""
    code, vision, _embed, _made = resolve_plan(
        primary=ASK, with_vision="qwen3-vl-32b", with_embeddings=None, vram_gib=72
    )
    assert vision == "qwen3-vl-32b"
    # 72 - 35 (pinned vision) - 4 overhead leaves 33, which the 45 GiB coder
    # cannot have; so pinning the greedy vision model costs the better coder.
    assert code == "devstral-small-2-24b"


def test_the_published_verdicts_still_hold(helper):
    """Every figure `docs/SIZING.md` publishes rests on these verdicts, and the
    plan is now chosen rather than written down -- so this is what notices if
    the helper ever starts answering differently."""
    expected = {
        "rtx-pro-6000-blackwell": "comfortable",
        "rtx-pro-5000-72": "comfortable",
        "rtx-pro-5000-48": "workable",
        "rtx-4090": "does-not-fit",
        "mac-studio-m3-ultra-96": "comfortable",
        "dgx-spark": "unusable-for-agents",
    }
    for accelerator, verdict in expected.items():
        assert size_machine(accelerator=accelerator).verdict == verdict, accelerator


# ---------------------------------------------------------------------------
# Degrading honestly.
# ---------------------------------------------------------------------------


def test_the_helper_being_absent_is_reported_rather_than_hidden(monkeypatch, catalog):
    """It is a declared dependency, so this should not happen -- which is
    exactly why it must say so rather than quietly pick something."""
    import builtins

    real_import = builtins.__import__

    def without_helper(name, *args, **kwargs):
        if name == "best_engine_ai_helper":
            raise ImportError("pretend it is not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_helper)
    choice = choose("code", vram_gib=96, catalog=catalog)
    assert choice.asked is False
    assert "not importable" in choice.reason
    assert choice.warnings
    # And it still names a model, so sizing keeps working offline.
    find_model(catalog, choice.model_id)


def test_a_helper_that_raises_is_not_fatal(monkeypatch, catalog, helper):
    """A recommendation is advice. Advice that throws should not take down an
    arithmetic command that can answer without it."""

    def boom(*args, **kwargs):
        raise RuntimeError("the catalogue is on fire")

    monkeypatch.setattr(helper, "rank", boom)
    choice = choose("code", vram_gib=96, catalog=catalog)
    assert choice.asked is False
    assert "could not rank" in choice.reason
    find_model(catalog, choice.model_id)


def test_an_unknown_role_is_refused(catalog):
    with pytest.raises(AssertionError) as caught:
        choose("translation", catalog=catalog)
    assert "code" in str(caught.value)


def test_a_choice_serialises(helper):
    import json

    payload = json.loads(json.dumps(choose("code", vram_gib=96).to_dict()))
    assert payload["model_id"] and payload["asked"] is True
