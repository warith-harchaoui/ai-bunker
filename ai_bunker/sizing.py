"""
Size a serving machine: what it can hold, how fast it answers, how many people
it carries.

The question this module answers is not "does the model fit". Capacity is the
easy half and the half that misleads: a machine with plenty of memory and a
narrow memory bus loads a large model comfortably and then answers too slowly
to be used. Decoding a token requires streaming the active weights out of
memory, so **bandwidth decides speed, and speed decides headcount**.

The model used here is the standard memory-roofline one for batched
autoregressive decode. In one decode step a server reads, once, the active
weights, plus the KV cache of every sequence currently in flight::

    bytes_per_step   = active_weights + sum(kv_bytes of in-flight sequences)
    steps_per_second = bandwidth * efficiency / bytes_per_step
    per_stream_tps   = steps_per_second          (one token per sequence per step)
    aggregate_tps    = per_stream_tps * batch

Two consequences drive every number below. Per-stream speed is roughly flat in
batch size while the weights dominate the read, then falls once the KV cache
overtakes them -- which is why a long-context deployment runs out of *speed*
before it runs out of *memory*. And a machine whose weights alone exceed
``bandwidth * efficiency / comfort_tps`` cannot reach the comfort floor at any
batch size, including one.

Everything the module cannot measure is a named, overridable assumption
(:class:`Assumptions`), reported alongside the result. Hardware facts come from
``os-helper``; the model and accelerator facts come from ``catalog/serving.yaml``.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import os_helper as osh
import yaml

GIB = 1024**3
GB = 1000**3

#: Two machines whose total cost differs by less than this are the same budget
#: decision; pick the one with more headroom rather than the one that is
#: nominally cheaper.
PRICE_TIE = 0.15

#: Largest team a runtime with parallel-but-not-paged batching (Ollama, MLX)
#: should be asked to serve. Above this the lack of paged attention stops being
#: a tax and starts being the bottleneck.
BASIC_BATCHING_MAX_TEAM = 4

#: Repository-bundled serving catalogue.
CATALOG_PATH = Path(__file__).resolve().parent.parent / "catalog" / "serving.yaml"


# ---------------------------------------------------------------------------
# Assumptions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Assumptions:
    """Everything the sizing cannot measure, named so it can be argued with.

    Attributes
    ----------
    efficiency : float
        Fraction of theoretical memory bandwidth a tuned vLLM actually
        achieves on decode. 0.70 is the conventional working figure; it
        absorbs kernel overhead, attention cost, and scheduler gaps.
    comfort_tps : float
        Per-stream tokens/second below which an interactive coding agent stops
        feeling interactive. At 20 tok/s a 1,500-token edit lands in ~75 s; at
        5 tok/s the same edit takes five minutes and the human leaves.
    avg_live_context : int
        Average number of tokens held by a session actually in flight -- the
        single most expensive assumption here, and the one a harness controls.
        A disciplined agent (bounded reads, an indexed charter instead of a
        pasted one, early compaction) holds around 32k on average even when
        served 256k. An undisciplined one fills whatever it is given and lands
        near 64k, which roughly halves the number of sessions a card carries.
        The discipline is not hygiene; it is hardware you do not have to buy.
    duty_cycle : float
        Fraction of a working session's wall time spent decoding. Agentic
        coding is bursty but dense -- the agent reasons, edits, and re-reads
        while the human watches.
    simultaneity : float
        Fraction of the team in a live session at the same moment during peak
        hours. Meetings, reviews, and timezones are the rest.
    vram_overhead_gib : float
        CUDA context, activations, fragmentation, and the slack
        ``--gpu-memory-utilization`` leaves behind.
    declared_fraction : float
        What fraction of the served context to declare to clients. Clients
        estimate tokens with their own rule and under-count; the server counts
        for real and refuses. 0.80 absorbs that gap.
    """

    efficiency: float = 0.70
    comfort_tps: float = 20.0
    avg_live_context: int = 32768
    duty_cycle: float = 0.25
    simultaneity: float = 0.50
    vram_overhead_gib: float = 4.0
    declared_fraction: float = 0.80

    def people_per_stream(self) -> float:
        """How many registered users one in-flight sequence represents."""
        return 1.0 / (self.duty_cycle * self.simultaneity)


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


def load_catalog(path: str | Path | None = None) -> dict[str, Any]:
    """Load the bundled serving catalogue.

    Parameters
    ----------
    path : str or Path, optional
        Override the catalogue location. Defaults to :data:`CATALOG_PATH`.

    Returns
    -------
    dict
        ``{"models": [...], "accelerators": [...]}``.
    """
    p = Path(path) if path else CATALOG_PATH
    osh.check(osh.file_exists(str(p)), f"Serving catalogue not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    osh.check("models" in data and "accelerators" in data, f"Malformed catalogue: {p}")
    return data


def _by_id(entries: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {e[key]: e for e in entries}


def find_model(catalog: dict[str, Any], model_id: str) -> dict[str, Any]:
    """Return one catalogue model by id, with a listing in the error if absent."""
    index = _by_id(catalog["models"], "id")
    osh.check(
        model_id in index,
        f"Unknown model {model_id!r}. Known: {', '.join(sorted(index))}",
    )
    return index[model_id]


def find_accelerator(catalog: dict[str, Any], accel_id: str) -> dict[str, Any]:
    """Return one catalogue accelerator by id, with a listing in the error if absent."""
    index = _by_id(catalog["accelerators"], "id")
    osh.check(
        accel_id in index,
        f"Unknown accelerator {accel_id!r}. Known: {', '.join(sorted(index))}",
    )
    return index[accel_id]


# ---------------------------------------------------------------------------
# Memory arithmetic
# ---------------------------------------------------------------------------


def kv_gib(model: dict[str, Any], context: int, dtype: str = "fp8") -> float:
    """KV-cache size for one sequence at ``context`` tokens, in GiB.

    Computed from published attention geometry when the catalogue carries it::

        bytes/token = 2 (K and V) * layers * kv_heads * head_dim * bytes_per_element

    and taken from the catalogue's measured ``gib_per_1k`` rate otherwise (used
    for MoE and MLA models whose geometry is not published). The geometric path
    was checked against our own measurements: a 40-layer, 8-KV-head,
    128-head-dim model costs 160 KiB/token in bf16, which is 5.0 GiB at 32k and
    20.0 GiB at 128k -- the figures we recorded.

    Parameters
    ----------
    model : dict
        A catalogue model entry.
    context : int
        Sequence length in tokens.
    dtype : {'fp8', 'bf16', 'fp16'}
        KV cache storage dtype. ``fp8`` halves the cache for 1-3% of quality
        and is worth it above roughly 7k tokens -- the permanent regime of a
        coding agent.

    Returns
    -------
    float
        GiB of KV cache for a single sequence.
    """
    kv = model.get("kv") or {}
    bytes_per_elem = 1 if dtype == "fp8" else 2

    if "gib_per_1k" in kv:
        # Measured rate; catalogue records it at fp8 storage.
        rate = float(kv["gib_per_1k"]) * (1.0 if dtype == "fp8" else 2.0)
        return rate * context / 1000.0

    osh.check(
        all(k in kv for k in ("layers", "kv_heads", "head_dim")),
        f"Model {model['id']} has neither KV geometry nor a measured rate.",
    )
    per_token = 2 * kv["layers"] * kv["kv_heads"] * kv["head_dim"] * bytes_per_elem
    return per_token * context / GIB


def weights_gib(model: dict[str, Any], quant: str | None = None) -> tuple[float, str]:
    """Weight footprint in GiB for a quantization, defaulting to the recommended one."""
    table = model.get("weights") or {}
    q = quant or model.get("recommended_quant")
    osh.check(
        q in table,
        f"Model {model['id']} has no {q!r} weights. Available: {', '.join(sorted(table))}",
    )
    return float(table[q]), str(q)


def active_weights_gib(model: dict[str, Any], quant: str | None = None) -> float:
    """Weights actually read per decode step.

    For a dense model this is the whole checkpoint. For a mixture of experts it
    is far less -- which is the entire point of serving one: a 3B-active, 80B-total
    model decodes with the memory traffic of a small model.

    The figure is deliberately pessimistic for MoE. Batching widens the set of
    experts touched per step (different tokens route differently), so the read
    tends toward the full checkpoint as the batch grows. A floor of 20% of total
    weights keeps a large batch from being credited with single-stream economics.
    """
    total, _ = weights_gib(model, quant)
    fraction = float(model.get("active_fraction", 1.0))
    if fraction >= 1.0:
        return total
    return max(total * fraction, total * 0.20)


# ---------------------------------------------------------------------------
# The sizing itself
# ---------------------------------------------------------------------------


@dataclass
class Plan:
    """One resident model in a deployment plan."""

    model_id: str
    role: str
    quant: str
    weights_gib: float
    max_context: int


@dataclass
class Sizing:
    """The result of sizing one machine for one deployment plan."""

    accelerator: str
    vram_gib: float
    bandwidth_gbs: float
    plan: list[Plan]
    primary: str
    served_context: int
    declared_context: int
    resident_weights_gib: float
    kv_pool_gib: float
    kv_per_session_gib: float
    kv_full_context_gib: float
    sessions_by_memory: int
    sessions_by_speed: int
    concurrent_sessions: int
    binding_constraint: str
    per_stream_tps: float
    single_stream_tps: float
    aggregate_tps: float
    consultants: int
    verdict: str
    warnings: list[str] = field(default_factory=list)
    assumptions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["plan"] = [asdict(p) for p in self.plan]
        return d


def _tps(bandwidth_gbs: float, eff: float, bytes_gib: float) -> float:
    """Decode steps per second given a per-step read of ``bytes_gib`` GiB."""
    if bytes_gib <= 0:
        return math.inf
    return (bandwidth_gbs * eff * GB) / (bytes_gib * GIB)


def size_machine(
    *,
    accelerator: str | dict[str, Any] | None = None,
    vram_gib: float | None = None,
    bandwidth_gbs: float | None = None,
    primary: str = "devstral-small-2-24b",
    with_vision: str | None = "qwen3-vl-32b",
    with_embeddings: str | None = "bge-m3",
    served_context: int | None = None,
    kv_dtype: str = "fp8",
    assumptions: Assumptions | None = None,
    catalog: dict[str, Any] | None = None,
) -> Sizing:
    """Size one machine for one deployment plan.

    Parameters
    ----------
    accelerator : str or dict, optional
        A catalogue accelerator id (e.g. ``"rtx-pro-6000-blackwell"``) or an
        inline ``{"name", "vram_gib", "bandwidth_gbs"}`` mapping. Omit it and
        pass ``vram_gib``/``bandwidth_gbs`` to size a hypothetical machine.
    vram_gib, bandwidth_gbs : float, optional
        Override or supply the accelerator's figures.
    primary : str
        Catalogue id of the code model, the one that decides the speed.
    with_vision, with_embeddings : str or None
        Catalogue ids of co-resident models, or None to leave them out. A
        resident VLM is what makes 96 GiB worth more than 80.
    served_context : int, optional
        Context to serve. Defaults to the primary model's maximum, capped so a
        single session's KV cache never exceeds a third of the pool -- serving
        a context no two sessions can hold at once is a paper number.
    kv_dtype : {'fp8', 'bf16'}
        KV cache storage dtype.
    assumptions : Assumptions, optional
        Override the named assumptions.
    catalog : dict, optional
        Injectable catalogue, for tests.

    Returns
    -------
    Sizing
        The full result, including which constraint binds and why.
    """
    a = assumptions or Assumptions()
    cat = catalog or load_catalog()
    warnings: list[str] = []

    # --- resolve the machine ------------------------------------------------
    accel: dict[str, Any] = {}
    if isinstance(accelerator, str):
        accel = find_accelerator(cat, accelerator)
    elif isinstance(accelerator, dict):
        accel = accelerator
    vram = float(vram_gib if vram_gib is not None else accel.get("vram_gib", 0.0))
    bw = float(bandwidth_gbs if bandwidth_gbs is not None else accel.get("bandwidth_gbs", 0.0))
    name = str(accel.get("name") or accelerator or f"{vram:.0f} GiB / {bw:.0f} GB/s")
    osh.check(vram > 0, "vram_gib must be positive (pass an accelerator id or --vram).")
    osh.check(bw > 0, "bandwidth_gbs must be positive (pass an accelerator id or --bandwidth).")

    if accel.get("caveat"):
        warnings.append(str(accel["caveat"]).strip())

    # --- resident plan ------------------------------------------------------
    main = find_model(cat, primary)
    plan: list[Plan] = []
    resident = 0.0
    for mid in [primary, with_vision, with_embeddings]:
        if not mid:
            continue
        m = find_model(cat, mid)
        w, q = weights_gib(m)
        if accel.get("fp8") is False and q == "fp8":
            warnings.append(
                f"{mid}: this accelerator has no FP8 compute. Keep bf16 weights "
                f"({m['weights'].get('bf16', '?')} GiB) and fp8 KV storage, which is supported."
            )
        plan.append(Plan(mid, str(m["role"]), q, w, int(m["max_context"])))
        resident += w

    pool = vram - resident - a.vram_overhead_gib
    if pool <= 0:
        return Sizing(
            accelerator=name,
            vram_gib=vram,
            bandwidth_gbs=bw,
            plan=plan,
            primary=primary,
            served_context=0,
            declared_context=0,
            resident_weights_gib=round(resident, 1),
            kv_pool_gib=round(pool, 1),
            kv_per_session_gib=0.0,
            kv_full_context_gib=0.0,
            sessions_by_memory=0,
            sessions_by_speed=0,
            concurrent_sessions=0,
            binding_constraint="memory",
            per_stream_tps=0.0,
            single_stream_tps=0.0,
            aggregate_tps=0.0,
            consultants=0,
            verdict="does-not-fit",
            warnings=[
                *warnings,
                f"The plan needs {resident:.0f} GiB of weights plus "
                f"{a.vram_overhead_gib:.0f} GiB of overhead and the card has {vram:.0f} GiB. "
                "Drop a co-resident model or quantize further.",
            ],
            assumptions=asdict(a),
        )

    # --- context ------------------------------------------------------------
    ctx = min(int(served_context or main["max_context"]), int(main["max_context"]))
    full_kv = kv_gib(main, ctx, kv_dtype)

    # A served context no single sequence can hold is a brochure number. Paged
    # attention means a session only occupies the blocks it has actually filled,
    # so the pool does not need room for everyone at full length -- but it must
    # have room for *someone*.
    while full_kv > pool and ctx > 8192:
        ctx //= 2
        full_kv = kv_gib(main, ctx, kv_dtype)
    if ctx < int(main["max_context"]):
        warnings.append(
            f"Serving {ctx:,} of the model's {int(main['max_context']):,} tokens: the KV pool "
            f"({pool:.0f} GiB) could not hold even one sequence at full length."
        )

    # What a session in flight actually occupies: paged attention charges for
    # filled blocks, so the live context is the honest figure for both the
    # memory budget and the bandwidth budget.
    live_ctx = min(a.avg_live_context, ctx)
    per_session = kv_gib(main, live_ctx, kv_dtype)
    if a.avg_live_context > ctx:
        warnings.append(
            f"Assumed live context ({a.avg_live_context:,}) exceeds the served context "
            f"({ctx:,}); sizing on the served figure instead."
        )

    # --- speed --------------------------------------------------------------
    active = active_weights_gib(main)
    kv_live = per_session
    single = _tps(bw, a.efficiency, active + kv_live)

    # Largest batch that still clears the comfort floor. Per-step read grows
    # with the batch, so per-stream speed falls; find where it crosses.
    budget_gib = (bw * a.efficiency * GB) / (a.comfort_tps * GIB)
    by_speed = int((budget_gib - active) // kv_live) if kv_live > 0 else 10_000
    by_speed = max(by_speed, 0)
    by_memory = int(pool // per_session) if per_session > 0 else 10_000

    sessions = max(0, min(by_memory, by_speed))
    binding = "speed" if by_speed <= by_memory else "memory"

    if by_speed == 0:
        warnings.append(
            f"This machine cannot reach {a.comfort_tps:.0f} tok/s at ANY batch size with "
            f"{primary}: reading {active:.0f} GiB of active weights per step at "
            f"{bw:.0f} GB/s caps a single stream at {single:.1f} tok/s. This is a bandwidth "
            "wall, not a capacity one -- more memory would not move it."
        )

    per_stream = _tps(bw, a.efficiency, active + max(sessions, 1) * kv_live)
    aggregate = per_stream * max(sessions, 1)
    consultants = team_for_sessions(sessions, a)

    if single >= a.comfort_tps and sessions >= 8:
        verdict = "comfortable"
    elif sessions >= 2 and single >= a.comfort_tps * 0.6:
        verdict = "workable"
    elif sessions >= 1:
        verdict = "single-user"
    else:
        verdict = "unusable-for-agents"

    return Sizing(
        accelerator=name,
        vram_gib=vram,
        bandwidth_gbs=bw,
        plan=plan,
        primary=primary,
        served_context=ctx,
        declared_context=int(ctx * a.declared_fraction),
        resident_weights_gib=round(resident, 1),
        kv_pool_gib=round(pool, 1),
        kv_per_session_gib=round(per_session, 2),
        kv_full_context_gib=round(full_kv, 2),
        sessions_by_memory=by_memory,
        sessions_by_speed=by_speed,
        concurrent_sessions=sessions,
        binding_constraint=binding,
        per_stream_tps=round(per_stream, 1),
        single_stream_tps=round(single, 1),
        aggregate_tps=round(aggregate, 1),
        consultants=consultants,
        verdict=verdict,
        warnings=warnings,
        assumptions=asdict(a),
    )


# ---------------------------------------------------------------------------
# Serve command
# ---------------------------------------------------------------------------


def serve_command(
    sizing: Sizing,
    *,
    model_id: str | None = None,
    port: int = 8000,
    kv_dtype: str = "fp8",
    catalog: dict[str, Any] | None = None,
) -> str:
    """The exact ``vllm serve`` command this sizing implies.

    Includes the flags that are easy to forget and expensive to omit: the
    tool-call parser (without it a coding agent cannot call a tool at all), the
    quantized KV cache, and a batch cap matching the concurrency the sizing
    actually supports.
    """
    cat = catalog or load_catalog()
    m = find_model(cat, model_id or sizing.primary)
    ref = m.get("awq") if m.get("recommended_quant") == "awq4" else m["hf"]
    n = max(sizing.concurrent_sessions, 1)

    parts = [
        f"vllm serve {ref}",
        f"  --port {port}",
        f"  --max-model-len {sizing.served_context}",
        f"  --kv-cache-dtype {kv_dtype}",
        f"  --max-num-seqs {n}",
        "  --max-num-batched-tokens 16384",
        "  --gpu-memory-utilization 0.92",
    ]
    parts += [f"  {flag}" for flag in m.get("vllm_flags", [])]
    return " \\\n".join(parts)


# ---------------------------------------------------------------------------
# This machine
# ---------------------------------------------------------------------------


def detect_machine() -> dict[str, Any]:
    """What os-helper can see about the machine running this code.

    Returns the hardware snapshot plus a ``serving`` verdict: a workstation is
    a place to *call* a bunker from, not a place to be one.
    """
    info = osh.hardware_info()
    discrete = info.get("gpus") or []
    vram = max((float(g.get("memory_gb") or 0) for g in discrete), default=0.0)
    unified = info.get("apple_unified_gb")

    serving = "server" if (info["platform"] == "linux" and vram >= 40) else "client"
    return {
        "platform": info["platform"],
        "cpu": info["cpu"]["model"],
        "cores": info["cpu"]["logical_cores"],
        "ram_gb": info["ram_gb"],
        "gpu_vendor": info["gpu_vendor"],
        "gpus": discrete,
        "discrete_vram_gb": vram or None,
        "apple_unified_gb": unified,
        "apple_chip": info.get("apple_chip"),
        "role": serving,
    }


# ---------------------------------------------------------------------------
# The inverse problem: which machine for a team of N?
# ---------------------------------------------------------------------------


def team_for_sessions(sessions: int, assumptions: Assumptions | None = None) -> int:
    """Largest team that ``sessions`` concurrent sequences can serve.

    The exact inverse of :func:`sessions_for_team`, so the two directions never
    contradict each other. Deliberately NOT ``sessions / (duty * simultaneity)``:
    that mean-based figure is optimistic by roughly a factor of two at the team
    sizes that matter, because it sizes for the average load rather than for
    the busy hour.
    """
    if sessions <= 0:
        return 0
    n = 1
    while n < 10_000 and sessions_for_team(n + 1, assumptions) <= sessions:
        n += 1
    return n


def _binomial_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p), computed directly."""
    total = 0.0
    for i in range(0, k + 1):
        total += math.comb(n, i) * (p**i) * ((1 - p) ** (n - i))
    return total


