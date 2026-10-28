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
    """The helper, and only when it can do what these tests assert about it.

    The two packages in this suite are released separately, so the version
    that resolves at install time is not necessarily the one this was written
    against -- and a version floor cannot express that, because a working tree
    and the release it shares a number with are different code. The tests that
    assert a *specific* choice therefore ask whether the ranking exists, and
    skip rather than fail when it does not. The tests that assert ai-bunker
    degrades honestly do not take this fixture, so they run either way.
    """
    module = pytest.importorskip("best_engine_ai_helper")
    for name in ("rank", "available_memory", "parse_task"):
        if not hasattr(module, name):
            pytest.skip(f"the installed best-engine-ai-helper offers no {name}")
    return module


# ---------------------------------------------------------------------------
# No literals left.
# ---------------------------------------------------------------------------


def test_no_model_name_is_hardcoded_in_the_package():
    """The defect this module exists to remove, asserted over the source.

    Six literals across `sizing.py` and `cli.py` used to contradict the
    README's own sentence. The catalogue is data and `engine.py` names models
    in its prose, so both are exempt; everything else must ask.

    **Families count, not just ids.** The first version of this guard matched
    whole catalogue ids, and `adopt.py` kept `model: str = "devstral"` through
    it for several releases -- a model name by any reading, on the line that
    decides what every client kit asks the gateway for. So the family a
    catalogue id starts with is an offender too.
    """

    from ai_bunker.adopt import ROOT

    names: set[str] = set()
    for model in load_catalog()["models"]:
        ident = str(model["id"])
        names.add(ident)
        # `devstral-small-2-24b` -> `devstral`. The segment before the first
        # hyphen is how a family is written when somebody abbreviates one.
        names.add(ident.split("-", 1)[0])

    offenders: list[str] = []
    for path in sorted((ROOT / "ai_bunker").glob("*.py")):
        if path.name == "engine.py":  # its docstring explains the literals it removed
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("#", 1)[0]
            if "default=" not in code and ": str = " not in code and "str | None = " not in code:
                continue
            if any(f'"{name}"' in code for name in names):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert offenders == [], "a model name is hardcoded as a default:\n" + "\n".join(offenders)


def test_the_sentinel_is_a_word_because_none_already_means_something():
    """`None` means "leave this model out of the plan", and it has to keep
    meaning that -- so "ask the helper" needs its own spelling."""
    assert ASK == "auto"
    settled = resolve_plan(primary=ASK, with_vision=None, with_embeddings=None, vram_gib=96)
    assert settled.code
    assert settled.vision is None and settled.embeddings is None and settled.image is None
    assert [c.role for c in settled.choices] == ["code"]


# ---------------------------------------------------------------------------
# The task description is an input.
# ---------------------------------------------------------------------------


def test_the_task_description_is_what_picks_the_ranking_axis(helper):
    """The sentence ai-bunker uses to describe itself to another program, and
    the four things that have to be true of it for the delegation to mean
    anything.

    It has to *parse* the way this project needs: `TASK` on the code axis,
    `VISION_TASK` on vision rather than `ocr` -- an earlier phrasing said
    "scanned documents" and got `ocr`, a different axis and a different model.
    It has to be *specific*, because a description that would fit any project
    would rank for any project. And it has to actually *reach the ranking*,
    which for several releases it did not: `choose` took a `task` argument,
    documented it, and ranked on a table indexed by role without ever reading
    it. The last assertion is the one that would have caught that -- a task
    the catalogue scores nothing on has to be reported, not silently ignored.
    """
    code = helper.parse_task(TASK)
    assert code["application"] == "code"
    assert code["kinds"] == ["llm"]

    vision = helper.parse_task(VISION_TASK)
    assert vision["vlm_application"] == "vision"
    assert "vlm" in vision["kinds"]

    for word in ("coding", "tool", "schema", "context"):
        assert word in TASK.lower(), f"the task description never mentions {word}"

    # The words reach the ranking. An OCR task parses to an axis this
    # catalogue records no benchmark for, so the slot falls back to its
    # default and says so -- which is only observable if `task` is read.
    ocr = choose(
        "vision",
        vram_gib=80,
        task="Read scanned paper documents and extract their text accurately.",
    )
    assert ocr.axis == "vision"
    assert any("ocr" in w for w in ocr.warnings), ocr.warnings

    # And the shipped strings leave no warning, because they parse onto the
    # axis this catalogue actually scores.
    assert choose("vision", vram_gib=80).warnings == []
    assert choose("code", vram_gib=80).warnings == []


