"""
Tests for the layer-streaming fallback: the arithmetic, the decision, the socket.

These lock the *claims*, the way `test_sizing.py` does. Three of them are
claims this project makes nowhere else and that are easy to get backwards, so
they are asserted rather than trusted:

1. A streaming engine reads the **whole** checkpoint per token, not the active
   part, which inverts the mixture-of-experts recommendation the rest of the
   repository makes.
2. The page cache helps precisely in the regime where streaming should not be
   used at all, so a half-cached figure must never be reported as a storage
   one.
3. `auto` activates from the machine in front of it and `on` activates because
   a human said so -- and `on` still has to object when the model would have
   fitted.

The engine's own path is driven against a stub. That is a deliberate limit and
it is stated in `ai_bunker/airllm.py`: a real run needs a multi-gibibyte
checkpoint and an hour of wall clock to produce one paragraph, so what is
covered here is the HTTP surface, the templating, the stream framing and the
refusals -- never "the tokens are right".

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import json

import pytest

from ai_bunker.airllm import (
    Loaded,
    _loader,
    create_app,
    generate_stream,
    generate_text,
    is_local_checkpoint,
    load_engine,
    render_prompt,
)
from ai_bunker.cli import build_parser
from ai_bunker.fallback import (
    ASSUMED_LAYERS,
    COMPRESSION_BYTES,
    MODE_ALIASES,
    MODE_ENV_VAR,
    MODES,
    PREFETCH_DEPTH,
    SPLIT_DISK_PEAK,
    SPLIT_DISK_STEADY,
    VERDICTS,
    Machine,
    StreamingAssumptions,
    checkpoint_gib,
    choose_engine,
    engine_command,
    find_storage,
    free_disk_gib,
    machine_from_catalog,
    machine_from_host,
    native_checkpoint_gib,
    normalise_mode,
    requested_mode,
    shard_gib,
    size_streaming,
    split_disk_gib,
    storage_classes,
    upstream_snippet,
)
from ai_bunker.sizing import find_model, load_catalog


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


def _machine(**kwargs) -> Machine:
    """A card with no page cache worth speaking of, so the storage term is the only one."""
    base = {
        "name": "test card",
        "device_gib": 24.0,
        "ram_gib": 8.0,  # host_reserve eats it: nothing is cacheable
        "unified": False,
        "memory_gbs": 1000.0,
        "storage": "nvme-gen4",
    }
    base.update(kwargs)
    return Machine(**base)


# ---------------------------------------------------------------------------
# The catalogue's new section is a published artifact too.
# ---------------------------------------------------------------------------


def test_every_storage_class_is_complete(catalog):
    for entry in storage_classes(catalog).values():
        assert entry["read_gbs"] > 0, entry["id"]
        assert entry.get("cached_gbs", 0) > 0, f"{entry['id']} has no cached rate"
        assert entry.get("source") in {"measured", "vendor", "derived"}, entry["id"]
        assert str(entry.get("note") or "").strip(), f"{entry['id']} has no provenance note"


def test_the_measured_class_is_the_one_we_measured(catalog):
    """`apple-nvme` is the only class in the catalogue carrying a figure from
    this repository's own hardware, and `scripts/bench_disk.py` is what
    produced it. If the number changes, the note has to change with it."""
    entry = find_storage("apple-nvme", catalog)
    assert entry["source"] == "measured"
    assert "bench_disk.py" in entry["note"]
    assert 5.0 <= entry["read_gbs"] <= 6.0


def test_an_unknown_storage_class_lists_the_known_ones(catalog):
    with pytest.raises(AssertionError) as caught:
        find_storage("floppy", catalog)
    assert "nvme-gen4" in str(caught.value)


def test_only_complete_machines_carry_a_drive(catalog):
    """A card does not have storage; the host it is plugged into does. An
    accelerator that claims a storage class without being a whole machine is
    asserting something the catalogue cannot know."""
    classes = set(storage_classes(catalog))
    for accel in catalog["accelerators"]:
        if accel.get("storage"):
            assert accel["storage"] in classes, accel["id"]
            assert accel.get("unified"), (
                f"{accel['id']} carries a storage class but is not a complete machine"
            )


# ---------------------------------------------------------------------------
# Bytes per token: the finding that inverts the rest of the repository.
# ---------------------------------------------------------------------------


def test_streaming_reads_the_whole_checkpoint_not_the_active_part(catalog):
    """The 80B is carried in the catalogue at 3B active, and that number is
    what makes it the fastest thing in it. A streaming engine loads each layer
    whole, every expert included, so none of that discount applies."""
    moe = find_model(catalog, "qwen3-coder-next")
    assert moe["active_fraction"] < 0.1, "the premise of this test moved"
    total, label = checkpoint_gib(moe)
    assert total == pytest.approx(moe["weights"]["awq4"])
    assert label == "awq4"


def test_the_moe_recommendation_inverts_under_streaming(catalog):
    """`docs/SIZING.md` says the 80B mixture of experts is nearly three times
    *faster* than the dense 24B. Under streaming it is slower, because the
    comparison is between 45 GiB of checkpoint and 25 GiB of checkpoint rather
    than between 9 GiB of active weights and 25.

    This is the single most counter-intuitive consequence of the fallback and
    the one a reader is most likely to get backwards, so it is asserted.
    """
    machine = _machine()
    moe = size_streaming(model="qwen3-coder-next", **_as_kwargs(machine), catalog=catalog)
    dense = size_streaming(model="devstral-small-2-24b", **_as_kwargs(machine), catalog=catalog)
    assert dense.tps > moe.tps
    # And the resident comparison still says the opposite, on the same machine.
    assert moe.resident_tps > dense.resident_tps


def _as_kwargs(machine: Machine) -> dict:
    return {
        "device_gib": machine.device_gib,
        "ram_gib": machine.ram_gib,
        "unified": machine.unified,
        "storage": machine.storage,
        "memory_gbs": machine.memory_gbs,
    }


def test_compression_is_a_fraction_of_the_sixteen_bit_checkpoint(catalog):
    dense = find_model(catalog, "devstral-small-2-24b")
    plain, _ = checkpoint_gib(dense, quant="bf16")
    four, label = checkpoint_gib(dense, compression="4bit")
    assert label == "bf16+4bit"
    assert four == pytest.approx(plain * COMPRESSION_BYTES["4bit"])
    # The scales and zero points are read with the weights, so it is not a
    # clean quarter and the catalogue should not pretend it is.
    assert four > plain / 4


def test_compression_is_refused_on_a_model_with_no_sixteen_bit_weights(catalog):
    """The community 4-bit checkpoint is all the catalogue carries for the 80B.
    There is nothing left to compress, and silently compressing the already
    quantized weights would report a throughput nothing can deliver."""
    moe = find_model(catalog, "qwen3-coder-next")
    with pytest.raises(AssertionError) as caught:
        checkpoint_gib(moe, compression="4bit")
    # The refusal has to name what the catalogue *does* carry, or the operator
    # has no way to know what to pass instead.
    assert "16-bit" in str(caught.value)
    assert "awq4" in str(caught.value)


def test_an_unknown_compression_is_refused(catalog):
    with pytest.raises(AssertionError):
        checkpoint_gib(find_model(catalog, "devstral-small-2-24b"), compression="2bit")


def test_a_published_layer_count_is_used_and_an_absent_one_is_flagged(catalog):
    published, layers, assumed = shard_gib(find_model(catalog, "devstral-small-2-24b"), 25.0)
    assert (layers, assumed) == (40, False)
    assert published == pytest.approx(25.0 / 40)

    _guessed, layers, assumed = shard_gib(find_model(catalog, "qwen3-coder-next"), 45.0)
    assert (layers, assumed) == (ASSUMED_LAYERS, True)


# ---------------------------------------------------------------------------
# The roofline.
# ---------------------------------------------------------------------------


def test_throughput_is_the_checkpoint_divided_by_the_disk(catalog):
    """The whole model, in one line, checked by hand: 25 GiB off a 10 GB/s
    device at 100% efficiency is 2.684 seconds a token."""
    s = size_streaming(
        model="devstral-small-2-24b",
        device_gib=24,
        ram_gib=8,
        unified=False,
        disk_gbs=10.0,
        cache_gbs=10.0,
        context=8192,
        assumptions=StreamingAssumptions(disk_efficiency=1.0),
        catalog=catalog,
    )
    assert s.cached_gib == 0.0, "the fixture is meant to have nothing cacheable"
    assert s.seconds_per_token == pytest.approx(25 * 1024**3 / 10e9, rel=1e-3)
    assert s.tps == pytest.approx(1 / s.seconds_per_token, rel=1e-2)


def test_halving_the_bytes_doubles_the_speed(catalog):
    """Compression's only mechanism, and the only knob with real leverage."""
    kwargs = dict(
        model="devstral-small-2-24b",
        device_gib=24,
        ram_gib=8,
        unified=False,
        disk_gbs=10.0,
        cache_gbs=10.0,
        context=8192,
        catalog=catalog,
    )
    plain = size_streaming(assumptions=StreamingAssumptions(), **kwargs)
    eight = size_streaming(assumptions=StreamingAssumptions(compression="8bit"), **kwargs)
    # bf16 is 48 GiB and 8-bit compression of it is ~25.2; fp8 is 25. So the
    # interesting assertion is not against `plain` but against the ratio.
    assert eight.checkpoint_gib == pytest.approx(48 * COMPRESSION_BYTES["8bit"], rel=1e-3)
    assert eight.tps == pytest.approx(
        plain.tps * plain.checkpoint_gib / eight.checkpoint_gib, rel=1e-2
    )


