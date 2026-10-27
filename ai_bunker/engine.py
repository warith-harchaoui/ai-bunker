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
all of it so ``ai-bunker sizing`` can print the chain instead of a name.

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
ROLE_KINDS = {"code": "llm", "vision": "vlm", "embed": "embed"}

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
    score: float | None = None
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


def _fallback(role: str, reason: str, catalog: dict[str, Any]) -> Choice:
    """The best-benchmarked catalogue model for a role, said out loud.

    Reached when the helper cannot answer -- it is not installed, or nothing in
    this catalogue fits the budget it was given. The point is that it is
    *reported*: a silent fallback to a literal is the defect this module was
    written to remove, and replacing one silent literal with another would be
    no improvement.
    """
    candidates = [m for m in catalog["models"] if str(m.get("role")) == role]
    osh.check(bool(candidates), f"The serving catalogue carries no {role!r} model.")

    def score(m: dict[str, Any]) -> float:
        bench = m.get("benchmarks") or {}
        return float(bench.get("swe_bench_verified") or bench.get("general") or 0.0)

    best = max(candidates, key=score)
    return Choice(
        role=role,
        model_id=str(best["id"]),
        asked=False,
        reason=reason,
        warnings=[
            f"{role}: chose {best['id']} from this catalogue's own benchmarks rather than "
            f"through best-engine-ai-helper. {reason}"
        ],
    )


def choose(
    role: str = "code",
    *,
    vram_gib: float | None = None,
    task: str | None = None,
    lean: bool | None = None,
    catalog: dict[str, Any] | None = None,
) -> Choice:
    """Ask the helper which model this machine should serve for ``role``.

    Parameters
    ----------
    role : {'code', 'vision', 'embed'}
        Which slot in the deployment plan is being filled.
    vram_gib : float, optional
        Memory the target machine has for weights. This is the figure that
        makes the answer machine-specific, and it is usually *not* this
        machine's -- sizing is normally asked about a catalogue accelerator.
        Omit it and the helper is asked about the local machine instead.
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
        The model id, whether the helper answered, and why.
    """
    cat = catalog or load_catalog()
    osh.check(role in ROLE_KINDS, f"Unknown role {role!r}. Known: {', '.join(ROLE_KINDS)}")

    try:
        import best_engine_ai_helper as be  # lazy: keeps `import ai_bunker` cheap
    except ImportError:
        return _fallback(
            role,
            "best-engine-ai-helper is not importable in this interpreter, though it is a "
            "declared dependency. Install it to have the choice made properly.",
            cat,
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
                warnings=[
                    f"{role}: nothing fits, so this is the smallest candidate rather than a "
                    "choice. The sizing below will report `does-not-fit`."
                ],
            )

    # The budget handed over. Only used for the helper's own annotations now --
    # the filtering above has already happened -- but an accelerator id was
    # almost certainly what the caller meant, so it is that machine's memory
    # rather than this laptop's.
    if vram_gib is not None:
        hardware: dict[str, Any] = {"vram_gb": round(vram_gib * 1.073741824, 1)}
    else:
        hardware = dict(be.available_memory())

    try:
        ordered = be.rank(
            hardware,
            affordable,
            kind,
            application="code" if kind == "llm" else "vision",
            backend="vllm",
            # A coding agent's tool call is constrained decoding, so a model
            # that cannot honour a schema is not a candidate at all. Enforced
            # for the code slot and not for vision, where this catalogue's
            # models do not claim it.
            require_structured=kind == "llm",
        )
    except Exception as exc:  # a recommendation is advice; its failure is not fatal
        return _fallback(role, f"best-engine-ai-helper could not rank the candidates ({exc}).", cat)

    ranked = [str(r.get("id")) for r in (ordered or []) if r.get("id")]
    if not ranked:
        return _fallback(
            role,
            "best-engine-ai-helper ranked none of this catalogue's candidates, which for the "
            "code slot means none of them claims structured output.",
            cat,
        )

    by_id = {e["id"]: e for e in affordable}
    axis = "code" if kind == "llm" else "vision"

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
            f" (benchmark {chosen['benchmarks']['code']}, {chosen['weights_gib']:.0f} GiB of "
            f"weights{', structured output' if chosen['structured_output'] else ''})."
        ),
        budget_gb=hardware.get("vram_gb") or hardware.get("unified_gb"),
        score=chosen["benchmarks"]["code"],
        rejected=[
            {
                "id": e["id"],
                "weights_gib": e["weights_gib"],
                "code": e["benchmarks"]["code"],
                "affordable": True,
            }
            for e in affordable
            if e["id"] != model_id
        ]
        + [
            {
                "id": e["id"],
                "weights_gib": e["weights_gib"],
                "code": e["benchmarks"]["code"],
                "affordable": False,
            }
            for e in entries
            if e not in affordable
        ],
    )


def resolve_plan(
    *,
    primary: str | None = ASK,
    with_vision: str | None = ASK,
    with_embeddings: str | None = ASK,
    vram_gib: float | None = None,
    catalog: dict[str, Any] | None = None,
) -> tuple[str, str | None, str | None, list[Choice]]:
    """Turn a plan that may say :data:`ASK` into one that names three models.

    ``None`` is left alone and keeps meaning "leave this model out", which it
    has always meant and which :data:`ASK` exists so as not to disturb.

    The three slots are resolved against a **running budget**, cheapest first,
    and that ordering is the whole subtlety. Asking each slot independently
    what fits the card over-commits it: on a 72 GiB card the best coder, the
    vision model and the embedder each fit on their own and do not fit
    together, which is how an earlier version of this function turned the
    cheapest card that holds the best model into ``does-not-fit``.

    So the embedder is settled first (it is about a gibibyte and there is one
    of it), then the vision model, and the code model takes what is left. That
    is also the priority ``docs/SIZING.md`` argues for from the other
    direction: with memory to spare you spend it on **a better coder**, so the
    coder is the slot that should receive the remainder rather than compete for
    it.

    Returns
    -------
    (str, str or None, str or None, list of Choice)
        The three model ids, and one :class:`Choice` per slot that was asked
        about -- so a report can show the reasoning rather than a bare name.
    """
    cat = catalog or load_catalog()
    made: list[Choice] = []
    remaining = None if vram_gib is None else float(vram_gib)

    def settle(value: str | None, role: str) -> str | None:
        nonlocal remaining
        if value is None:
            return None
        if value != ASK:
            # A named model still consumes budget, or the slots that follow
            # would be sized as though it were free.
            _spend(value, role, cat)
            return value
        choice = choose(role, vram_gib=remaining, catalog=cat)
        made.append(choice)
        _spend(choice.model_id, role, cat)
        return choice.model_id

    def _spend(model_id: str, _role: str, catalogue: dict[str, Any]) -> None:
        nonlocal remaining
        if remaining is None:
            return
        entry = find_model(catalogue, model_id)
        quant = str(entry.get("recommended_quant") or "")
        remaining = max(remaining - float((entry.get("weights") or {}).get(quant) or 0.0), 0.0)

    # Cheapest first; the coder gets the remainder. See the docstring.
    embeddings = settle(with_embeddings, "embed")
    vision = settle(with_vision, "vision")
    code = settle(primary, "code")
    osh.check(bool(code), "A deployment plan needs a code model.")
    return str(code), vision, embeddings, made
