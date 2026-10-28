"""
Which model to serve, asked rather than assumed.

This module exists to delete three string literals. ``sizing.py`` used to
default to ``primary="devstral-small-2-24b"`` and ``with_vision="qwen3-vl-32b"``,
and the README said, for several releases, that **ai-bunker describes its needs
in a brief and lets the helper choose; it never hardcodes a model name**. The
second half of that sentence was false in six places, which is the kind of
claim this repository has a linter for and had not pointed at itself.

So the choice is now a question put to
`best-engine-ai-helper <https://github.com/warith-harchaoui/best-engine-ai-helper>`_,
which is the suite's answer to "which model, on what hardware, through which
backend" and has been all along.

What is asked, and what is answered
-----------------------------------
The helper's ``recommend_engines`` takes a catalogue, a hardware budget and a
task in words. It is not asked about *its* catalogue, which is the workstation
one -- Ollama tags, models that fit a laptop. It is asked about **this**
project's catalogue, the server one, translated into the shape it expects:

    ai-bunker ``catalog/serving.yaml``  ->  helper entry schema  ->  the choice

That translation is :func:`as_helper_entries`, and the join between the two
worlds is a field the helper's own catalogue already carries: ``vllm_id``,
which is the same Hugging Face reference this project stores as ``hf``.

**Which half of the answer is used, and why only that half.** The helper is
asked to *rank*, not to judge fit. Two measured reasons. Its ``headroom``
parameter is documented as clamped to 0.5, which is right for a laptop also
running an editor and wrong for a node doing nothing else. And for a ``vllm``
backend it recomputes the weight footprint from the parameter count at 16 bits
-- 55.2 GB for the 24B this catalogue serves at 26.8 -- because serving an
unquantized checkpoint is the vLLM default, where this project's whole
catalogue is quantized and says so per model.

So the affordable set is decided here, from this catalogue's measured weight
tables, and the helper ranks within it. Each tool is authoritative over the
thing it actually knows: the helper knows which model is *better* for a coding
agent and whether it can honour a schema, this project knows what the weights
weigh.

Three things come free with asking, and all three were missing before:

**The structured-output requirement is enforced rather than assumed.** A coding
agent calls tools, tool calling *is* constrained decoding, and the helper's
``require_structured`` defaults to True. This project had no field for that
capability at all -- it was implied by the presence of a ``--tool-call-parser``
flag in the catalogue and checked by nobody.

**The choice follows the target machine.** Sizing is usually asked about a
machine nobody is standing in front of (``--accelerator rtx-pro-6000-blackwell``),
so the budget handed to the helper is *that* accelerator's memory, not this
laptop's. "Which model should this machine serve" is the question, and the
answer should move when the machine does.

**The reasoning is inspectable.** The helper returns the budget it used, the
headroom it kept, the candidates it rejected and why. :class:`Choice` carries
all of it, :class:`ResolvedPlan` carries one per slot, and ``ai-bunker sizing``
prints the chain under ``WHY THESE MODELS`` instead of a bare name. That last
clause was false for a while: the reasoning was built, attached to nothing and
dropped, so the sentence describing it was a claim about code that did not run.

The fourth slot: a picture
--------------------------
``code``, ``vision`` and ``embed`` are chosen over ``catalog/serving.yaml``,
which is this project's own and records what a *server* needs. ``image`` is
not, and keeps no entry here at all.

The reason is that a diffusion model is not a language model with different
weights. It is three or four networks that take turns -- text encoders, a
denoiser, a decoder -- so its footprint depends on whether they are held at
once or swapped through the accelerator one at a time, and its cost is in
denoising steps rather than tokens, which makes the honest unit *seconds per
image*. None of the columns this catalogue exists for -- weights per
quantization, key-value cache geometry, tool-call parsers -- say anything
about any of that.

The helper already carries that catalogue and that arithmetic
(``imagine_rank``, ``imagine_pick``, ``image_footprint_gb``), so the slot is
delegated whole rather than copied. What this project adds is the one rule the
helper's ``pick`` does not apply, :data:`LEAN_TOLERANCE`: ``pick`` takes the
best image model that runs, which on an 80 GiB card is a 43 GiB pipeline, and
this is a gateway for coding agents whose spare memory is supposed to buy a
better coder.

What is deliberately NOT delegated
----------------------------------
The *arithmetic*. The helper sizes a workstation by memory fit; this project
sizes a server by the memory roofline, the key-value cache geometry and the
concurrency a team needs, over a catalogue carrying weight footprints per
quantization and prices. Those are different questions over different data, and
``catalog/serving.yaml``'s header has said so since before this module existed.
The helper picks **which** model; :mod:`ai_bunker.sizing` works out what it
costs.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import os_helper as osh

from ai_bunker.sizing import find_model, load_catalog

#: The value that means "ask the helper". Not ``None``, which already means
#: "leave this model out of the plan entirely" and has to keep meaning it.
ASK = "auto"

#: Catalogue roles, and the ``kind`` the helper knows them as.
#:
#: ``image`` is the odd one and deliberately so. The other three name models
#: this project's own ``catalog/serving.yaml`` carries; the image slot names
#: none, because a diffusion pipeline is not a vLLM deployment and the figures
#: that decide it -- component footprints, a denoising step count, seconds per
#: image -- are a different arithmetic over different data. The helper already
#: owns all of it (``imagine_rank``, ``imagine_pick``), so the slot is
#: delegated whole rather than copied into a catalogue that would then have to
#: be kept in step with somebody else's.
ROLE_KINDS = {"code": "llm", "vision": "vlm", "embed": "embed", "image": "image"}

#: Which benchmark column each role is ranked and reported on. One table
#: rather than an expression repeated per use, because the repetition is what
#: let the vision slot rank on ``vision`` and publish ``code`` -- a column its
#: models leave empty, so the slot's whole published reasoning read ``None``.
#: An embedder has no column here: this catalogue records no benchmark for the
#: one it carries, and inventing an axis to report zero on would be worse than
#: saying nothing.
AXES = {"code": "code", "vision": "vision", "image": "image"}

#: What this project is for, written out, because that sentence is the input to
#: somebody else's decision and not a comment.
#:
#: ``best-engine-ai-helper`` parses a task in words (``parse_task``) and the
#: parse chooses the scoring axis the ranking then uses. So this is the one
#: place where ai-bunker has to say plainly what it does, and get it right:
#: phrase it loosely and the helper ranks on its general axis, which would
#: recommend a good conversationalist to a machine that has to emit patches.
#:
#: Checked rather than hoped: ``parse_task`` on this string returns
#: ``application="code"`` and ``kinds=["llm"]``, and ``tests/test_engine.py``
#: asserts it, so a rewrite that reads better and ranks worse fails the suite.
TASK = (
    "Serve a sovereign, OpenAI-compatible gateway on one GPU for autonomous coding "
    "agents: read and edit source files across a large repository, call tools, and "
    "return schema-constrained JSON reliably, over a context window of hundreds of "
    "thousands of tokens."
)

#: The same thing for the vision slot, and a separate string because the helper
#: narrows ``kinds`` from the task text -- a sentence about code does not ask
#: for a vision model, and would get ranked as though it had.
#:
#: Deliberately about screenshots and diagrams rather than scanned paper. An
#: earlier phrasing said "scanned documents" and ``parse_task`` answered
#: ``vlm_application="ocr"``, which is a different axis and a different model:
#: this project's vision slot exists so an agent can look at a running
#: application and return a schema, which is what ``docs/SIZING.md`` identified
#: as the one thing Apple's serving stack cannot do.
VISION_TASK = (
    "Serve a vision-language model to a coding agent that reads screenshots and "
    "diagrams of a running application, and must return its findings as "
    "schema-constrained JSON."
)

#: Benchmark points a co-resident model may give up to save memory. The
#: helper's own ``pick`` names this the anti-greed rule and gives the reason
#: this project needs it: a gibibyte of footprint "is paid on every run and
#: competes with the caller's own workload". Here it competes with the coder
#: and with the key-value cache pool, and ``docs/SIZING.md`` spends a section
#: arguing that spare memory should go to **a better coder**.
#:
#: So the vision and embedding slots take the leanest model within this many
#: points of the best, and the code slot takes the best outright. Measured
#: effect on the 72 GiB card: the lean vision model leaves room for the 80B
#: coder, and the greedy one does not.
LEAN_TOLERANCE = 10.0

#: Device memory this project reserves for everything that is not weights --
#: the accelerator context, activations, and the key-value cache pool that
#: makes the machine useful. Used to decide which models the target machine can
#: *afford* before the helper is asked to rank them.
#:
#: Note what is NOT done here: no ``headroom`` is passed to the helper. Its
#: own parameter is documented as clamped to ``MAX_HEADROOM`` (0.5), a figure
#: tuned for a laptop that is also running an editor and a browser, and
#: passing 0.8 to a function that silently clamps it to 0.5 would put a number
#: in this file that does not describe what happens.
OVERHEAD_GIB = 4.0


@dataclass
class Choice:
    """One model, chosen for one machine, with the reasoning kept."""

    role: str
    model_id: str
    asked: bool
    reason: str
    budget_gb: float | None = None
    #: Which benchmark column the ranking was ordered by, so a reader can tell
    #: what :attr:`score` is a score *of*. Carried rather than inferred from
    #: the role, because the two were allowed to disagree once already: the
    #: vision slot was ranked on `vision` and reported on `code`, which is a
    #: column its models leave empty, so every figure the slot published read
    #: `None` and said nothing.
    axis: str = ""
    score: float | None = None
    #: What the chosen model occupies, in GiB. Redundant for the three roles
    #: whose weights ``catalog/serving.yaml`` records, and the only source of
    #: the figure for the image slot, which this project deliberately keeps no
    #: catalogue of. ``None`` means "ask the catalogue", and the image slot is
    #: the one role that cannot be asked.
    weights_gib: float | None = None
    #: The reference that actually serves the model -- a Hugging Face id. For
    #: the three local roles it duplicates the catalogue's ``hf``; for the
    #: image slot it is the only name the runtime understands, since
    #: ``catalog_id`` belongs to the helper's catalogue and not to ours.
    hf: str = ""
    #: Whatever is true of this role and no other. The image slot puts its
    #: output size, its denoising step count and its seconds-per-image here:
    #: three figures that mean nothing for a language model, and promoting
    #: them to fields would leave every other role carrying three nulls.
    detail: dict[str, Any] = field(default_factory=dict)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Translating this project's catalogue into the shape the helper reads
# ---------------------------------------------------------------------------


def _structured(model: dict[str, Any]) -> bool:
    """Whether this model can be driven by a tool-calling agent.

    Read from the vLLM flags the catalogue already carries, because that is
    where the fact lives: a model served without ``--tool-call-parser`` cannot
    emit a tool call an agent can act on, whatever the weights are capable of.
    Inferred rather than stored so there is one source of truth and not two
    that can disagree.
    """
    flags = " ".join(str(f) for f in (model.get("vllm_flags") or []))
    return "--tool-call-parser" in flags or "--enable-auto-tool-choice" in flags


def as_helper_entries(catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """This project's serving catalogue, in the helper's entry schema.

    Only the fields the helper's scoring actually reads are produced, and each
    is taken from the nearest equivalent rather than invented:

    ========================  =======================================
    helper field              from ``catalog/serving.yaml``
    ========================  =======================================
    ``id``                    ``id``
    ``kind``                  ``role``, through :data:`ROLE_KINDS`
    ``size_b``                ``params_b``
    ``ram_gb``/``disk_gb``    the recommended quantization's weights
    ``benchmarks``            ``benchmarks``, on the ``code`` axis
    ``structured_output``     whether a tool-call parser is configured
    ``vllm_id``               ``hf`` -- the join between the two worlds
    ========================  =======================================

    Returns
    -------
    list of dict
        One entry per catalogue model, ready for ``recommend_engines``.
    """
    cat = catalog or load_catalog()
    out: list[dict[str, Any]] = []
    for m in cat["models"]:
        role = str(m.get("role") or "")
        quant = str(m.get("recommended_quant") or "")
        weights = float((m.get("weights") or {}).get(quant) or 0.0)
        bench = dict(m.get("benchmarks") or {})
        swe = bench.get("swe_bench_verified")
        out.append(
            {
                "id": str(m["id"]),
                "kind": ROLE_KINDS.get(role, role),
                "size_b": float(m.get("params_b") or 0.0),
                # GiB in this catalogue, gigabytes in the helper's. The factor
                # is small and ignoring it would quietly shift every budget
                # comparison by 7% in the flattering direction.
                "ram_gb": round(weights * 1.073741824, 1),
                "disk_gb": round(weights * 1.073741824, 1),
                # Mapped onto the helper's axes by name, because the names
                # differ and a missing key ranks as zero rather than failing:
                # the vision slot was being ordered by accident until
                # `openvlm_average` was wired to `vision`.
                "benchmarks": {
                    "code": swe,
                    "general": bench.get("general") or swe,
                    "vision": bench.get("openvlm_average") or bench.get("vision"),
                    "ocr": bench.get("ocr"),
                    "math": bench.get("math"),
                },
                "structured_output": _structured(m),
                "vllm_id": str(m.get("hf") or ""),
                "notes": str(m.get("notes") or "").strip(),
                # Not part of the helper's schema, and carried anyway: this is
                # the measured footprint at the quantization this project
                # serves, and it is what decides affordability before the
                # helper is asked to rank. The helper ignores unknown keys.
                "weights_gib": weights,
            }
        )
    return out


# ---------------------------------------------------------------------------
# The question
# ---------------------------------------------------------------------------


def _fallback(
    role: str,
    reason: str,
    catalog: dict[str, Any],
    affordable: list[dict[str, Any]] | None = None,
) -> Choice:
    """The best-benchmarked catalogue model for a role, said out loud.

    Reached when the helper cannot answer -- it is not installed, it predates
    the ranking, or it raised. The point is that it is *reported*: a silent
    fallback to a literal is the defect this module was written to remove, and
    replacing one silent literal with another would be no improvement.

    ``affordable`` is the set the target machine can actually hold, and passing
    it matters more than it looks. Without it this picks the best-benchmarked
    model for the role regardless of the budget, and the three slots then
    over-commit the card: measured on an 80 GiB H100, the unbudgeted fallback
    produced an 81 GiB plan and turned a machine that fits into
    ``does-not-fit``. The degraded path has to degrade in quality, not in
    arithmetic.
    """
    allowed = {e["id"] for e in affordable} if affordable is not None else None
    # Both sets are kept. The choice is made among the ones the card can hold;
    # the ones it cannot are still named in `rejected`, because "nothing better
    # exists" and "something better exists and does not fit" are different
    # answers and only one of them is an argument for a bigger card.
    role_models = [m for m in catalog["models"] if str(m.get("role")) == role]
    candidates = [m for m in role_models if allowed is None or str(m["id"]) in allowed]
    osh.check(bool(candidates), f"The serving catalogue carries no {role!r} model.")

    def score(m: dict[str, Any]) -> float:
        bench = m.get("benchmarks") or {}
        return float(
            bench.get("swe_bench_verified")
            or bench.get("openvlm_average")
            or bench.get("general")
            or 0.0
        )

    def weight(m: dict[str, Any]) -> float:
        return float((m.get("weights") or {}).get(str(m.get("recommended_quant") or "")) or 0.0)

    best = max(candidates, key=score)
    if role != "code":
        # The same anti-greed rule the ranked path applies, for the same
        # reason: a co-resident model's footprint competes with the coder and
        # the key-value cache pool. Without it the degraded path picks the
        # biggest vision model it can afford *in isolation* and then leaves the
        # coder nowhere to go -- which turned a 48 GiB card that fits into
        # `does-not-fit`, with every individual step having respected its own
        # budget. Degrading in quality is the intent; degrading in arithmetic
        # is not.
        close = [m for m in candidates if score(best) - score(m) <= LEAN_TOLERANCE]
        if close:
            best = min(close, key=weight)
    return Choice(
        role=role,
        model_id=str(best["id"]),
        asked=False,
        reason=reason,
        axis=AXES.get(role, ""),
        score=score(best) or None,
        weights_gib=weight(best) or None,
        hf=str(best.get("hf") or ""),
        rejected=[
            {
                "id": str(m["id"]),
                "weights_gib": weight(m),
                "score": score(m) or None,
                "affordable": allowed is None or str(m["id"]) in allowed,
            }
            for m in sorted(role_models, key=score, reverse=True)
            if m["id"] != best["id"]
        ],
        warnings=[
            f"{role}: chose {best['id']} from this catalogue's own benchmarks rather than "
            f"through best-engine-ai-helper. {reason}"
        ],
    )


# ---------------------------------------------------------------------------
# The image slot, which this project keeps no catalogue of
# ---------------------------------------------------------------------------

#: GiB per gigabyte. The helper answers in gigabytes and this project sizes in
#: gibibytes, and the two differ by 7% -- small enough to ignore by accident
#: and large enough to turn a card that fits into one that does not, which is
#: the only kind of rounding error worth naming a constant for.
GIB_PER_GB = 1 / 1.073741824


def _image_entries(be: Any) -> list[dict[str, Any]]:
    """The helper's own text-to-image catalogue.

    Theirs, not ours, and that is the point of the slot: ``catalog/serving.yaml``
    records what a vLLM deployment needs -- weights per quantization, key-value
    cache geometry, tool-call parsers -- and none of those words mean anything
    to a denoising loop. Keeping a second copy of somebody else's image
    catalogue here would buy nothing and go stale.
    """
    return [e for e in be.load_catalog() if str(e.get("kind")) == "image"]


def _no_image(reason: str) -> Choice:
    """No image model, said out loud rather than sized as though free.

    The empty ``model_id`` is what :func:`resolve_plan` reads as "drop this
    slot". Degrading in quality -- no image generation on this deployment --
    is the intent; degrading in arithmetic, by planning a model whose
    footprint nobody could work out, is what this avoids.
    """
    return Choice(
        role="image",
        model_id="",
        asked=False,
        reason=reason,
        axis=AXES["image"],
        warnings=[f"image: the slot was requested and is being left out. {reason}"],
    )


def _choose_image(
    *,
    vram_gib: float | None,
    bandwidth_gbs: float | None,
    lean: bool,
    only: str | None = None,
) -> Choice:
    """Ask the helper which text-to-image model this machine should serve.

    Delegated whole. ``imagine_rank`` sizes a diffusion pipeline the way it has
    to be sized -- per component, with the option of letting ``diffusers`` swap
    them so the peak is the largest rather than the sum -- and returns seconds
    per image, which is the unit a person waits in and the one that decides
    whether the slot is worth its memory at all. None of that is a language
    model's arithmetic and none of it belongs here.

    What this project adds is the one rule the helper's own ``pick`` does not
    apply: :data:`LEAN_TOLERANCE`. ``pick`` takes the best image model that
    runs, which on an 80 GiB card is a 43 GiB pipeline -- and this deployment's
    first job is to serve a coding agent, so a slot that halves the coder's
    budget to buy a few points of image quality has the priority backwards.
    """
    try:
        import best_engine_ai_helper as be  # lazy: keeps `import ai_bunker` cheap
    except ImportError:
        return _no_image(
            "best-engine-ai-helper is not importable in this interpreter, and the image "
            "catalogue, the footprints and the timings all live there."
        )

    missing = [n for n in ("load_catalog", "imagine_rank", "imagine_pick") if not hasattr(be, n)]
    if missing:
        return _no_image(
            f"the installed best-engine-ai-helper offers no {' or '.join(missing)}; it "
            "predates the image picker."
        )

    # In gigabytes, because that is the unit the helper answers in. `vram_gib`
    # is already net of whatever the earlier slots spent -- `resolve_plan`
    # hands over what is left, not what the card holds.
    room_gb = None if vram_gib is None else max(float(vram_gib) - OVERHEAD_GIB, 0.0) / GIB_PER_GB
    try:
        entries = _image_entries(be)
        if only:
            # A caller who named a model is still sized, not trusted: the same
            # footprint and timing arithmetic runs over a candidate set of one,
            # so `--image sdxl` on a card that cannot hold it says so instead
            # of planning it as though it were free.
            entries = [e for e in entries if str(e.get("id")) == only]
            if not entries:
                known = ", ".join(sorted(str(e.get("id")) for e in _image_entries(be)))
                return _no_image(
                    f"best-engine-ai-helper's image catalogue has no model {only!r}. "
                    f"Known: {known}."
                )
        if room_gb is None:
            # No machine was named, so the question is about this one -- and
            # then its bandwidth is the right one too. Only here: when a
            # caller named an accelerator, borrowing this laptop's bandwidth
            # would time the answer on the wrong machine, which is worse than
            # reporting that it could not be timed.
            hardware = dict(be.available_memory())
            room_gb = float(hardware.get("vram_gb") or hardware.get("unified_gb") or 0.0)
            if bandwidth_gbs is None and hasattr(be, "compute_profile"):
                bandwidth_gbs = (dict(be.compute_profile()) or {}).get("bandwidth_gbs")
        plans = be.imagine_rank(entries, budget_gb=room_gb, bandwidth_gbs=bandwidth_gbs)
        best = be.imagine_pick(plans)
    except Exception as exc:  # a recommendation is advice; its failure is not fatal
        return _no_image(f"best-engine-ai-helper could not rank the image models ({exc}).")

    if not best:
        smallest = min(
            (p for p in plans if p.get("resident_gb")),
            key=lambda p: float(p["resident_gb"]),
            default=None,
        )
        short = (
            f" The smallest is {smallest['catalog_id']} at {smallest['resident_gb']:.0f} GB."
            if smallest
            else ""
        )
        return _no_image(
            f"No text-to-image model fits the {room_gb:.0f} GB left once the language models "
            f"are resident.{short}"
        )

    def points(plan: dict[str, Any]) -> float:
        return float(plan.get("score") or 0.0)

    if lean:
        close = [p for p in plans if p.get("fits") and points(best) - points(p) <= LEAN_TOLERANCE]
        if close:
            best = min(close, key=lambda p: float(p.get("resident_gb") or 0.0))

    resident_gib = float(best.get("resident_gb") or 0.0) * GIB_PER_GB
    seconds = best.get("seconds_per_image")
    return Choice(
        role="image",
        model_id=str(best.get("catalog_id") or best.get("model") or ""),
        asked=True,
        reason=(
            f"best-engine-ai-helper chose {best.get('catalog_id')} among "
            f"{len(plans)} text-to-image model(s) for the {room_gb:.0f} GB left after the "
            f"language models (image benchmark {points(best):g}, {resident_gib:.0f} GiB "
            f"resident, {best.get('steps')} denoising steps at {best.get('size')}"
            + (f", about {seconds:g} s an image)." if seconds else ").")
        ),
        budget_gb=round(room_gb, 1),
        axis=AXES["image"],
        score=best.get("score"),
        weights_gib=round(resident_gib, 1),
        hf=str(best.get("model") or ""),
        detail={
            "size": best.get("size"),
            "steps": best.get("steps"),
            "seconds_per_image": seconds,
            # True when `diffusers` is to swap the components through the
            # accelerator one at a time. It is what makes a pipeline fit a card
            # that cannot hold it whole, and it is slower, so it is reported
            # rather than quietly assumed.
            "offload": bool(best.get("offload")),
            "usable": bool(best.get("usable")),
        },
        rejected=[
            {
                "id": p.get("catalog_id"),
                "weights_gib": round(float(p.get("resident_gb") or 0.0) * GIB_PER_GB, 1),
                "score": p.get("score"),
                "affordable": bool(p.get("fits")),
                "seconds_per_image": p.get("seconds_per_image"),
            }
            for p in plans
            if p.get("catalog_id") != best.get("catalog_id")
        ],
        warnings=(
            []
            if best.get("usable")
            else [
                # `seconds` is None when no bandwidth was supplied and no
                # measurement exists, which is the ordinary case for
                # `choose('image')` called without a machine. Unusable then
                # means "could not be timed", not "too slow", and the warning
                # has to be able to say either without formatting a None.
                f"image: {best.get('catalog_id')} fits but "
                + (
                    f"takes about {seconds:g} s an image, which is batch work rather than "
                    "interactive. "
                    if seconds
                    else "could not be timed on this machine. "
                )
                + "The blockers the helper named: "
                + ", ".join(best.get("blockers") or ["none"])
            ]
        ),
    )


def choose(
    role: str = "code",
    *,
    vram_gib: float | None = None,
    bandwidth_gbs: float | None = None,
    task: str | None = None,
    lean: bool | None = None,
    catalog: dict[str, Any] | None = None,
) -> Choice:
    """Ask the helper which model this machine should serve for ``role``.

    Parameters
    ----------
    role : {'code', 'vision', 'embed', 'image'}
        Which slot in the deployment plan is being filled. The first three are
        decided over this project's serving catalogue; ``image`` is delegated
        whole to the helper, which keeps the only catalogue of them -- see
        :func:`_choose_image`.
    vram_gib : float, optional
        Memory the target machine has for weights. This is the figure that
        makes the answer machine-specific, and it is usually *not* this
        machine's -- sizing is normally asked about a catalogue accelerator.
        Omit it and the helper is asked about the local machine instead.
    bandwidth_gbs : float, optional
        Memory bandwidth of the target machine. Read only by the image slot,
        whose honest unit is seconds per image and whose sampling loop is
        bound by it. The language slots are ranked on benchmarks and memory
        fit, and sizing does their throughput arithmetic itself.
    task : str, optional
        What the model is for, in words the helper parses. Defaults to
        :data:`TASK`, or :data:`VISION_TASK` for the vision role.
    lean : bool, optional
        Apply the anti-greed rule: take the leanest candidate within
        :data:`LEAN_TOLERANCE` points of the best rather than the best.
        Defaults to True for every role except ``code``, which is the slot
        spare memory is supposed to go to.
    catalog : dict, optional
        Injectable serving catalogue, for tests.

    Returns
    -------
    Choice
        The model id, whether the helper answered, and why. An empty
        ``model_id`` means the slot could not be filled and should be dropped,
        which only the image slot can answer.
    """
    cat = catalog or load_catalog()
    osh.check(role in ROLE_KINDS, f"Unknown role {role!r}. Known: {', '.join(ROLE_KINDS)}")

    if role == "image":
        return _choose_image(
            vram_gib=vram_gib,
            bandwidth_gbs=bandwidth_gbs,
            # The same anti-greed default as the vision slot, and for the same
            # reason: this is a gateway for coding agents, and an image model
            # that halves the coder's budget has the priority backwards.
            lean=True if lean is None else lean,
        )

    # An embedder is not an `llm` or a `vlm`, which are the only kinds the
    # helper's ranking knows. There is one in this catalogue and ranking a set
    # of one is theatre, so the role is answered directly and says so.
    kind = ROLE_KINDS[role]
    entries = [e for e in as_helper_entries(cat) if e["kind"] == kind]
    if not entries:
        return _fallback(role, f"This catalogue carries no {role!r} model to choose between.", cat)
    if kind == "embed":
        only = min(entries, key=lambda e: e["weights_gib"])
        return Choice(
            role=role,
            model_id=str(only["id"]),
            asked=False,
            reason=(
                f"{only['id']} is the catalogue's embedder. The helper ranks `llm` and `vlm` "
                "kinds; an embedder is neither, and ranking a set of one would be theatre."
            ),
            weights_gib=only["weights_gib"],
            hf=str(only["vllm_id"]),
        )

    # The affordable set, decided here. This catalogue records what each model's
    # weights actually weigh at the quantization it is served at, and the
    # helper's fit check inflates that for a vLLM backend -- measured: every
    # model in this catalogue reads as `fits=False` on a 96 GiB machine, the
    # 24B included. So affordability is settled against the real numbers and
    # the helper is asked only for the thing it is authoritative about, which
    # is the order.
    affordable = entries
    if vram_gib is not None:
        room = float(vram_gib) - OVERHEAD_GIB
        affordable = [e for e in entries if e["weights_gib"] <= room]
        if not affordable:
            smallest = min(entries, key=lambda e: e["weights_gib"])
            return Choice(
                role=role,
                model_id=str(smallest["id"]),
                asked=False,
                reason=(
                    f"No {role} model in this catalogue fits {vram_gib:.0f} GiB once "
                    f"{OVERHEAD_GIB:.0f} GiB is left for context and the key-value cache. "
                    f"Naming the smallest ({smallest['id']}, {smallest['weights_gib']:.0f} GiB) so "
                    "the sizing can say by how much it misses."
                ),
                axis=AXES[role],
                score=smallest["benchmarks"].get(AXES[role]),
                weights_gib=smallest["weights_gib"],
                hf=str(smallest["vllm_id"]),
                # Named even though none of them fits, because that is the
                # whole content of this answer: the reader is being told the
                # card is too small, and the list of what it is too small for
                # is how they decide which bigger card to ask for.
                rejected=[
                    {
                        "id": e["id"],
                        "weights_gib": e["weights_gib"],
                        "score": e["benchmarks"].get(AXES[role]),
                        "affordable": False,
                    }
                    for e in sorted(entries, key=lambda e: e["weights_gib"])
                    if e["id"] != smallest["id"]
                ],
                warnings=[
                    f"{role}: nothing fits, so this is the smallest candidate rather than a "
                    "choice. The sizing below will report `does-not-fit`."
                ],
            )

    try:
        import best_engine_ai_helper as be  # lazy: keeps `import ai_bunker` cheap
    except ImportError:
        return _fallback(
            role,
            "best-engine-ai-helper is not importable in this interpreter, though it is a "
            "declared dependency. Install it to have the choice made properly.",
            cat,
            affordable,
        )

    # The budget handed over. Only used for the helper's own annotations now --
    # the filtering above has already happened -- but an accelerator id was
    # almost certainly what the caller meant, so it is that machine's memory
    # rather than this laptop's.
    #
    # Everything from here is behind one guard, and by capability rather than
    # by version. The suite's two packages are released separately, so the
    # helper that resolves at install time is not necessarily the one this was
    # written against -- and a version floor cannot express it, since a working
    # tree and the release it shares a number with are different code. Asking
    # whether the function is there is the only check that is true.
    missing = [name for name in ("rank", "available_memory") if not hasattr(be, name)]
    if missing:
        return _fallback(
            role,
            f"the installed best-engine-ai-helper offers no {' or '.join(missing)}; it predates "
            "the ranking this project asks for.",
            cat,
            affordable,
        )

    try:
        hardware: dict[str, Any] = (
            {"vram_gb": round(vram_gib * 1.073741824, 1)}
            if vram_gib is not None
            else dict(be.available_memory())
        )
        ordered = be.rank(
            hardware,
            affordable,
            kind,
            # The same column the choice is reported on, from the same table.
            # The helper ranks by it and `points` below re-reads it for the
            # anti-greed tie-break, so a divergence here would order the
            # candidates on one axis and justify the winner on another.
            application=AXES[role],
            backend="vllm",
            # A coding agent's tool call is constrained decoding, so a model
            # that cannot honour a schema is not a candidate at all. Enforced
            # for the code slot and not for vision, where this catalogue's
            # models do not claim it.
            require_structured=kind == "llm",
        )
    except Exception as exc:  # a recommendation is advice; its failure is not fatal
        return _fallback(
            role,
            f"best-engine-ai-helper could not rank the candidates ({exc}).",
            cat,
            affordable,
        )

    ranked = [str(r.get("id")) for r in (ordered or []) if r.get("id")]
    if not ranked:
        return _fallback(
            role,
            "best-engine-ai-helper ranked none of this catalogue's candidates, which for the "
            "code slot means none of them claims structured output.",
            cat,
            affordable,
        )

    by_id = {e["id"]: e for e in affordable}
    axis = AXES[role]

    def points(entry: dict[str, Any]) -> float:
        return float(entry["benchmarks"].get(axis) or 0.0)

    model_id = ranked[0]
    if lean if lean is not None else role != "code":
        # The leanest candidate the helper ranked that is within tolerance of
        # its first choice. `ranked` order is the helper's; the tolerance and
        # the tie-break on weight are this project's requirement.
        best = points(by_id[model_id])
        close = [
            by_id[i] for i in ranked if i in by_id and best - points(by_id[i]) <= LEAN_TOLERANCE
        ]
        if close:
            model_id = str(min(close, key=lambda e: e["weights_gib"])["id"])
    find_model(cat, model_id)
    chosen = by_id[model_id]
    return Choice(
        role=role,
        model_id=model_id,
        asked=True,
        reason=(
            f"best-engine-ai-helper ranked {model_id} first for {role} among the "
            f"{len(affordable)} model(s) that fit {vram_gib:.0f} GiB"
            if vram_gib is not None
            else f"best-engine-ai-helper ranked {model_id} first for {role} among "
            f"{len(affordable)} candidate(s)"
        )
        + (
            f" ({axis} benchmark {points(chosen):g}, {chosen['weights_gib']:.0f} GiB of "
            f"weights{', structured output' if chosen['structured_output'] else ''})."
        ),
        budget_gb=hardware.get("vram_gb") or hardware.get("unified_gb"),
        axis=axis,
        score=chosen["benchmarks"][axis],
        weights_gib=chosen["weights_gib"],
        hf=str(chosen["vllm_id"]),
        rejected=[
            {
                "id": e["id"],
                "weights_gib": e["weights_gib"],
                "score": e["benchmarks"][axis],
                "affordable": e in affordable,
            }
            for e in sorted(entries, key=lambda e: (e not in affordable, -points(e)))
            if e["id"] != model_id
        ],
    )


@dataclass
class ResolvedPlan:
    """A deployment plan with every slot settled, and why each one is what it is.

    A record rather than a tuple because the slots grew: it was three, the
    image slot made it four, and a caller unpacking positionally would have
    gone on working and silently read the image model as the embedder.
    """

    code: str
    vision: str | None = None
    embeddings: str | None = None
    image: str | None = None
    #: One per slot that was asked about -- so a report can show the reasoning
    #: rather than a bare name.
    choices: list[Choice] = field(default_factory=list)

    def warnings(self) -> list[str]:
        """Every slot's warnings, in the order the slots were settled."""
        return [w for choice in self.choices for w in choice.warnings]