# ---------------------------------------------------------------------------
# Translating the catalogue.
# ---------------------------------------------------------------------------


def test_the_catalogue_translates_into_every_field_the_ranking_reads(catalog):
    """The join between two catalogues, and every column it has to carry.

    Each field is taken from the nearest equivalent rather than invented, and
    each one has a way of being silently wrong:

    - **benchmarks**, mapped by name. `openvlm_average` is what this catalogue
      records and `vision` is what the helper scores, so until they were
      joined the vision slot was ordered by accident -- a missing key ranks as
      zero rather than failing.
    - **structured_output**, inferred from the tool-call flags. A coding
      agent's tool call is constrained decoding, and a model served without a
      parser cannot emit one whatever its weights can do. Inferred so there is
      one source of truth and not two that can disagree.
    - **vllm_id**, which is `hf` under the helper's name for it. Without this
      the two worlds cannot refer to the same model at all.
    - **ram_gb**, in gigabytes where this catalogue keeps gibibytes. Ignoring
      the factor would shift every budget comparison by 7% in the flattering
      direction.
    """
    entries = as_helper_entries(catalog)
    assert len(entries) == len(catalog["models"])
    by_id = {e["id"]: e for e in entries}

    for entry in entries:
        assert entry["id"] and entry["kind"] in set(ROLE_KINDS.values())
        assert entry["weights_gib"] > 0, entry["id"]
        assert entry["ram_gb"] >= entry["weights_gib"], "GiB must convert up to GB"

    assert by_id["qwen3-vl-32b"]["benchmarks"]["vision"] == 87
    assert by_id["qwen3-vl-8b"]["benchmarks"]["vision"] == 80
    assert by_id["qwen3-coder-next"]["benchmarks"]["code"] == 70.6
    assert by_id["devstral-small-2-24b"]["benchmarks"]["code"] == 68.0

    assert by_id["devstral-small-2-24b"]["structured_output"] is True
    assert by_id["qwen3-coder-next"]["structured_output"] is True
    assert by_id["bge-m3"]["structured_output"] is False

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
    settled = resolve_plan(vram_gib=72)
    assert (settled.code, settled.vision, settled.embeddings) == (
        "qwen3-coder-next",
        "qwen3-vl-8b",
        "bge-m3",
    )
    # No image slot unless one was asked for: it is the only slot that is off
    # by default, because its memory would come out of the coder's.
    assert settled.image is None
    assert [c.role for c in settled.choices] == ["embed", "vision", "code"]


def test_a_named_model_still_spends_the_budget(helper, catalog):
    """A slot the caller pinned is not free, and treating it as free would size
    the remaining slots against memory that is already committed."""
    settled = resolve_plan(
        primary=ASK, with_vision="qwen3-vl-32b", with_embeddings=None, vram_gib=72
    )
    code, vision = settled.code, settled.vision
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


# ---------------------------------------------------------------------------
# What continuous integration actually installs.
# ---------------------------------------------------------------------------


