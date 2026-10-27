"""
When the model does not fit: size the machine for layer-by-layer streaming.

The rest of this project sizes a machine that *holds* a model. This module
answers the other question — what happens when it does not, and the choice is
between a smaller model and a slower one.

`AirLLM <https://github.com/lyogavin/airllm>`_ makes the second option real. It
keeps one transformer layer resident at a time and streams the rest off
storage, so a 70B checkpoint runs inside four gibibytes of device memory. The
capacity wall disappears. What takes its place is the arithmetic below, and it
is the same arithmetic the rest of this repository runs — a roofline over the
device the weights are read from — applied to a device one to two orders of
magnitude slower than memory::

    seconds_per_token  =  bytes_read_per_token  /  storage_bandwidth
    tokens_per_second  =  1 / seconds_per_token

Three consequences, and all three are load-bearing.

**The read is the whole checkpoint, not the active part.** A layer is loaded
whole, so every expert of every layer crosses the bus whether the router picks
it or not. The mixture-of-experts economics that make an 80B/3B model the
fastest thing in ``catalog/serving.yaml`` are a property of *resident* serving,
and they do not survive the move to storage: under streaming the 45-gibibyte
80B is **slower** than the 25-gibibyte dense 24B, which is the exact inverse
of the recommendation this project makes everywhere else.

**The page cache helps exactly where it is not needed.** Shards the operating
system can keep in free memory are re-read at memory speed. But a machine with
enough free memory to cache the checkpoint is a machine that could have held
the checkpoint, where a memory-mapped resident engine is strictly better. So
the regime streaming exists for is the regime where the cache cannot save it,
and the mixing below is here to stop a half-cached measurement being quoted as
a storage figure.

**Prefill is nearly free, and decode is nearly everything.** A prompt of any
length makes one pass over the layers, because the whole prompt goes through
each layer while it is resident. Streaming therefore inverts the usual cost
shape: a 32,000-token prompt costs about one token's worth of reads, and then
every single generated token costs another full pass. Long context is almost
free here and generated length is ruinous.

Nothing in this module imports ``airllm``, and that is deliberate: the decision
of whether to stream is arithmetic over a catalogue, it has to work on a
machine that will never run the engine, and it must not drag PyTorch into a
gateway process. :mod:`ai_bunker.airllm` is the half that does the importing.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import os_helper as osh

from ai_bunker.sizing import (
    GB,
    GIB,
    active_weights_gib,
    find_model,
    kv_gib,
    load_catalog,
    weights_gib,
)

#: Activation modes, in the order of how much the operator is asserting.
#:
#: The spellings are ``best-engine-ai-helper``'s, not this project's. That
#: package owns the suite's AirLLM adapter and published this vocabulary first,
#: and a suite in which one tool says ``--mode on`` while its sibling says
#: ``airllm: always`` for the identical policy is a suite whose documentation
#: cannot be read straight through. ``always`` and ``never`` are also the
#: better words: they describe a *rule*, which is what this is, where ``on``
#: and ``off`` describe a state.
MODES = ("auto", "always", "never")

#: Spellings accepted for a mode, canonicalised. Mirrors
#: ``best_engine_ai_helper.offload._REQUEST_ALIASES`` -- including ``off``/``on``,
#: which were this project's own canonical words before the vocabularies were
#: reconciled, so nothing anybody has typed or written down stops working.
#: ``tests/test_fallback.py`` asserts the two tables agree wherever the helper
#: is importable, so this is a guarded copy rather than a forked one.
MODE_ALIASES = {
    "auto": "auto",
    "always": "always",
    "on": "always",
    "true": "always",
    "yes": "always",
    "1": "always",
    "never": "never",
    "off": "never",
    "false": "never",
    "no": "never",
    "0": "never",
}

#: The suite's switch for this path, read when no mode is given explicitly.
#: Honoured here so that ``BEST_ENGINE_AIRLLM=never`` means never across the
#: suite -- a kill switch one tool ignores is not a kill switch.
MODE_ENV_VAR = "BEST_ENGINE_AIRLLM"

#: Verdicts, best first. The thresholds are in :class:`StreamingAssumptions`.
VERDICTS = ("interactive", "batch", "overnight", "impractical")

#: Layers assumed when the catalogue does not publish the count. Transformer
#: depth is a narrow band across the 8B-80B range this catalogue covers --
#: 32 to 64 -- and the figure only sets how much memory one resident shard
#: needs, never the throughput, which depends on the checkpoint's total size.
#: Every result computed from it says so in ``layers_assumed``.
ASSUMED_LAYERS = 48

#: Resident shards: the one being computed plus the one being fetched. AirLLM
#: prefetches the next layer while the current one runs, which is what makes
#: the pipeline continuous and what doubles the shard footprint.
PREFETCH_DEPTH = 2

#: Disk the split needs while it runs, and once it has settled, as multiples
#: of the shard bytes. AirLLM writes per-layer shards beside the original
#: checkpoint, so the cache briefly holds both.
#:
#: Both figures are ``best-engine-ai-helper``'s (``_SPLIT_DISK_PEAK`` and
#: ``_SPLIT_DISK_STEADY``), copied so the two packages cannot report different
#: disk requirements for the same model. Theirs derives the checkpoint from a
#: parameter count; this one reads it from ``catalog/serving.yaml``'s measured
#: weight tables, which is the better input -- so the constants are shared and
#: the inputs are not.
SPLIT_DISK_PEAK = 2.1
SPLIT_DISK_STEADY = 1.1

#: Block-wise compression, as a fraction of a 16-bit checkpoint's bytes. The
#: 1.05 factor is the per-block scales and zero points, which are stored
#: alongside the quantized weights and are read with them.
COMPRESSION_BYTES = {"4bit": 0.25 * 1.05, "8bit": 0.50 * 1.05}


# ---------------------------------------------------------------------------
# Storage facts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StreamingAssumptions:
    """Everything the streaming sizing cannot measure, named so it can be argued with.

    Attributes
    ----------
    disk_efficiency : float
        Fraction of a device's sequential read bandwidth that a real shard
        read achieves. Shards are read whole and in order, which is the
        friendly case, and the loss is file-system overhead, shard boundaries
        that do not land on block boundaries, and the gaps prefetching does
        not quite cover. 0.85 is deliberately generous: being generous here
        and still landing three orders of magnitude below the interactive
        floor is a stronger statement than being careful.
    answer_tokens : int
        Generated length the verdict is judged on. Not a context size: under
        streaming the prompt is nearly free and the *answer* is the whole
        cost, so the honest unit is wall-clock for an answer somebody asked
        for. 500 tokens is a short patch or a paragraph.
    interactive_tps : float
        Per-stream tokens/second below which an interactive agent stops being
        interactive. The same 20 the resident sizing uses, so the two
        verdicts are comparable.
    batch_seconds : float
        Wall clock within which an answer counts as a batch job somebody will
        wait for. One hour.
    overnight_seconds : float
        Wall clock within which it counts as a job somebody will leave
        running. Twelve hours.
    device_overhead_gib : float
        Device memory that is not weights and not KV cache: activations for
        one layer's forward pass, the accelerator's own context, and
        fragmentation. Small, and it is what decides whether a four-gibibyte
        card clears the bar at all, so it is named rather than folded in.
    host_reserve_gib : float
        **System** memory the operating system, the Python process and the
        tokenizer need, and which is therefore not available to cache shards
        in. Charged against RAM, never against the device -- the mistake in
        the other direction makes a small card look unable to run anything,
        which is the one claim AirLLM exists to refute.
    kv_dtype : {'bf16', 'fp8'}
        KV cache storage dtype. ``bf16`` by default and not by preference:
        the streaming path is PyTorch, it has no paged-attention kernel, and
        the 8-bit cache the resident path assumes is a vLLM feature.
    compression : str or None
        AirLLM block-wise compression: ``'4bit'``, ``'8bit'`` or None for the
        checkpoint as the catalogue lists it. It is applied to a 16-bit
        checkpoint, so it is refused on a model this catalogue only carries
        already-quantized.
    """

    disk_efficiency: float = 0.85
    answer_tokens: int = 500
    interactive_tps: float = 20.0
    batch_seconds: float = 3600.0
    overnight_seconds: float = 43200.0
    device_overhead_gib: float = 1.5
    host_reserve_gib: float = 8.0
    kv_dtype: str = "bf16"
    compression: str | None = None


def storage_classes(catalog: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """The catalogue's named storage devices, keyed by id."""
    cat = catalog or load_catalog()
    entries = cat.get("storage") or []
    osh.check(bool(entries), "The serving catalogue carries no `storage:` section.")
    return {str(e["id"]): e for e in entries}