def test_a_prompt_costs_one_pass_whatever_its_length(catalog):
    """Streaming inverts the usual cost shape, and this is the assertion of it:
    prefill is one pass over the layers however long the prompt is, so it costs
    what a single token costs."""
    s = size_streaming(
        model="devstral-small-2-24b",
        device_gib=24,
        ram_gib=8,
        unified=False,
        storage="nvme-gen4",
        context=8192,
        catalog=catalog,
    )
    assert s.prefill_seconds == pytest.approx(s.seconds_per_token)


def test_a_measured_disk_figure_does_not_become_the_cached_figure(catalog):
    """Measuring the drive measures the drive. The page-cache re-read rate is
    a different number on a different device and has to come from somewhere
    else, or a measured figure silently governs one nobody measured."""
    s = size_streaming(
        model="devstral-small-2-24b",
        device_gib=24,
        ram_gib=64,
        unified=False,
        storage="nvme-gen4",
        disk_gbs=1.0,
        catalog=catalog,
    )
    assert s.disk_source == "measured"
    assert s.disk_gbs == 1.0
    assert s.cache_gbs == find_storage("nvme-gen4", catalog)["cached_gbs"]


def test_a_vendor_figure_says_it_is_one(catalog):
    s = size_streaming(
        model="devstral-small-2-24b",
        device_gib=24,
        ram_gib=8,
        unified=False,
        storage="nvme-gen4",
        catalog=catalog,
    )
    assert s.disk_source == "catalogue"
    assert any("vendor's peak" in w for w in s.warnings)