def sessions_for_team(
    team_size: int, assumptions: Assumptions | None = None, *, quantile: float = 0.95
) -> int:
    """How many sequences must be in flight to serve a team of ``team_size``.

    Not ``team_size * duty_cycle``. An average is the wrong statistic for a
    capacity question: a machine sized for the mean is overloaded half the
    time. Each person is modelled as independently decoding with probability
    ``duty_cycle * simultaneity``, and the machine is sized for the 95th
    percentile of that binomial -- busy enough to be rare, not busy enough to
    be never.

    Small teams get a floor of two concurrent sequences regardless. Below a
    handful of people the averaging that makes the percentile meaningful does
    not happen, and the failure the floor prevents is the obvious one: one
    colleague's long generation blocking the other's entirely.

    Parameters
    ----------
    team_size : int
        People who will use the deployment.
    assumptions : Assumptions, optional
        Supplies ``duty_cycle`` and ``simultaneity``.
    quantile : float
        Load percentile to size for. 0.95 means the machine is at capacity
        roughly one working hour in twenty.

    Returns
    -------
    int
        Concurrent sequences the machine must sustain above the comfort floor.
    """
    a = assumptions or Assumptions()
    osh.check(team_size >= 1, "team_size must be at least 1.")
    p = max(min(a.duty_cycle * a.simultaneity, 1.0), 1e-6)
    k = 0
    while k < team_size and _binomial_cdf(k, team_size, p) < quantile:
        k += 1
    return max(k, min(team_size, 2))