def find_storage(storage_id: str, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return one catalogue storage class by id, with a listing in the error if absent."""
    index = storage_classes(catalog)
    osh.check(
        storage_id in index,
        f"Unknown storage class {storage_id!r}. Known: {', '.join(sorted(index))}",
    )
    return index[storage_id]


# ---------------------------------------------------------------------------
# Bytes per token
# ---------------------------------------------------------------------------


def checkpoint_gib(
    model: dict[str, Any],
    *,
    quant: str | None = None,
    compression: str | None = None,
) -> tuple[float, str]:
    """Bytes of weights a streaming engine reads per decode step, in GiB.

    The whole checkpoint, because every layer is loaded and every layer is
    loaded whole. ``active_fraction`` is not consulted and must not be: it
    describes what a resident engine *reads* out of memory it already holds,
    and a streaming engine holds nothing.

    Parameters
    ----------
    model : dict
        A catalogue model entry.
    quant : str, optional
        Which of the catalogue's weight tables to hand the engine. Defaults
        to the model's recommended quantization.
    compression : {'4bit', '8bit'}, optional
        AirLLM block-wise compression, applied to the 16-bit checkpoint. The
        catalogue must list ``bf16`` weights for the model, since that is what
        gets compressed; a model carried here only as a 4-bit community quant
        has nothing to compress and the call is refused.

    Returns
    -------
    (float, str)
        GiB read per token, and the label describing how the bytes were
        obtained -- a quantization name, or ``'bf16+4bit'``.
    """
    if compression:
        osh.check(
            compression in COMPRESSION_BYTES,
            f"Unknown compression {compression!r}. Known: {', '.join(COMPRESSION_BYTES)}",
        )
        table = model.get("weights") or {}
        osh.check(
            "bf16" in table,
            f"{model['id']}: block-wise compression quantizes a 16-bit checkpoint and the "
            f"catalogue carries none for this model (has: {', '.join(sorted(table))}). "
            "Hand the engine the quantized checkpoint instead and drop --compression.",
        )
        return float(table["bf16"]) * COMPRESSION_BYTES[compression], f"bf16+{compression}"

    total, label = weights_gib(model, quant)
    return total, label


def native_checkpoint_gib(
    model: dict[str, Any],
    *,
    quant: str | None = None,
    compression: str | None = None,
) -> float:
    """The checkpoint as downloaded, which is what the split reads.

    Compression shrinks the shards, never the original: AirLLM reads the
    downloaded weights to produce the compressed ones, so the download has to
    be on disk first either way. Confusing the two understates peak disk by up
    to a factor of four, which is the figure that decides whether the split can
    run at all.
    """
    if compression:
        table = model.get("weights") or {}
        return float(table["bf16"])
    return checkpoint_gib(model, quant=quant)[0]


def shard_gib(model: dict[str, Any], total_gib: float) -> tuple[float, int, bool]:
    """Size of one resident layer shard, the layer count, and whether it was assumed.

    The engine's memory requirement is one shard (plus the one being
    prefetched) rather than the checkpoint, which is the entire trick. The
    count comes from the catalogue's published attention geometry when it has
    it and from :data:`ASSUMED_LAYERS` otherwise -- and the caller is told
    which, because a memory figure computed from an assumed depth should not
    be read as a measured one.
    """
    layers = int((model.get("kv") or {}).get("layers") or 0)
    assumed = layers <= 0
    if assumed:
        layers = ASSUMED_LAYERS
    return total_gib / layers, layers, assumed


def split_disk_gib(native_gib: float, shards_gib: float) -> tuple[float, float]:
    """Free disk the split needs, at its peak and once settled, in GiB.

    The constraint that actually bites. The memory side of streaming is the
    easy half -- that is the half AirLLM solved -- and the disk side is where a
    235B model stops being possible on a laptop with a 2 terabyte drive.

    Parameters
    ----------
    native_gib : float
        The checkpoint as downloaded. Compression does not shrink it: the split
        reads the original, so the original has to be there first either way.
    shards_gib : float
        The per-layer shards, which is where compression does apply.

    Returns
    -------
    (float, float)
        ``(peak, steady)``. Peak is during the split, with both copies on
        disk; steady is afterwards, and only reachable with
        ``--delete-original``.
    """
    peak = native_gib + shards_gib * (SPLIT_DISK_PEAK - 1.0)
    return round(peak, 1), round(shards_gib * SPLIT_DISK_STEADY, 1)


def free_disk_gib(path: str | None) -> float | None:
    """Free space on the filesystem holding ``path``, in GiB, or None.

    None rather than zero when it cannot be read, and the distinction matters:
    zero would make every plan fail the disk check on a platform whose
    ``statvfs`` is missing, which is a refusal nobody can act on. An unknown
    figure is reported as unknown.
    """
    if not path:
        return None
    import os
    from pathlib import Path as _Path

    probe = _Path(path).expanduser()
    # The directory may not exist yet -- it is where shards are *going* -- so
    # walk up to the nearest parent that does.
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        stat = os.statvfs(str(probe))
    except (OSError, AttributeError):
        return None
    return (stat.f_bavail * stat.f_frsize) / GIB


# ---------------------------------------------------------------------------
# The sizing
# ---------------------------------------------------------------------------


@dataclass
class Streaming:
    """What layer-by-layer streaming of one model on one machine actually costs."""

    model_id: str
    quant: str
    storage: str
    disk_source: str
    disk_gbs: float
    cache_gbs: float
    context: int
    layers: int
    layers_assumed: bool
    checkpoint_gib: float
    native_gib: float
    split_peak_gib: float
    split_steady_gib: float
    free_disk_gib: float | None
    shard_gib: float
    cached_gib: float
    streamed_gib: float
    device_need_gib: float
    kv_gib: float
    seconds_per_token: float
    tps: float
    answer_tokens: int
    answer_seconds: float
    prefill_seconds: float
    resident_tps: float | None
    slowdown: float | None
    verdict: str
    warnings: list[str] = field(default_factory=list)
    assumptions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _verdict(tps: float, answer_seconds: float, a: StreamingAssumptions) -> str:
    if tps >= a.interactive_tps:
        return "interactive"
    if answer_seconds <= a.batch_seconds:
        return "batch"
    if answer_seconds <= a.overnight_seconds:
        return "overnight"
    return "impractical"


def size_streaming(
    *,
    model: str,
    device_gib: float,
    ram_gib: float | None = None,
    unified: bool = False,
    storage: str = "nvme-gen4",
    disk_gbs: float | None = None,
    cache_gbs: float | None = None,
    memory_gbs: float | None = None,
    context: int | None = None,
    quant: str | None = None,
    shards_dir: str | None = None,
    assumptions: StreamingAssumptions | None = None,
    catalog: dict[str, Any] | None = None,
) -> Streaming:
    """Size one machine for streaming one model off storage.

    Parameters
    ----------
    model : str
        Catalogue model id.
    device_gib : float
        Memory the resident shards and the KV cache live in: a discrete card's
        VRAM, or the usable part of a unified pool.
    ram_gib : float, optional
        System memory, where the operating system's page cache lives. Defaults
        to ``device_gib`` on a unified machine and to eight times the device
        on a discrete one, which is the ordinary workstation ratio.
    unified : bool
        True on Apple Silicon and other unified-memory machines, where the
        page cache and the model compete for one pool rather than two. It is
        the difference between caching shards being free and caching shards
        taking room away from the KV cache.
    storage : str
        Catalogue storage-class id, used when ``disk_gbs`` is not given.
    disk_gbs : float, optional
        Measured sequential read bandwidth in GB/s. Prefer it over a class:
        ``python scripts/bench_disk.py`` produces it, and a measured figure
        is the difference between this result and a brochure.
    cache_gbs : float, optional
        Rate at which a shard already in the page cache is re-read. Measured
        by the same script; defaults to the storage class's figure.
    memory_gbs : float, optional
        The machine's memory bandwidth, used only to report how much slower
        streaming is than holding the model. Omit it and ``slowdown`` is None.
    context : int, optional
        Context to serve. Defaults to the model's maximum, halved until the
        KV cache fits beside the resident shards.
    quant : str, optional
        Which weight table to hand the engine.
    shards_dir : str, optional
        Where the split checkpoint will be written. Given, the free space there
        is read and compared against the peak the split needs -- the one
        constraint in this whole module that can be checked rather than
        projected, and the one most likely to stop a run that the memory
        arithmetic said would work.
    assumptions, catalog
        Overridable assumptions and an injectable catalogue.

    Returns
    -------
    Streaming
        The full result, including the verdict and why.
    """
    a = assumptions or StreamingAssumptions()
    cat = catalog or load_catalog()
    m = find_model(cat, model)
    warnings: list[str] = []

    osh.check(device_gib > 0, "device_gib must be positive.")

    # The class is resolved either way: a measured read bandwidth says nothing
    # about the page-cache re-read rate, and defaulting the second to the first
    # would quietly make a measured figure govern a number nobody measured.
    entry = find_storage(storage, cat)
    disk_source = "measured"
    if disk_gbs is None:
        disk_source = "catalogue"
        disk_gbs = float(entry["read_gbs"])
        if str(entry.get("source")) == "vendor":
            warnings.append(
                f"{storage}: {disk_gbs:.1f} GB/s is the vendor's peak sequential figure, not a "
                "measurement of your drive. A full, warm or externally attached device runs at "
                "a fraction of it. Measure yours: python scripts/bench_disk.py"
            )
    osh.check(disk_gbs > 0, "disk_gbs must be positive.")
    cache_rate = float(cache_gbs if cache_gbs else (entry.get("cached_gbs") or disk_gbs))

    total, label = checkpoint_gib(m, quant=quant, compression=a.compression)
    native = native_checkpoint_gib(m, quant=quant, compression=a.compression)
    peak_gib, steady_gib = split_disk_gib(native, total)
    free_gib = free_disk_gib(shards_dir)
    if free_gib is not None and free_gib < peak_gib:
        warnings.append(
            f"The split needs {peak_gib:.0f} GiB free while it runs -- the download "
            f"({native:.0f} GiB) and the shards ({total:.0f} GiB) are both on disk at once -- "
            f"and {shards_dir} has {free_gib:.0f} GiB. This is the constraint that stops a run "
            "the memory arithmetic said would work. Afterwards it settles to "
            f"{steady_gib:.0f} GiB, reachable only with --delete-original."
        )
    shard, layers, assumed = shard_gib(m, total)
    if assumed:
        warnings.append(
            f"{model}: the catalogue does not publish a layer count, so one shard is sized at "
            f"1/{ASSUMED_LAYERS} of the checkpoint ({shard:.2f} GiB). The throughput below does "
            "not depend on it -- only on the checkpoint's total size -- but the memory "
            "requirement does."
        )

    # --- context: the KV cache is resident, and it is the thing that binds ---
    shards_gib = shard * PREFETCH_DEPTH
    room = device_gib - shards_gib - a.device_overhead_gib
    if room <= 0:
        return Streaming(
            model_id=model,
            quant=label,
            storage=storage,
            disk_source=disk_source,
            disk_gbs=round(disk_gbs, 2),
            cache_gbs=round(cache_rate, 2),
            context=0,
            layers=layers,
            layers_assumed=assumed,
            checkpoint_gib=round(total, 1),
            native_gib=round(native, 1),
            split_peak_gib=peak_gib,
            split_steady_gib=steady_gib,
            free_disk_gib=None if free_gib is None else round(free_gib, 1),
            shard_gib=round(shard, 2),
            cached_gib=0.0,
            streamed_gib=0.0,
            device_need_gib=round(shards_gib + a.device_overhead_gib, 1),
            kv_gib=0.0,
            seconds_per_token=0.0,
            tps=0.0,
            answer_tokens=a.answer_tokens,
            answer_seconds=0.0,
            prefill_seconds=0.0,
            resident_tps=None,
            slowdown=None,
            verdict="impractical",
            warnings=[
                *warnings,
                f"Streaming needs {shards_gib:.1f} GiB for {PREFETCH_DEPTH} resident shards plus "
                f"{a.device_overhead_gib:.1f} GiB of activations and context, and the device has "
                f"{device_gib:.0f} GiB. Layer streaming removes the capacity wall for the "
                "checkpoint; it does not remove it for a single layer.",
            ],
            assumptions=asdict(a),
        )

    ctx = min(int(context or m["max_context"]), int(m["max_context"]))
    kv = kv_gib(m, ctx, a.kv_dtype)
    while kv > room and ctx > 1024:
        ctx //= 2
        kv = kv_gib(m, ctx, a.kv_dtype)
    if ctx < int(context or m["max_context"]):
        warnings.append(
            f"Context cut to {ctx:,} tokens: the KV cache has to sit beside the resident shards "
            f"in {device_gib:.0f} GiB, and {int(context or m['max_context']):,} tokens of it "
            f"did not. Streaming moves the weights off the device; the KV cache stays on it."
        )
    if kv > room:
        warnings.append(
            f"Even {ctx:,} tokens of KV cache ({kv:.1f} GiB) exceeds the {room:.1f} GiB left "
            "beside the shards. This machine cannot run the model at any context."
        )

    # --- the page cache, which helps least where it is needed most ----------
    device_need = shards_gib + kv + a.device_overhead_gib
    system_ram = float(
        ram_gib if ram_gib is not None else (device_gib if unified else device_gib * 8)
    )
    if unified:
        # One pool: anything the page cache holds is room the model does not
        # have, so the device's need comes out of the same figure.
        free_for_cache = max(system_ram - device_need - a.host_reserve_gib, 0.0)
    else:
        free_for_cache = max(system_ram - a.host_reserve_gib, 0.0)
    cached = min(total, free_for_cache)
    streamed = max(total - cached, 0.0)

    if streamed <= 0:
        warnings.append(
            f"Free memory ({free_for_cache:.0f} GiB) can hold the whole {total:.0f} GiB "
            "checkpoint, so after the first pass this is not storage-bound at all -- and a "
            "machine that can cache the checkpoint can hold it. A memory-mapped resident "
            "engine (llama.cpp, MLX) is strictly faster here; layer streaming is for the case "
            "where the checkpoint does not fit in memory."
        )

    # --- the roofline -------------------------------------------------------
    eff = a.disk_efficiency
    seconds = (streamed * GIB) / (disk_gbs * eff * GB) + (cached * GIB) / (cache_rate * eff * GB)
    # The KV cache is re-read per token too, out of device memory, and at
    # device bandwidth it is noise next to a checkpoint crossing a disk. It is
    # left out rather than modelled badly, and leaving it out is optimistic,
    # which is the safe direction for a verdict this negative.
    tps = 1.0 / seconds if seconds > 0 else 0.0

    # The comparison worth making is against what the *resident* path would
    # give on the same machine, which reads the active weights rather than all
    # of them. For a dense model the two are the same; for a mixture of
    # experts the gap is the finding -- streaming charges full price for a
    # checkpoint whose whole appeal was that serving it did not.
    resident_tps = None
    slowdown = None
    if memory_gbs:
        active = active_weights_gib(m, quant)
        resident = (active * GIB) / (float(memory_gbs) * 0.70 * GB)
        resident_tps = round(1.0 / resident, 1) if resident > 0 else None
        slowdown = round(seconds / resident, 1) if resident > 0 else None

    answer_seconds = seconds * a.answer_tokens
    verdict = _verdict(tps, answer_seconds, a)

    return Streaming(
        model_id=model,
        quant=label,
        storage=storage,
        disk_source=disk_source,
        disk_gbs=round(disk_gbs, 2),
        cache_gbs=round(cache_rate, 2),
        context=ctx,
        layers=layers,
        layers_assumed=assumed,
        checkpoint_gib=round(total, 1),
        native_gib=round(native, 1),
        split_peak_gib=peak_gib,
        split_steady_gib=steady_gib,
        free_disk_gib=None if free_gib is None else round(free_gib, 1),
        shard_gib=round(shard, 2),
        cached_gib=round(cached, 1),
        streamed_gib=round(streamed, 1),
        device_need_gib=round(device_need, 1),
        kv_gib=round(kv, 2),
        seconds_per_token=round(seconds, 3),
        tps=round(tps, 3),
        answer_tokens=a.answer_tokens,
        answer_seconds=round(answer_seconds, 1),
        # One pass over the layers, whatever the prompt length.
        prefill_seconds=round(seconds, 3),
        resident_tps=resident_tps,
        slowdown=slowdown,
        verdict=verdict,
        warnings=warnings,
        assumptions=asdict(a),
    )


# ---------------------------------------------------------------------------
# The machine
# ---------------------------------------------------------------------------

#: Unified memory macOS keeps for itself and will not let a graphics context
#: wire down. The catalogue's own Apple entries use the same convention --
#: 96 GiB of installed memory is listed as 90 usable -- so the detected path
#: and the catalogue path agree instead of disagreeing by a constant.
#: ``sysctl iogpu.wired_limit_mb`` moves it, and raising it is the first thing
#: to try on a machine that just misses.
APPLE_WIRED_RESERVE_GIB = 6.0


@dataclass
class Machine:
    """Where the weights would be read from and held, on one machine.

    Attributes
    ----------
    name : str
        What to call it in a report.
    device_gib : float
        Memory the resident shards and the KV cache live in.
    ram_gib : float
        System memory, which is where the page cache lives.
    unified : bool
        True when ``device_gib`` and ``ram_gib`` name the same physical pool.
    memory_gbs : float or None
        Memory bandwidth, for the resident-versus-streaming comparison. None
        when it is not known, in which case the comparison is omitted rather
        than guessed.
    storage : str
        Catalogue storage-class id.
    disk_gbs : float or None
        A measured read bandwidth, when one has been supplied. Always
        preferred over the class.
    cache_gbs : float or None
        A measured page-cache re-read rate. Separate from ``disk_gbs``
        because measuring one does not measure the other.
    source : str
        ``'catalogue'`` or ``'detected'``, so a report can say which.
    """

    name: str
    device_gib: float
    ram_gib: float
    unified: bool
    memory_gbs: float | None
    storage: str
    disk_gbs: float | None = None
    cache_gbs: float | None = None
    source: str = "catalogue"


def machine_from_catalog(
    accelerator: str,
    *,
    ram_gib: float | None = None,
    catalog: dict[str, Any] | None = None,
) -> Machine:
    """One catalogue accelerator, as a streaming target.

    An entry marked ``unified: true`` is a complete machine with one memory
    pool; a card is not, and its host's system memory is a fact the catalogue
    does not carry. Pass ``ram_gib`` for the card case; the default is the
    larger of 32 GiB and the card itself, which is deliberately on the low
    side -- host memory only enters this arithmetic as page cache, where
    assuming more of it makes the answer look better than it is.
    """
    cat = catalog or load_catalog()
    from ai_bunker.sizing import find_accelerator

    accel = find_accelerator(cat, accelerator)
    unified = bool(accel.get("unified"))
    device = float(accel["vram_gib"])
    return Machine(
        name=str(accel.get("name") or accelerator),
        device_gib=device,
        ram_gib=float(
            ram_gib if ram_gib is not None else (device if unified else max(32.0, device))
        ),
        unified=unified,
        memory_gbs=float(accel["bandwidth_gbs"]),
        storage=str(accel.get("storage") or "nvme-gen4"),
        source="catalogue",
    )


def machine_from_host(host: dict[str, Any] | None = None) -> Machine:
    """This machine, as a streaming target.

    Built from :func:`ai_bunker.sizing.detect_machine`, which is to say from
    ``os-helper``. Two facts it cannot supply are named rather than invented:
    **memory bandwidth**, which no portable interface reports and which is
    therefore left None, and **storage bandwidth**, which is defaulted to a
    class by platform and should be replaced by a measurement --
    ``python scripts/bench_disk.py``.
    """
    from ai_bunker.sizing import detect_machine

    info = host or detect_machine()
    ram = float(info.get("ram_gb") or 0.0)
    unified_gb = info.get("apple_unified_gb")
    discrete = float(info.get("discrete_vram_gb") or 0.0)

    if unified_gb:
        device = max(float(unified_gb) - APPLE_WIRED_RESERVE_GIB, 1.0)
        return Machine(
            name=str(info.get("apple_chip") or info.get("cpu") or "this machine"),
            device_gib=device,
            ram_gib=float(unified_gb),
            unified=True,
            memory_gbs=None,
            storage="apple-nvme",
            source="detected",
        )
    if discrete > 0:
        return Machine(
            name=str((info.get("gpus") or [{}])[0].get("name") or info.get("gpu_vendor") or "GPU"),
            device_gib=discrete,
            ram_gib=ram or max(32.0, discrete),
            unified=False,
            memory_gbs=None,
            storage="nvme-gen4",
            source="detected",
        )
    # No accelerator at all. System memory *is* the device, and that is the
    # case layer streaming was written for.
    osh.check(ram > 0, "Could not detect any memory on this machine.")
    return Machine(
        name=f"{info.get('cpu') or 'CPU'} (no accelerator)",
        device_gib=ram,
        ram_gib=ram,
        unified=True,
        memory_gbs=None,
        storage="nvme-gen4",
        source="detected",
    )


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------


def normalise_mode(value: object) -> str:
    """Canonicalise one of the spellings in :data:`MODE_ALIASES`.

    Parameters
    ----------
    value : object
        ``'auto'``, ``'always'``, ``'never'``, or any accepted alias.
        ``None`` and ``''`` resolve to ``'auto'``.

    Returns
    -------
    str
        One of :data:`MODES`.
    """
    if value is None or str(value).strip() == "":
        return "auto"
    key = str(value).strip().lower()
    osh.check(
        key in MODE_ALIASES,
        f"Unknown mode {value!r}. Known: {', '.join(sorted(set(MODE_ALIASES)))}",
    )
    return MODE_ALIASES[key]


def requested_mode(explicit: object = None, env: dict[str, str] | None = None) -> str:
    """The mode in force: what was asked for, else the environment, else auto.

    Precedence mirrors ``best_engine_ai_helper.offload.requested`` exactly --
    an explicit value wins, :data:`MODE_ENV_VAR` is the fallback, ``auto`` is
    the default -- so one suite-wide switch produces one answer whichever tool
    is asked.

    Note what this means for the kill switch: ``BEST_ENGINE_AIRLLM=never``
    stops the fallback engaging anywhere, and an explicit ``--mode always``
    still overrides it. That is deliberate and it is the sibling's rule: a
    person typing a flag now is more present than a variable set in a profile
    once, and the override is visible in the command somebody ran.
    """
    if explicit is not None and str(explicit).strip() != "":
        return normalise_mode(explicit)
    import os

    source = os.environ if env is None else env
    return normalise_mode(source.get(MODE_ENV_VAR))


@dataclass
class Choice:
    """Which engine should serve one model on one machine, and why."""

    model_id: str
    machine: str
    mode: str
    engine: str
    activated: bool
    reason: str
    resident_fits: bool
    resident_tps: float
    streaming: Streaming | None
    floor: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["streaming"] = self.streaming.to_dict() if self.streaming else None
        return d


def choose_engine(
    *,
    model: str,
    machine: Machine,
    mode: str | None = None,
    floor: str = "batch",
    context: int | None = None,
    quant: str | None = None,
    shards_dir: str | None = None,
    assumptions: StreamingAssumptions | None = None,
    catalog: dict[str, Any] | None = None,
) -> Choice:
    """Decide whether to stream the model off storage, and say why either way.

    The three modes are the three honest positions an operator can hold, they
    are spelled the way ``best-engine-ai-helper`` spells them, and the default
    is the middle one.

    ``never``
        Do not stream. If the model does not fit, the answer is that it does
        not fit, and the report still says what streaming *would* cost so the
        decision can be made with the number in hand rather than without it.
        ``off`` is an accepted alias.
    ``auto``
        Stream only when the model does not fit resident **and** the result
        clears ``floor``. This is the "decide from the running machine"
        position, and it is what makes the fallback safe to leave configured:
        on a machine where streaming would be useless it does not engage.
    ``always``
        Stream because a human said so. The report still carries the cost,
        and it still objects when the model would have fitted -- streaming a
        model that fits is strictly slower, with no compensating benefit.
        ``on`` is an accepted alias.

    ``mode=None`` -- the default -- resolves through :func:`requested_mode`, so
    ``BEST_ENGINE_AIRLLM`` in the environment is honoured and the suite has one
    switch rather than two.

    What ``auto`` deliberately does not do
    --------------------------------------
    It does not switch engines underneath a running gateway. A coding agent
    pointed at an engine that answers at a fifth of a token per second does
    not degrade; it hangs, the client times out, and the operator debugs a
    network problem that is not one. So the automatic part of automatic is the
    **decision**, computed from the machine in front of you and printed with
    the command it implies. A human still starts the engine, which is the same
    rule this project applies to a premium route: the expensive, surprising
    path is one somebody writes down.

    Parameters
    ----------
    model : str
        Catalogue model id.
    machine : Machine
        Where it would run. :func:`machine_from_host` or
        :func:`machine_from_catalog`.
    mode : {'auto', 'always', 'never'}, optional
        The activation policy above, in any spelling
        :data:`MODE_ALIASES` accepts. None reads ``BEST_ENGINE_AIRLLM`` and
        falls back to ``'auto'``.
    floor : {'interactive', 'batch', 'overnight', 'impractical'}
        Worst verdict ``auto`` will accept. ``'batch'`` means "an answer
        within the hour or do not bother".
    context, quant, shards_dir, assumptions, catalog
        Passed through to :func:`size_streaming`.

    Returns
    -------
    Choice
        The decision, the reason, and the full streaming sizing whenever one
        was computed.
    """
    from ai_bunker.sizing import Assumptions, size_machine

    mode = requested_mode(mode)
    osh.check(floor in VERDICTS, f"floor must be one of {', '.join(VERDICTS)}, not {floor!r}")
    cat = catalog or load_catalog()
    warnings: list[str] = []

    # Does it fit the ordinary way? Asked of this model alone: the fallback
    # question is never "model plus a vision model plus an embedder", it is
    # "can this machine run the one model at all".
    resident = size_machine(
        accelerator={
            "name": machine.name,
            "vram_gib": machine.device_gib,
            "bandwidth_gbs": machine.memory_gbs or 1.0,
        },
        primary=model,
        with_vision=None,
        with_embeddings=None,
        served_context=context,
        assumptions=Assumptions(),
        catalog=cat,
    )
    fits = resident.verdict != "does-not-fit"

    def _stream() -> Streaming:
        return size_streaming(
            model=model,
            device_gib=machine.device_gib,
            ram_gib=machine.ram_gib,
            unified=machine.unified,
            storage=machine.storage,
            disk_gbs=machine.disk_gbs,
            cache_gbs=machine.cache_gbs,
            memory_gbs=machine.memory_gbs,
            context=context,
            quant=quant,
            shards_dir=shards_dir,
            assumptions=assumptions,
            catalog=cat,
        )

    if machine.memory_gbs is None:
        warnings.append(
            f"{machine.name}: memory bandwidth is not something os-helper can read, so the "
            "resident comparison is omitted. Pass --bandwidth, or size a catalogue machine "
            "with --accelerator, to get it."
        )

    streaming = _stream()
    worse_than_floor = VERDICTS.index(streaming.verdict) > VERDICTS.index(floor)

    if mode == "never":
        return Choice(
            model_id=model,
            machine=machine.name,
            mode=mode,
            engine="resident" if fits else "none",
            activated=False,
            reason=(
                f"{model} fits in {machine.device_gib:.0f} GiB and is served resident; the "
                "fallback was not consulted."
                if fits
                else f"{model} does not fit in {machine.device_gib:.0f} GiB and the mode is "
                f"`never`. Streaming it would give {streaming.tps:.2f} tok/s "
                f"({streaming.verdict}); pass --mode auto to let that decide, or --mode always to "
                "take it anyway."
            ),
            resident_fits=fits,
            resident_tps=resident.single_stream_tps,
            streaming=streaming,
            floor=floor,
            warnings=warnings + streaming.warnings,
        )

    if mode == "auto":
        if fits:
            reason = (
                f"{model} fits in {machine.device_gib:.0f} GiB. Streaming a model that fits is "
                "strictly slower with nothing to show for it, so the fallback stays off."
            )
            engine, activated = "resident", False
        elif worse_than_floor:
            reason = (
                f"{model} does not fit in {machine.device_gib:.0f} GiB, and streaming it is "
                f"{streaming.verdict} ({streaming.tps:.2f} tok/s, "
                f"{streaming.answer_seconds / 60:.0f} min for a "
                f"{streaming.answer_tokens}-token answer) against a floor of {floor}. Not "
                "activated: a smaller model, a harder quantization or a bigger machine all "
                "beat this."
            )
            engine, activated = "none", False
        else:
            reason = (
                f"{model} does not fit in {machine.device_gib:.0f} GiB. Streaming it off "
                f"{machine.storage} gives {streaming.tps:.2f} tok/s "
                f"({streaming.answer_seconds / 60:.0f} min for a {streaming.answer_tokens}-token "
                f"answer), which clears the {floor} floor."
            )
            engine, activated = "airllm", True
            warnings.append(
                "Activated, and still not an interactive engine: at "
                f"{streaming.tps:.2f} tok/s a coding agent pointed at this will look like a "
                "hung network, not a slow model. Route work to it by need -- `offline`, "
                "`overnight` -- and leave the interactive needs on something resident."
            )
        return Choice(
            model_id=model,
            machine=machine.name,
            mode=mode,
            engine=engine,
            activated=activated,
            reason=reason,
            resident_fits=fits,
            resident_tps=resident.single_stream_tps,
            streaming=streaming,
            floor=floor,
            warnings=warnings + streaming.warnings,
        )

    # mode == "always": the human has decided, and the report still has to be true.
    if fits:
        warnings.append(
            f"{model} fits in {machine.device_gib:.0f} GiB. Streaming it anyway reads the whole "
            f"checkpoint off {machine.storage} for every token instead of out of memory"
            + (f", which is {streaming.slowdown:.0f} times slower" if streaming.slowdown else "")
            + ". This is what --mode always means; it is almost never what anybody wants."
        )
    if streaming.verdict == "impractical":
        warnings.append(
            "The verdict is `impractical`: at "
            f"{streaming.tps:.3f} tok/s a {streaming.answer_tokens}-token answer takes "
            f"{streaming.answer_seconds / 3600:.1f} hours. Activated because --mode always was "
            "asked for, not because it is a good idea."
        )
    return Choice(
        model_id=model,
        machine=machine.name,
        mode=mode,
        engine="airllm",
        activated=True,
        reason=(
            f"--mode always: streaming {model} off {machine.storage} at {streaming.tps:.2f} tok/s "
            f"({streaming.verdict}), by hand rather than by arithmetic."
        ),
        resident_fits=fits,
        resident_tps=resident.single_stream_tps,
        streaming=streaming,
        floor=floor,
        warnings=warnings + streaming.warnings,
    )


# ---------------------------------------------------------------------------
# What to run
# ---------------------------------------------------------------------------


def engine_command(
    choice: Choice,
    *,
    port: int = 8003,
    shards_dir: str = "~/.cache/ai-bunker/shards",
    catalog: dict[str, Any] | None = None,
) -> str:
    """The exact command this decision implies, with the flags worth not forgetting.

    Mirrors :func:`ai_bunker.sizing.serve_command` for the resident path: the
    context the KV cache actually fits, the compression that is the only knob
    with real leverage here, and a shard directory, because the default lands
    beside the checkpoint and wants as much room again.

    ``--model`` is emitted as a **path**, not as the catalogue's repository id,
    because ``ai-bunker airllm serve`` refuses a repository id without
    ``--allow-download`` -- and a generated command that the tool generating it
    would reject is worse than no command. The download form follows as a
    comment, with the flag visible, which is what "the decision is written
    down" means here.
    """
    osh.check(choice.streaming is not None, "This choice carries no streaming sizing.")
    s = choice.streaming
    assert s is not None  # for type checkers; osh.check already raised
    cat = catalog or load_catalog()
    m = find_model(cat, choice.model_id)
    ref = str(m.get("hf") or choice.model_id)
    leaf = ref.rsplit("/", 1)[-1]

    parts = [
        f"ai-bunker airllm serve --model /models/{leaf}",
        f"  --port {port}",
        f"  --context {s.context}",
        f"  --shards {shards_dir}",
    ]
    compression = (s.assumptions or {}).get("compression")
    if compression:
        parts.append(f"  --compression {compression}")
    return " \\\n".join(parts) + (
        "\n"
        "# Point --model at the checkpoint you already have. To fetch it instead,\n"
        "# which reaches a third party, say so:\n"
        f"#   --model {ref} --allow-download"
    )


def upstream_snippet(choice: Choice, *, name: str = "fallback", port: int = 8003) -> str:
    """The ``gateway.yaml`` stanza that puts the engine behind the gateway.

    There is no fallback-specific configuration key, and that is the point.
    The engine speaks the dialect the gateway already proxies, so it is an
    upstream like any other and every guarantee -- screening, the budget, the
    decision log, the breaker -- applies to it unchanged.
    """
    osh.check(choice.streaming is not None, "This choice carries no streaming sizing.")
    s = choice.streaming
    assert s is not None
    cat = load_catalog()
    ref = str(find_model(cat, choice.model_id).get("hf") or choice.model_id)
    # The same reference `engine_command` serves, so the two blocks an operator
    # copies in one sitting agree with each other.
    served = f"/models/{ref.rsplit('/', 1)[-1]}"
    return "\n".join(
        [
            "upstreams:",
            f"  {name}:",
            f"    base_url: http://127.0.0.1:{port}/v1",
            f"    served_context: {s.context}",
            "    remote: false",
            f"    model: {served}",
            "",
            "needs:",
            "  # Route the slow work here by name, never the interactive work:",
            "  #   curl -H 'X-AI-Bunker-Need: offline' ...",
            f"  offline: {name}",
        ]
    )