# ---------------------------------------------------------------------------
# The page cache, which helps least where it is needed most.
# ---------------------------------------------------------------------------


def test_a_fully_cacheable_checkpoint_says_to_use_a_resident_engine(catalog):
    """The regime trap. A machine with enough free memory to cache the
    checkpoint is a machine that could have held it, where memory-mapping it
    is strictly faster -- so a figure from this regime must not be read as a
    storage measurement."""
    s = size_streaming(
        model="devstral-small-2-24b",
        device_gib=90,
        ram_gib=96,
        unified=True,
        disk_gbs=5.6,
        cache_gbs=13.0,
        context=32768,
        catalog=catalog,
    )
    assert s.streamed_gib == 0.0
    assert any("memory-mapped resident engine" in w for w in s.warnings)


def test_unified_memory_charges_the_cache_against_the_model(catalog):
    """On one pool, caching a shard takes room the KV cache needed. On two it
    does not. Same numbers otherwise, so the difference is the flag."""
    kwargs = dict(
        model="devstral-small-2-24b",
        device_gib=32,
        ram_gib=32,
        disk_gbs=5.0,
        cache_gbs=13.0,
        context=32768,
        catalog=catalog,
    )
    one_pool = size_streaming(unified=True, **kwargs)
    two_pools = size_streaming(unified=False, **kwargs)
    assert one_pool.cached_gib < two_pools.cached_gib
    assert one_pool.tps < two_pools.tps


# ---------------------------------------------------------------------------
# What stays on the device.
# ---------------------------------------------------------------------------


def test_an_eighty_billion_checkpoint_runs_inside_four_gibibytes(catalog):
    """AirLLM's headline claim, as arithmetic. It is the one thing streaming
    genuinely delivers, and the point of the rest of this module is what it
    costs -- so the claim itself has to hold or nothing else matters."""
    s = size_streaming(
        model="qwen3-coder-next",
        device_gib=4,
        ram_gib=16,
        unified=False,
        storage="nvme-gen4",
        catalog=catalog,
    )
    assert s.device_need_gib <= 4.0
    assert s.context >= 4096
    assert s.verdict != "impractical" or s.tps > 0


def test_the_context_is_cut_until_the_kv_cache_fits_beside_the_shards(catalog):
    """Streaming moves the weights off the device. It does not move the KV
    cache, and on a small card that is what binds."""
    s = size_streaming(
        model="devstral-small-2-24b",
        device_gib=8,
        ram_gib=16,
        unified=False,
        storage="nvme-gen4",
        context=262144,
        catalog=catalog,
    )
    assert s.context < 262144
    assert any("Context cut" in w for w in s.warnings)


def test_a_device_too_small_for_one_layer_is_refused(catalog):
    """The wall streaming removes is the checkpoint's, not the layer's."""
    s = size_streaming(
        model="devstral-small-2-24b",
        device_gib=1.0,
        ram_gib=16,
        unified=False,
        storage="nvme-gen4",
        catalog=catalog,
    )
    assert s.verdict == "impractical"
    assert s.tps == 0.0
    assert any("does not remove it for a single layer" in w for w in s.warnings)


def test_the_shard_footprint_counts_the_prefetched_layer(catalog):
    s = size_streaming(
        model="devstral-small-2-24b",
        device_gib=24,
        ram_gib=8,
        unified=False,
        storage="nvme-gen4",
        context=8192,
        catalog=catalog,
    )
    assert s.device_need_gib == pytest.approx(
        s.shard_gib * PREFETCH_DEPTH + s.kv_gib + s.assumptions["device_overhead_gib"],
        abs=0.1,
    )


# ---------------------------------------------------------------------------
# Verdicts.
# ---------------------------------------------------------------------------


def test_the_verdict_is_wall_clock_for_an_answer_somebody_asked_for(catalog):
    """Not a tokens-per-second threshold. Under streaming the prompt is free
    and the answer is the whole cost, so the unit a reader can judge is the
    minutes an answer takes."""
    fast = size_streaming(
        model="devstral-small-2-24b",
        device_gib=24,
        ram_gib=8,
        unified=False,
        disk_gbs=2000.0,  # absurd on purpose: the threshold is under test, not the device
        cache_gbs=2000.0,
        context=8192,
        catalog=catalog,
    )
    assert fast.verdict == "interactive"

    slow = size_streaming(
        model="devstral-small-2-24b",
        device_gib=24,
        ram_gib=8,
        unified=False,
        storage="hdd",
        context=8192,
        catalog=catalog,
    )
    assert slow.verdict == "impractical"
    assert slow.answer_seconds > 43200


@pytest.mark.parametrize("floor", VERDICTS)
def test_every_verdict_is_a_usable_floor(catalog, floor):
    choice = choose_engine(
        model="qwen3-coder-next",
        machine=_machine(),
        mode="auto",
        floor=floor,
        catalog=catalog,
    )
    assert choice.engine in {"resident", "airllm", "none"}


# ---------------------------------------------------------------------------
# The decision.
# ---------------------------------------------------------------------------


def test_off_never_activates_but_still_prices_it(catalog):
    """A refusal with no number attached is a refusal nobody can argue with."""
    choice = choose_engine(
        model="qwen3-coder-next", machine=_machine(), mode="off", catalog=catalog
    )
    assert choice.activated is False
    assert choice.engine == "none"
    assert choice.streaming is not None
    assert choice.streaming.tps > 0