def test_importing_this_package_does_not_drag_in_a_deep_learning_stack():
    """The promise that keeps the gateway's start-up and its continuous
    integration light.

    `best-engine-ai-helper` carries `airllm` as a core dependency now, which
    means torch, transformers and accelerate. This project is a proxy: it never
    loads a model, and a gateway that pays seconds of import time -- or a lane
    that pays gigabytes of download -- for a capability it never uses is paying
    for nothing. Every reference to the helper is therefore inside a function.
    """
    import subprocess
    import sys

    probe = (
        "import sys, ai_bunker, ai_bunker.sizing, ai_bunker.engine, ai_bunker.gateway; "
        "print(','.join(m for m in "
        "('torch','transformers','airllm','diffusers','best_engine_ai_helper') "
        "if m in sys.modules))"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out == "", f"importing ai_bunker pulled in: {out}"


def test_the_choice_degrades_honestly_when_the_helper_is_older(monkeypatch, catalog):
    """A helper without the ranking is the shape of a version skew between two
    separately released packages, and it must not be a crash. It must also not
    be silent: the whole point of this module is that a choice nobody delegated
    says so."""
    import types

    stub = types.ModuleType("best_engine_ai_helper")  # no `rank`, no `available_memory`
    monkeypatch.setitem(__import__("sys").modules, "best_engine_ai_helper", stub)
    choice = choose("code", vram_gib=96, catalog=catalog)
    assert choice.asked is False
    assert "predates" in choice.reason
    assert choice.warnings
    find_model(catalog, choice.model_id)


def test_sizing_still_works_with_no_helper_at_all(monkeypatch):
    """`ai-bunker sizing` is arithmetic over a committed catalogue. It should
    answer on a machine that has never heard of the helper -- reporting that
    the choice was not delegated, and otherwise working."""
    import builtins

    real_import = builtins.__import__

    def without_helper(name, *args, **kwargs):
        if name == "best_engine_ai_helper":
            raise ImportError("not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_helper)
    sizing = size_machine(accelerator="rtx-pro-6000-blackwell")
    assert sizing.verdict != "does-not-fit"
    assert sizing.primary
    assert any("best-engine-ai-helper" in w for w in sizing.warnings)


# ---------------------------------------------------------------------------
# The reported reasoning is about the slot it belongs to.
# ---------------------------------------------------------------------------


def test_every_slot_is_reported_on_the_axis_it_was_ranked_on(helper):
    """The bug: `choose` computed the axis, used it for the anti-greed
    tie-break, and then hardcoded `code` in all three places that report.

    Vision models leave the code column empty, so the vision slot published
    `benchmark None`, `score=None` and a rejected list of nulls -- every
    figure a reader needs to argue with the anti-greed trade, absent. The code
    slot looked fine for the same reason it was broken: it is the column that
    was hardcoded.

    The rejected list also has to distinguish what the card could have held
    from what it could not. "Nothing better exists" and "something better
    exists and does not fit" are different answers, and only one of them is an
    argument for a bigger card.
    """
    vision = choose("vision", vram_gib=96)
    assert vision.axis == "vision"
    assert vision.score and vision.score > 0
    assert f"vision benchmark {vision.score:g}" in vision.reason
    assert vision.rejected and all(r["score"] for r in vision.rejected)

    code = choose("code", vram_gib=96)
    assert code.axis == "code"
    assert (
        code.score == find_model(load_catalog(), code.model_id)["benchmarks"]["swe_bench_verified"]
    )
    assert all(r["affordable"] for r in code.rejected), "everything fits 96 GiB"

    tight = choose("code", vram_gib=48)
    assert any(not r["affordable"] for r in tight.rejected), "the 80B does not fit 48 GiB"


# ---------------------------------------------------------------------------
# The image slot, which is delegated whole.
# ---------------------------------------------------------------------------


def test_the_image_slot_is_answered_entirely_out_of_the_helpers_catalogue(helper, catalog):
    """The slot exists here and the entries deliberately do not.

    A diffusion pipeline's figures -- component footprints, a denoising step
    count, seconds per image -- are none of the columns `catalog/serving.yaml`
    is for, and the helper already carries both the entries and the
    arithmetic. So the choice comes back naming a model this project has never
    heard of, with a footprint and a timing only the helper could work out.
    """
    assert "image" in ROLE_KINDS
    assert [m for m in catalog["models"] if m.get("role") == "image"] == []

    if not hasattr(helper, "imagine_rank"):
        pytest.skip("the installed best-engine-ai-helper offers no image picker")

    choice = choose("image", vram_gib=80, bandwidth_gbs=3350.0)
    assert choice.asked is True
    assert choice.model_id and choice.hf
    assert choice.weights_gib and choice.weights_gib > 0
    assert choice.detail["steps"] and choice.detail["seconds_per_image"]
    assert choice.model_id in {str(e.get("id")) for e in helper.load_catalog()}

    # A model the helper's catalogue does not carry is refused by name rather
    # than planned as though it were free.
    settled = resolve_plan(
        primary=ASK,
        with_vision=None,
        with_embeddings=None,
        with_image="not-a-diffusion-model",
        vram_gib=96,
    )
    assert settled.image is None
    picture = next(c for c in settled.choices if c.role == "image")
    assert "no model" in picture.reason and picture.warnings


def test_the_image_slot_applies_the_anti_greed_rule_the_helper_does_not(helper):
    """`imagine_pick` takes the best image model that runs, which on a large
    card is the biggest pipeline in its catalogue. This is a gateway for coding
    agents: spare memory is supposed to buy a better coder, so the slot takes
    the leanest candidate within LEAN_TOLERANCE of the best."""
    if not hasattr(helper, "imagine_rank"):
        pytest.skip("the installed best-engine-ai-helper offers no image picker")
    plans = helper.imagine_rank(
        [e for e in helper.load_catalog() if e.get("kind") == "image"],
        budget_gb=200.0,
        bandwidth_gbs=3350.0,
    )
    greedy = helper.imagine_pick(plans)
    lean = choose("image", vram_gib=200, bandwidth_gbs=3350.0)
    assert lean.score is not None and greedy["score"] - lean.score <= LEAN_TOLERANCE
    chosen = next(p for p in plans if p["catalog_id"] == lean.model_id)
    assert chosen["resident_gb"] <= greedy["resident_gb"]


def test_the_image_slot_is_off_by_default_and_costs_the_coder_when_it_is_not(helper):
    """The only slot that is off unless asked for, and the trade is the reason.

    Its memory comes out of the coder's, and this gateway's first job is to
    serve a coder. On an 80 GiB card, asking for pictures drops the plan from
    the 80B to the dense 24B -- which is a decision an operator should be able
    to see in the report rather than discover from a slower agent.
    """
    assert resolve_plan(vram_gib=96).image is None

    if not hasattr(helper, "imagine_rank"):
        pytest.skip("the installed best-engine-ai-helper offers no image picker")

    without = resolve_plan(vram_gib=80, bandwidth_gbs=3350.0)
    with_pictures = resolve_plan(vram_gib=80, bandwidth_gbs=3350.0, with_image=ASK)
    assert with_pictures.image
    assert with_pictures.code != without.code
    code = next(c for c in with_pictures.choices if c.role == "code")
    assert any(not r["affordable"] for r in code.rejected)


def test_the_image_slot_answers_honestly_when_it_cannot_answer_fully(helper, monkeypatch):
    """Two degradations, and neither may be silent.

    With **no helper at all** there is no catalogue here to fall back to, so
    the slot is dropped -- and dropping it quietly would size a plan the
    machine never agreed to.

    With **no bandwidth** the timing is unknown, and `seconds_per_image` being
    None is what makes `usable` False. The warning explaining the unusable
    choice was formatting that None, which is a crash found by calling the
    slot the way a library caller would. "Could not be timed" and "too slow"
    are different sentences and it has to be able to say either.
    """
    if not hasattr(helper, "imagine_rank"):
        pytest.skip("the installed best-engine-ai-helper offers no image picker")

    # No bandwidth, and an accelerator named -- so there is nothing to borrow
    # this machine's figure for, which is the combination that crashed.
    monkeypatch.setattr(helper, "compute_profile", lambda: {}, raising=False)
    untimed = choose("image", vram_gib=96)
    assert untimed.model_id
    assert untimed.detail["seconds_per_image"] is None
    assert untimed.warnings and "could not be timed" in untimed.warnings[0]

    import types

    stub = types.ModuleType("best_engine_ai_helper")  # no imagine_* at all
    monkeypatch.setitem(__import__("sys").modules, "best_engine_ai_helper", stub)
    dropped = choose("image", vram_gib=96)
    assert dropped.asked is False
    assert dropped.model_id == ""
    assert dropped.warnings and "left out" in dropped.warnings[0]


def test_the_local_machines_bandwidth_is_borrowed_only_for_the_local_machine(helper):
    """Asked about this machine, the slot should time the answer on it. Asked
    about a catalogue accelerator, it must not: borrowing this laptop's
    bandwidth would report a number about the wrong machine, which is worse
    than reporting that it could not be timed."""
    if not hasattr(helper, "imagine_rank") or not hasattr(helper, "compute_profile"):
        pytest.skip("the installed best-engine-ai-helper offers no image picker")
    here = choose("image")
    named = choose("image", vram_gib=96)
    if (helper.compute_profile() or {}).get("bandwidth_gbs"):
        assert here.detail["seconds_per_image"]
    assert named.detail["seconds_per_image"] is None