@dataclass
class Recommendation:
    """One candidate machine, judged against a team size."""

    accelerator_id: str
    sizing: Sizing
    sessions_needed: int
    fits: bool
    price_usd: float
    node_usd: float
    total_usd: float
    usd_per_person: float | None
    batching: str
    disqualified: str | None = None


def recommend_for_team(
    team_size: int,
    *,
    primary: str = "devstral-small-2-24b",
    with_vision: str | None = "qwen3-vl-32b",
    with_embeddings: str | None = "bge-m3",
    served_context: int | None = None,
    kv_dtype: str = "fp8",
    assumptions: Assumptions | None = None,
    catalog: dict[str, Any] | None = None,
    shared_server: bool = True,
) -> list[Recommendation]:
    """Rank every catalogue accelerator against a team size, cheapest fit first.

    Parameters
    ----------
    team_size : int
        People the deployment must serve.
    shared_server : bool
        When True (a machine several people share), an accelerator without a
        production continuous-batching runtime is disqualified however fast it
        is: without batching, concurrent sessions queue rather than share, and
        the second user waits for the first to finish. Set False to size a
        single-person workstation, where the limitation does not apply.

    Returns
    -------
    list of Recommendation
        Candidates that fit, cheapest first, then the ones that do not.
    """
    a = assumptions or Assumptions()
    cat = catalog or load_catalog()
    needed = sessions_for_team(team_size, a)

    out: list[Recommendation] = []
    for accel in cat["accelerators"]:
        s = size_machine(
            accelerator=accel["id"],
            primary=primary,
            with_vision=with_vision,
            with_embeddings=with_embeddings,
            served_context=served_context,
            kv_dtype=kv_dtype,
            assumptions=a,
            catalog=cat,
        )
        batching = str(accel.get("batching", "unknown"))
        disq = None
        if shared_server and batching == "none":
            disq = (
                "no concurrency at all: sessions queue, so the second user waits "
                "for the first to finish"
            )
        elif shared_server and batching == "basic" and team_size > BASIC_BATCHING_MAX_TEAM:
            disq = (
                f"Ollama-class parallel requests only (no paged attention): credible up "
                f"to {BASIC_BATCHING_MAX_TEAM} people, not {team_size}"
            )
        fits = s.concurrent_sessions >= needed and s.verdict != "does-not-fit" and disq is None
        card = float(accel.get("price_usd", 0) or 0)
        node = float(accel.get("node_extra_usd", 0) or 0)
        total = card + node
        out.append(
            Recommendation(
                accelerator_id=accel["id"],
                sizing=s,
                sessions_needed=needed,
                fits=fits,
                price_usd=card,
                node_usd=node,
                total_usd=total,
                usd_per_person=(total / team_size) if (fits and team_size) else None,
                batching=batching,
                disqualified=disq,
            )
        )

    # Cheapest machine that does the job wins -- but not by a rounding error.
    # Two cards within a few percent of each other are the same purchase
    # decision, and between them the one with headroom is strictly better:
    # a machine sized to exactly its requirement has nowhere to put the team's
    # next hire. So candidates within PRICE_TIE of the cheapest fit are re-ranked
    # by capacity, and only then by price.
    #
    # The rest follow by how close they came, so a near-miss stays visible
    # instead of merely being absent.
    fitting = [r for r in out if r.fits]
    missing = [r for r in out if not r.fits]
    missing.sort(key=lambda r: -r.sizing.concurrent_sessions)

    if fitting:
        floor = min(r.total_usd for r in fitting)
        tie = floor * (1.0 + PRICE_TIE)
        close = sorted(
            (r for r in fitting if r.total_usd <= tie),
            key=lambda r: (-r.sizing.concurrent_sessions, r.total_usd),
        )
        rest = sorted(
            (r for r in fitting if r.total_usd > tie),
            key=lambda r: r.total_usd,
        )
        fitting = close + rest

    return fitting + missing