def test_auto_activates_when_the_model_does_not_fit_and_the_floor_is_cleared(catalog):
    choice = choose_engine(
        model="qwen3-coder-next",
        machine=_machine(device_gib=24),
        mode="auto",
        floor="overnight",
        catalog=catalog,
    )
    assert choice.resident_fits is False
    assert (choice.engine, choice.activated) == ("airllm", True)


def test_auto_refuses_when_the_result_is_worse_than_the_floor(catalog):
    choice = choose_engine(
        model="qwen3-coder-next",
        machine=_machine(storage="hdd"),
        mode="auto",
        floor="batch",
        catalog=catalog,
    )
    assert (choice.engine, choice.activated) == ("none", False)
    assert "against a floor of batch" in choice.reason


def test_auto_leaves_a_model_that_fits_alone(catalog):
    """Streaming a model that fits is strictly slower with nothing to show for
    it, so the automatic mode is safe to leave configured."""
    choice = choose_engine(
        model="devstral-small-2-24b",
        machine=_machine(device_gib=96, ram_gib=128),
        mode="auto",
        catalog=catalog,
    )
    assert choice.resident_fits is True
    assert (choice.engine, choice.activated) == ("resident", False)


def test_an_activated_fallback_always_says_it_is_not_interactive(catalog):
    """The failure this prevents is an operator pointing a coding agent at a
    fifth of a token per second and debugging a network problem that is not
    one."""
    choice = choose_engine(
        model="qwen3-coder-next",
        machine=_machine(),
        mode="auto",
        floor="overnight",
        catalog=catalog,
    )
    assert choice.activated
    assert any("not an interactive engine" in w for w in choice.warnings)


def test_on_activates_by_hand_and_objects_when_the_model_fits(catalog):
    choice = choose_engine(
        model="devstral-small-2-24b",
        machine=_machine(device_gib=96, ram_gib=128),
        mode="on",
        catalog=catalog,
    )
    assert (choice.engine, choice.activated) == ("airllm", True)
    assert choice.resident_fits is True
    assert any("almost never what anybody wants" in w for w in choice.warnings)


def test_on_activates_even_when_the_verdict_is_impractical_and_says_so(catalog):
    choice = choose_engine(
        model="qwen3-coder-next", machine=_machine(storage="hdd"), mode="on", catalog=catalog
    )
    assert choice.activated is True
    assert any("not because it is a good idea" in w for w in choice.warnings)


@pytest.mark.parametrize("bad", ["maybe", "sometimes", "fast", "4bit"])
def test_a_mode_nobody_defined_is_refused(catalog, bad):
    with pytest.raises(AssertionError) as caught:
        choose_engine(model="devstral-small-2-24b", machine=_machine(), mode=bad, catalog=catalog)
    # The refusal lists every spelling that works, aliases included, because an
    # operator who typed the wrong word needs the right one and not a subset.
    for spelling in MODES:
        assert spelling in str(caught.value)


@pytest.mark.parametrize("lenient", ["ON", "  off  ", "Auto", ""])
def test_case_and_whitespace_are_not_a_users_problem(catalog, lenient):
    """These used to be refused. Refusing `ON` while accepting `on` is a
    checker having an opinion about shift keys."""
    choice = choose_engine(
        model="devstral-small-2-24b", machine=_machine(), mode=lenient, catalog=catalog
    )
    assert choice.mode in MODES


def test_an_unknown_floor_is_refused(catalog):
    with pytest.raises(AssertionError):
        choose_engine(
            model="devstral-small-2-24b", machine=_machine(), floor="fast", catalog=catalog
        )


def test_a_choice_serialises_whole(catalog):
    choice = choose_engine(
        model="qwen3-coder-next", machine=_machine(), mode="auto", catalog=catalog
    )
    payload = json.loads(json.dumps(choice.to_dict()))
    assert payload["streaming"]["tps"] == choice.streaming.tps


# ---------------------------------------------------------------------------
# The machine.
# ---------------------------------------------------------------------------


def test_a_catalogue_machine_knows_whether_its_memory_is_one_pool(catalog):
    apple = machine_from_catalog("macbook-m2-max-96", catalog=catalog)
    assert apple.unified is True
    assert apple.ram_gib == apple.device_gib
    assert apple.storage == "apple-nvme"

    card = machine_from_catalog("rtx-4090", catalog=catalog)
    assert card.unified is False
    assert card.ram_gib >= 32, "the host-memory default should not be below a plausible host"


def test_host_memory_for_a_card_is_pessimistic_by_default(catalog):
    """Host memory enters this arithmetic only as page cache, where assuming
    more of it makes the answer look better than it is."""
    big = machine_from_catalog("rtx-pro-6000-blackwell", catalog=catalog)
    assert big.ram_gib == big.device_gib


def test_detection_reports_what_it_cannot_know_as_unknown():
    """Memory bandwidth is not something a portable interface reports, so the
    detected path leaves it None and the comparison is omitted rather than
    invented."""
    machine = machine_from_host(
        {
            "platform": "linux",
            "cpu": "a cpu",
            "ram_gb": 64.0,
            "gpu_vendor": "nvidia",
            "gpus": [{"name": "A card", "memory_gb": 24.0}],
            "discrete_vram_gb": 24.0,
            "apple_unified_gb": None,
        }
    )
    assert machine.memory_gbs is None
    assert machine.source == "detected"
    assert machine.device_gib == 24.0