def resolve_plan(
    *,
    primary: str | None = ASK,
    with_vision: str | None = ASK,
    with_embeddings: str | None = ASK,
    with_image: str | None = None,
    vram_gib: float | None = None,
    bandwidth_gbs: float | None = None,
    catalog: dict[str, Any] | None = None,
) -> ResolvedPlan:
    """Turn a plan that may say :data:`ASK` into one that names its models.

    ``None`` is left alone and keeps meaning "leave this model out", which it
    has always meant and which :data:`ASK` exists so as not to disturb. It is
    also the default for ``with_image``, and that asymmetry is deliberate: a
    coding agent needs a coder, usually wants eyes and an embedder, and does
    not generate pictures unless somebody asked for it. A slot that turned
    itself on would take its memory from the coder.

    The slots are resolved against a **running budget**, cheapest first, and
    that ordering is the whole subtlety. Asking each slot independently what
    fits the card over-commits it: on a 72 GiB card the best coder, the vision
    model and the embedder each fit on their own and do not fit together, which
    is how an earlier version of this function turned the cheapest card that
    holds the best model into ``does-not-fit``.

    So the embedder is settled first (it is about a gibibyte and there is one
    of it), then the vision model, then the image model, and the code model
    takes what is left. That is also the priority ``docs/SIZING.md`` argues for
    from the other direction: with memory to spare you spend it on **a better
    coder**, so the coder is the slot that should receive the remainder rather
    than compete for it.

    Parameters
    ----------
    primary, with_vision, with_embeddings, with_image : str or None
        A catalogue id, :data:`ASK` to put the question to the helper, or
        ``None`` to leave the slot out.
    vram_gib : float, optional
        The target machine's memory for weights.
    bandwidth_gbs : float, optional
        The target machine's memory bandwidth. Read only by the image slot,
        whose answer is in seconds per image.
    catalog : dict, optional
        Injectable serving catalogue, for tests.

    Returns
    -------
    ResolvedPlan
        The settled slots, and one :class:`Choice` per slot that was asked
        about.
    """
    cat = catalog or load_catalog()
    made: list[Choice] = []
    remaining = None if vram_gib is None else float(vram_gib)

    def spend(gib: float) -> None:
        nonlocal remaining
        if remaining is not None:
            remaining = max(remaining - gib, 0.0)

    def spend_catalogue(model_id: str) -> None:
        if remaining is None:
            return
        entry = find_model(cat, model_id)
        quant = str(entry.get("recommended_quant") or "")
        spend(float((entry.get("weights") or {}).get(quant) or 0.0))

    def settle(value: str | None, role: str) -> str | None:
        if value is None:
            return None
        if role == "image":
            # Both branches go through the helper, because even a model the
            # caller named has a footprint only the helper can work out --
            # this project keeps no image catalogue to look it up in.
            choice = _choose_image(
                vram_gib=remaining,
                bandwidth_gbs=bandwidth_gbs,
                lean=True,
                only=None if value == ASK else value,
            )
            made.append(choice)
            if not choice.model_id:
                return None
            spend(float(choice.weights_gib or 0.0))
            return choice.model_id
        if value != ASK:
            # A named model still consumes budget, or the slots that follow
            # would be sized as though it were free.
            spend_catalogue(value)
            return value
        choice = choose(role, vram_gib=remaining, catalog=cat)
        made.append(choice)
        spend_catalogue(choice.model_id)
        return choice.model_id

    # Cheapest first; the coder gets the remainder. See the docstring.
    embeddings = settle(with_embeddings, "embed")
    vision = settle(with_vision, "vision")
    image = settle(with_image, "image")
    code = settle(primary, "code")
    osh.check(bool(code), "A deployment plan needs a code model.")
    return ResolvedPlan(
        code=str(code), vision=vision, embeddings=embeddings, image=image, choices=made
    )