def test_a_machine_with_no_accelerator_streams_into_system_memory():
    machine = machine_from_host(
        {
            "platform": "linux",
            "cpu": "a cpu",
            "ram_gb": 32.0,
            "gpu_vendor": "none",
            "gpus": [],
            "discrete_vram_gb": None,
            "apple_unified_gb": None,
        }
    )
    assert machine.unified is True
    assert machine.device_gib == 32.0


def test_apple_detection_agrees_with_the_catalogue_entry():
    """The detected path and the catalogue path reserve the same unified memory
    for macOS, so this project does not report two different figures for one
    machine depending on which door you came in by."""
    detected = machine_from_host(
        {
            "platform": "darwin",
            "cpu": "Apple M2 Max",
            "apple_chip": "Apple M2 Max",
            "ram_gb": 96.0,
            "gpu_vendor": "apple",
            "gpus": [],
            "discrete_vram_gb": None,
            "apple_unified_gb": 96.0,
        }
    )
    assert detected.device_gib == machine_from_catalog("macbook-m2-max-96").device_gib


# ---------------------------------------------------------------------------
# What to run.
# ---------------------------------------------------------------------------


def test_the_command_carries_the_context_the_sizing_arrived_at(catalog):
    choice = choose_engine(
        model="devstral-small-2-24b",
        machine=_machine(device_gib=8),
        mode="on",
        catalog=catalog,
    )
    command = engine_command(choice)
    assert "ai-bunker airllm serve" in command
    assert f"--context {choice.streaming.context}" in command
    # A path, because `serve` refuses a repository id without --allow-download
    # and a generated command the generator would reject is worse than none.
    served = next(line for line in command.splitlines() if "--model" in line)
    assert "--model /models/" in served
    # The download form is still offered, with the flag visible.
    assert (
        f"--model {find_model(catalog, 'devstral-small-2-24b')['hf']} --allow-download" in command
    )


def test_the_command_passes_compression_through(catalog):
    choice = choose_engine(
        model="devstral-small-2-24b",
        machine=_machine(),
        mode="on",
        assumptions=StreamingAssumptions(compression="4bit"),
        catalog=catalog,
    )
    assert "--compression 4bit" in engine_command(choice)


def test_the_gateway_learns_about_it_as_an_ordinary_upstream(catalog):
    """There is no fallback-specific configuration key, and that is the design:
    the engine speaks the dialect the gateway already proxies, so screening,
    the budget, the breaker and the decision log apply unchanged."""
    choice = choose_engine(
        model="devstral-small-2-24b", machine=_machine(), mode="on", catalog=catalog
    )
    snippet = upstream_snippet(choice, name="slow", port=9000)
    assert "upstreams:" in snippet and "  slow:" in snippet
    # The two blocks an operator copies in one sitting must agree.
    served = next(line for line in engine_command(choice).splitlines() if "--model" in line)
    assert served.split("--model ", 1)[1].strip(" \\") in snippet
    assert "http://127.0.0.1:9000/v1" in snippet
    assert f"served_context: {choice.streaming.context}" in snippet
    assert "remote: false" in snippet


# ---------------------------------------------------------------------------
# The engine's socket, against a stub.
# ---------------------------------------------------------------------------


class StubTokenizer:
    """The three methods this project asks of a tokenizer, and no more."""

    chat_template = None

    def __call__(self, prompt, **kwargs):
        self.seen = prompt
        return {"input_ids": [[1, 2, 3]]}

    def decode(self, ids, **kwargs):
        # The prompt is three ids and the completion is four, so the prompt is
        # a genuine prefix of the answer -- which is the condition
        # `generate_text` strips against.
        return "PROMPT answer" if len(ids) > 3 else "PROMPT"


class StubEngine:
    """A model that does not take a ``streamer``, which is the older surface."""

    def __init__(self):
        self.tokenizer = StubTokenizer()
        self.calls = []

    def generate(self, input_ids, **kwargs):
        if "streamer" in kwargs:
            raise TypeError("generate() got an unexpected keyword argument 'streamer'")
        self.calls.append(kwargs)
        return [[1, 2, 3, 4]]


class SilentStreamerEngine(StubEngine):
    """Accepts ``streamer``, ignores it, and answers the ordinary way.

    The shape that used to produce an empty completion reported as a
    successful one.
    """

    def generate(self, input_ids, **kwargs):
        kwargs.pop("streamer", None)
        self.calls.append(kwargs)
        return [[1, 2, 3, 4]]


def _loaded(engine=None) -> Loaded:
    return Loaded(engine=engine or StubEngine(), model="stub/model", context=2048, compression=None)


@pytest.fixture
def client():
    starlette = pytest.importorskip("starlette.testclient")
    loaded = _loaded()
    app = create_app(lambda: loaded)
    return starlette.TestClient(app), loaded


def test_a_prompt_uses_the_chat_template_when_the_checkpoint_has_one():
    class Templated(StubTokenizer):
        chat_template = "{{ anything }}"

        def apply_chat_template(self, messages, **kwargs):
            return f"<TEMPLATED {len(messages)}>"

    out = render_prompt(Templated(), [{"role": "user", "content": "hi"}])
    assert out == "<TEMPLATED 1>"


def test_a_prompt_without_a_template_becomes_a_transcript():
    out = render_prompt(StubTokenizer(), [{"role": "user", "content": "hi"}])
    assert "user: hi" in out
    assert out.rstrip().endswith("assistant:")


def test_the_text_parts_of_a_multimodal_message_are_kept():
    """Dropping them silently would answer a different question than the one
    asked; keeping the image parts would send bytes to a text model."""
    out = render_prompt(
        StubTokenizer(),
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "what is this"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}},
                ],
            }
        ],
    )
    assert "what is this" in out
    assert "base64" not in out


def test_a_blocking_completion_strips_the_prompt_back_off():
    assert generate_text(_loaded(), [{"role": "user", "content": "hi"}]) == " answer"


def test_temperature_is_only_passed_when_it_means_something():
    engine = StubEngine()
    generate_text(_loaded(engine), [{"role": "user", "content": "hi"}], temperature=0.0)
    assert "do_sample" not in engine.calls[-1]
    generate_text(_loaded(engine), [{"role": "user", "content": "hi"}], temperature=0.7)
    assert engine.calls[-1]["do_sample"] is True


def test_an_engine_that_cannot_stream_still_answers():
    """Falling back to one chunk is the right failure: a caller cannot tell the
    difference except in the timing, and refusing outright would make the
    socket depend on a transformers version."""
    pieces = list(generate_stream(_loaded(), [{"role": "user", "content": "hi"}]))
    assert "".join(pieces) == " answer"


def test_an_engine_that_accepts_a_streamer_and_ignores_it_does_not_answer_empty():
    """The silent-empty bug. Nothing streamed and no error raised used to be
    reported to the client as a successful completion with no content."""
    pieces = list(
        generate_stream(_loaded(SilentStreamerEngine()), [{"role": "user", "content": "hi"}])
    )
    assert "".join(pieces) == " answer"


def test_a_real_failure_is_raised_rather_than_swallowed():
    class Broken(StubEngine):
        def generate(self, input_ids, **kwargs):
            raise RuntimeError("the shards are gone")

    with pytest.raises(RuntimeError, match="shards are gone"):
        list(generate_stream(_loaded(Broken()), [{"role": "user", "content": "hi"}]))


def test_health_answers_before_the_engine_is_loaded(client):
    http, _loadedref = client
    body = http.get("/health").json()
    assert body["status"] == "idle"
    assert body["interactive"] is False
    assert "storage for every generated token" in body["note"]


def test_health_answers_during_a_load():
    """Splitting a checkpoint takes as long as the download did. For that half
    hour an operator needs to be able to tell 'working' from 'wedged', so
    /health must not be the thing that loads the engine."""
    starlette = pytest.importorskip("starlette.testclient")
    app = create_app(lambda: (_ for _ in ()).throw(AssertionError("/health loaded the engine")))
    with starlette.TestClient(app) as http:
        assert http.get("/health").json()["status"] == "idle"


def test_models_is_empty_until_something_is_loaded(client):
    http, _ = client
    assert http.get("/v1/models").json()["data"] == []
    http.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})
    listed = http.get("/v1/models").json()["data"]
    assert listed[0]["id"] == "stub/model"
    assert listed[0]["context_length"] == 2048


def test_a_completion_comes_back_in_the_openai_shape(client):
    http, _ = client
    body = http.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}], "max_tokens": 8},
    ).json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["finish_reason"] == "stop"


def test_a_stream_is_framed_the_way_a_client_expects(client):
    http, _ = client
    with http.stream(
        "POST",
        "/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "hi"}], "stream": True},
    ) as response:
        text = "".join(response.iter_text())
    assert response.headers["content-type"].startswith("text/event-stream")
    assert text.startswith("data: ")
    assert "data: [DONE]" in text
    chunks = [
        json.loads(line.removeprefix("data: "))
        for line in text.splitlines()
        if line.startswith("data: ") and not line.endswith("[DONE]")
    ]
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert "answer" in "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)


def test_a_body_that_is_not_a_request_is_refused(client):
    http, _ = client
    assert http.post("/v1/chat/completions", content=b"not json").status_code == 400
    assert http.post("/v1/chat/completions", json={"messages": []}).status_code == 400
    assert http.post("/v1/chat/completions", json={}).status_code == 400


def test_a_missing_engine_is_a_501_naming_the_extra():
    """The failure an operator actually hits: the arithmetic ran, the decision
    said stream, and `airllm` was never installed."""
    starlette = pytest.importorskip("starlette.testclient")

    def load():
        raise ImportError("pip install 'ai-bunker[airllm]'")

    http = starlette.TestClient(create_app(load))
    response = http.post(
        "/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]}
    )
    assert response.status_code == 501
    assert "ai-bunker[airllm]" in response.json()["error"]["message"]


def test_a_load_failure_is_a_503_rather_than_a_crash():
    starlette = pytest.importorskip("starlette.testclient")

    def load():
        raise RuntimeError("no room for the shards")

    http = starlette.TestClient(create_app(load))
    response = http.post(
        "/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]}
    )
    assert response.status_code == 503
    assert "no room" in response.json()["error"]["message"]
    assert http.get("/health").json()["error"]


# ---------------------------------------------------------------------------
# Loading, and the one thing it must not do quietly.
# ---------------------------------------------------------------------------


def test_a_repository_id_is_refused_rather_than_downloaded():
    """The sovereignty rule, in the one module allowed to load a checkpoint.
    Handing a loader a repository id makes it reach a third-party hub, and a
    project whose argument is that nothing leaves the local network does not do
    that because a flag defaulted the other way."""
    with pytest.raises(AssertionError) as caught:
        load_engine("Qwen/Qwen3-Coder-Next")
    assert "not a local checkpoint" in str(caught.value)
    assert "allow_download" in str(caught.value)


def test_a_directory_with_no_configuration_is_not_a_checkpoint(tmp_path):
    """Conservative on purpose: treating a plausible-looking path as a
    checkpoint turns a typo into a silent download."""
    assert is_local_checkpoint(str(tmp_path)) is False
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    assert is_local_checkpoint(str(tmp_path)) is True


def test_an_index_file_also_counts_as_a_checkpoint(tmp_path):
    (tmp_path / "model.safetensors.index.json").write_text("{}", encoding="utf-8")
    assert is_local_checkpoint(str(tmp_path)) is True


@pytest.mark.parametrize("value", ["", "owner/name", "/does/not/exist"])
def test_nothing_that_is_not_a_directory_is_a_checkpoint(value):
    assert is_local_checkpoint(value) is False


def test_the_serve_flag_is_the_one_the_refusal_names():
    """The message tells an operator to pass `--allow-download`. If the flag
    were ever renamed, the refusal would be instructions to type something that
    does not exist."""
    parser = build_parser()
    namespace = parser.parse_args(["airllm", "serve", "--model", "x", "--allow-download"])
    assert namespace.allow_download is True
    assert parser.parse_args(["airllm", "serve", "--model", "x"]).allow_download is False


# ---------------------------------------------------------------------------
# Which adapter actually loads the checkpoint.
# ---------------------------------------------------------------------------


def test_the_suites_own_adapter_is_preferred_over_importing_airllm(monkeypatch):
    """`best-engine-ai-helper` owns "which local model, through which backend"
    and carries the suite's AirLLM adapter, so exactly one place in the suite
    should be passing keyword arguments to `AutoModel.from_pretrained`. This
    asserts ai-bunker is not that place when the helper can be."""
    helper = pytest.importorskip("best_engine_ai_helper")
    if not hasattr(helper, "airllm_load"):
        pytest.skip("the installed helper predates its offload module")

    seen: dict[str, object] = {}

    def fake_load(model, **kwargs):
        seen.update({"model": model, **kwargs})
        return StubEngine()

    monkeypatch.setattr(helper, "airllm_load", fake_load)
    loaded = load_engine(
        "/tmp/not/real", allow_download=True, compression="4bit", shards_dir="/shards"
    )
    assert isinstance(loaded.engine, StubEngine)
    assert seen["model"] == "/tmp/not/real"
    assert seen["compression"] == "4bit"
    # The helper spells it airllm's way; this module must translate rather than
    # invent a third name for the same directory.
    assert seen["layer_shards_saving_path"] == "/shards"


def test_importing_airllm_directly_is_the_fallback_not_the_default(monkeypatch):
    """Version skew is what a two-repository suite actually has: a machine can
    carry the engine and an older helper. Without the direct path this module
    would be pinned to a release of its sibling."""
    import builtins

    real_import = builtins.__import__

    def without_the_helper(name, *args, **kwargs):
        if name == "best_engine_ai_helper":
            raise ImportError("pretend the helper predates offload.py")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_the_helper)
    try:
        loader = _loader()
    except ImportError as exc:
        # No engine installed either, which is the ordinary case in this suite's
        # continuous integration. The refusal still has to name the extra.
        assert "ai-bunker[airllm]" in str(exc)
    else:
        assert loader.__name__ == "directly"


def test_an_absent_hugging_face_token_is_not_a_crash(monkeypatch):
    """`osh.get_config` raises when a key resolves nowhere, which is right for
    something a program cannot run without and wrong for a token only a gated
    repository needs. Loading used to die on any machine without one."""
    helper = pytest.importorskip("best_engine_ai_helper")
    if not hasattr(helper, "airllm_load"):
        pytest.skip("the installed helper predates its offload module")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(helper, "airllm_load", lambda model, **kwargs: StubEngine())
    assert load_engine("/tmp/not/real", allow_download=True).model == "/tmp/not/real"


def test_serving_a_repository_id_is_refused_before_the_socket_opens(monkeypatch):
    """Loading is lazy so `/health` can answer while a checkpoint is being
    split, and the cost of that was a configuration error arriving as a
    per-request failure: `--model owner/name` without `--allow-download` used
    to start a socket that refused every request it ever received."""
    import ai_bunker.airllm as engine_module

    def must_not_run(*args, **kwargs):  # pragma: no cover - the point is it is not called
        raise AssertionError("uvicorn.run was reached on an unservable model")

    monkeypatch.setattr(engine_module, "create_app", must_not_run)
    with pytest.raises(AssertionError) as caught:
        engine_module.serve(model="Qwen/Qwen3-Coder-Next")
    assert "not a local checkpoint" in str(caught.value)
    assert "--allow-download" in str(caught.value)


# ---------------------------------------------------------------------------
# One vocabulary across the suite.
# ---------------------------------------------------------------------------


def test_the_canonical_modes_are_the_suites_modes():
    """`best-engine-ai-helper` owns the AirLLM adapter and published this
    vocabulary first. A suite where one tool says `--mode on` and its sibling
    says `airllm: always` for the identical policy is a suite whose
    documentation cannot be read straight through."""
    assert MODES == ("auto", "always", "never")


@pytest.mark.parametrize(
    "spelling,canonical",
    [
        ("auto", "auto"),
        ("always", "always"),
        ("on", "always"),
        ("true", "always"),
        ("never", "never"),
        ("off", "never"),
        ("no", "never"),
        ("", "auto"),
        (None, "auto"),
        ("  Always  ", "always"),
    ],
)
def test_every_accepted_spelling_canonicalises(spelling, canonical):
    assert normalise_mode(spelling) == canonical


def test_the_old_spellings_still_work():
    """`off` and `on` were this project's canonical words before the two
    vocabularies were reconciled. Anything anybody typed or wrote down has to
    keep working, or reconciling vocabularies is a breaking change dressed up
    as tidying."""
    assert normalise_mode("off") == "never"
    assert normalise_mode("on") == "always"


def test_the_alias_table_agrees_with_the_siblings():
    """The drift guard that makes a copied table defensible. If the helper
    teaches its policy a new spelling, this fails rather than the two packages
    silently accepting different words."""
    offload = pytest.importorskip("best_engine_ai_helper.offload")
    theirs = getattr(offload, "_REQUEST_ALIASES", None)
    if theirs is None:
        pytest.skip("the installed helper predates its request aliases")
    assert theirs == MODE_ALIASES


def test_the_environment_is_the_fallback_and_an_explicit_mode_wins():
    """Precedence mirrors `offload.requested` exactly, so one suite-wide switch
    produces one answer whichever tool is asked."""
    assert requested_mode(None, env={}) == "auto"
    assert requested_mode(None, env={MODE_ENV_VAR: "never"}) == "never"
    assert requested_mode("always", env={MODE_ENV_VAR: "never"}) == "always"
    assert requested_mode("", env={MODE_ENV_VAR: "always"}) == "always"


def test_the_suite_kill_switch_reaches_this_project(catalog, monkeypatch):
    """A kill switch one tool ignores is not a kill switch. An operator who set
    `BEST_ENGINE_AIRLLM=never` must not find ai-bunker activating anyway."""
    monkeypatch.setenv(MODE_ENV_VAR, "never")
    choice = choose_engine(model="qwen3-coder-next", machine=_machine(), catalog=catalog)
    assert choice.mode == "never"
    assert choice.activated is False


def test_an_unknown_mode_lists_the_spellings_that_work(catalog):
    with pytest.raises(AssertionError) as caught:
        choose_engine(model="qwen3-coder-next", machine=_machine(), mode="sometimes")
    assert "always" in str(caught.value) and "never" in str(caught.value)


# ---------------------------------------------------------------------------
# The disk, which is the constraint that actually bites.
# ---------------------------------------------------------------------------


def test_the_split_disk_figures_match_the_siblings():
    """Two packages reporting different disk requirements for the same model is
    the failure this shares constants to prevent. These are the sibling's own
    doctest values, in its units."""
    assert split_disk_gib(140.0, 140.0) == (294.0, 154.0)
    assert split_disk_gib(140.0, 35.0) == (178.5, 38.5)


def test_the_split_constants_are_the_siblings():
    offload = pytest.importorskip("best_engine_ai_helper.offload")
    peak = getattr(offload, "_SPLIT_DISK_PEAK", None)
    steady = getattr(offload, "_SPLIT_DISK_STEADY", None)
    if peak is None or steady is None:
        pytest.skip("the installed helper predates its split-disk constants")
    assert (peak, steady) == (SPLIT_DISK_PEAK, SPLIT_DISK_STEADY)


def test_compression_shrinks_the_shards_and_not_the_download(catalog):
    """Confusing the two understates peak disk by up to a factor of four, and
    peak disk is what decides whether the split can run at all."""
    dense = find_model(catalog, "devstral-small-2-24b")
    assert native_checkpoint_gib(dense, compression="4bit") == dense["weights"]["bf16"]
    shards, _ = checkpoint_gib(dense, compression="4bit")
    assert shards < dense["weights"]["bf16"] / 3
    peak, steady = split_disk_gib(native_checkpoint_gib(dense, compression="4bit"), shards)
    # The download dominates the peak however hard the shards are compressed.
    assert peak > dense["weights"]["bf16"]
    assert steady < peak / 3


def test_a_short_disk_is_reported_against_the_peak(catalog, tmp_path):
    s = size_streaming(
        model="qwen3-coder-next",
        device_gib=24,
        ram_gib=32,
        unified=False,
        storage="nvme-gen4",
        context=32768,
        shards_dir=str(tmp_path),
        catalog=catalog,
    )
    assert s.split_peak_gib > s.checkpoint_gib
    assert s.free_disk_gib is not None
    if s.free_disk_gib < s.split_peak_gib:
        assert any("free while it runs" in w for w in s.warnings)
    else:  # a roomy machine; the figures still have to be there
        assert not any("free while it runs" in w for w in s.warnings)


def test_no_shards_directory_means_no_disk_claim(catalog):
    """Reporting a figure nobody asked for is one thing; reporting a *check*
    that was never run is another."""
    s = size_streaming(
        model="qwen3-coder-next",
        device_gib=24,
        ram_gib=32,
        unified=False,
        storage="nvme-gen4",
        context=32768,
        catalog=catalog,
    )
    assert s.free_disk_gib is None
    assert not any("free while it runs" in w for w in s.warnings)


def test_unreadable_free_space_is_unknown_rather_than_zero():
    """Zero would make every plan fail the disk check on a platform without
    `statvfs`, which is a refusal nobody can act on."""
    assert free_disk_gib(None) is None
    assert free_disk_gib("") is None
    # A path that does not exist yet is the normal case -- it is where shards
    # are *going* -- so it walks up to a parent that does.
    assert free_disk_gib("/does/not/exist/yet/shards") is not None


def test_the_report_shows_the_disk_block(catalog):
    from ai_bunker.report import render_fallback

    choice = choose_engine(
        model="qwen3-coder-next",
        machine=_machine(),
        mode="always",
        shards_dir="/tmp",
        catalog=catalog,
    )
    out = render_fallback(choice)
    assert "WHAT THE SPLIT NEEDS ON DISK" in out
    assert "free space while splitting" in out
    assert "with --delete-original" in out
