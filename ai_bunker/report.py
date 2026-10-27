"""
Render a :class:`~ai_bunker.sizing.Sizing` as something a human can argue with.

A sizing that prints only its conclusion is a sizing nobody can check. Every
report here shows the chain -- what was assumed, what that implied, and which
constraint actually bound -- so a reader who disagrees knows exactly which
number to change.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_bunker.fallback import PREFETCH_DEPTH as PREFETCH_SHARDS
from ai_bunker.sizing import Assumptions, Sizing, load_catalog, serve_command

if TYPE_CHECKING:
    from ai_bunker.sizing import Recommendation

_VERDICT = {
    "comfortable": "COMFORTABLE  — room to grow",
    "workable": "WORKABLE     — sized right, little slack",
    "single-user": "SINGLE USER  — a developer box, not a server",
    "unusable-for-agents": "UNUSABLE     — too slow for an interactive agent",
    "does-not-fit": "DOES NOT FIT — the plan exceeds this card",
}


def _rule(width: int = 74) -> str:
    return "─" * width


def render(sizing: Sizing, *, show_command: bool = True) -> str:
    """Full human-readable sizing report."""
    a = sizing.assumptions
    out: list[str] = []
    w = out.append

    w(_rule())
    w(f"  {sizing.accelerator}")
    w(f"  {sizing.vram_gib:.0f} GiB  ·  {sizing.bandwidth_gbs:.0f} GB/s memory bandwidth")
    w(_rule())
    w("")

    w("  RESIDENT PLAN")
    for p in sizing.plan:
        w(f"    {p.role:<7} {p.model_id:<24} {p.quant:<6} {p.weights_gib:>6.1f} GiB")
    w(f"    {'':<7} {'weights total':<24} {'':<6} {sizing.resident_weights_gib:>6.1f} GiB")
    w(f"    {'':<7} {'overhead':<24} {'':<6} {a['vram_overhead_gib']:>6.1f} GiB")
    w(f"    {'':<7} {'KV cache pool':<24} {'':<6} {sizing.kv_pool_gib:>6.1f} GiB")
    w("")

    if sizing.verdict == "does-not-fit":
        w(f"  VERDICT  {_VERDICT[sizing.verdict]}")
        w("")
        for note in sizing.warnings:
            w(f"  ⚠  {note}")
        return "\n".join(out)

    w("  CONTEXT")
    w(f"    served to the model            {sizing.served_context:>9,} tokens")
    w(
        f"    declared to clients            {sizing.declared_context:>9,} tokens"
        f"   ({a['declared_fraction']:.0%} of served)"
    )
    w(f"    KV at full served context      {sizing.kv_full_context_gib:>9.1f} GiB  (one sequence)")
    w(
        f"    KV at assumed live context     {sizing.kv_per_session_gib:>9.1f} GiB  "
        f"({a['avg_live_context']:,} tokens)"
    )
    w("")

    w("  CONCURRENCY")
    w(f"    sessions the KV pool holds     {sizing.sessions_by_memory:>9}")
    w(f"    sessions above {a['comfort_tps']:.0f} tok/s          {sizing.sessions_by_speed:>9}")
    w(
        f"    → in flight at once            {sizing.concurrent_sessions:>9}"
        f"   (bound by {sizing.binding_constraint})"
    )
    w("")

    w("  SPEED")
    w(f"    one stream, alone              {sizing.single_stream_tps:>9.1f} tok/s")
    w(f"    one stream, at full batch      {sizing.per_stream_tps:>9.1f} tok/s")
    w(f"    the machine, aggregate         {sizing.aggregate_tps:>9.1f} tok/s")
    w("")

    w("  HEADCOUNT")
    w(f"    duty cycle (decoding / session)   {a['duty_cycle']:>6.0%}")
    w(f"    simultaneity (team in session)    {a['simultaneity']:>6.0%}")
    w(f"    → people one stream represents    {1 / (a['duty_cycle'] * a['simultaneity']):>6.1f}")
    w(f"    → PEOPLE THIS MACHINE CARRIES     {sizing.consultants:>6}")
    w("")

    w(f"  VERDICT  {_VERDICT.get(sizing.verdict, sizing.verdict)}")
    w("")

    for note in sizing.warnings:
        w(f"  ⚠  {note}")
    if sizing.warnings:
        w("")

    if show_command:
        w("  SERVE")
        for line in serve_command(sizing).splitlines():
            w(f"    {line}")
        w("")

    w(_rule())
    w("  Assumptions, all overridable — change one and the numbers move:")
    w(
        f"    --efficiency {a['efficiency']}  --comfort-tps {a['comfort_tps']:.0f}  "
        f"--live-context {a['avg_live_context']}"
    )
    w(f"    --duty-cycle {a['duty_cycle']}  --simultaneity {a['simultaneity']}")
    w(_rule())
    return "\n".join(out)


def render_comparison(sizings: list[Sizing], *, prices: dict[str, float] | None = None) -> str:
    """One line per machine, for choosing between them."""
    out: list[str] = []
    w = out.append
    head = (
        f"  {'MACHINE':<30} {'VRAM':>6} {'BW':>7} {'CTX':>9} "
        f"{'SESS':>5} {'TOK/S':>7} {'PEOPLE':>7}  VERDICT"
    )
    w(_rule(104))
    w(head)
    w(_rule(104))
    for s in sizings:
        name = s.accelerator[:30]
        ctx = f"{s.served_context // 1024}k" if s.served_context else "—"
        w(
            f"  {name:<30} {s.vram_gib:>5.0f}G {s.bandwidth_gbs:>6.0f}  {ctx:>9} "
            f"{s.concurrent_sessions:>5} {s.single_stream_tps:>7.1f} {s.consultants:>7}  "
            f"{_VERDICT.get(s.verdict, s.verdict).split('—')[0].strip()}"
        )
    w(_rule(104))

    if prices:
        w("")
        w("  COST PER PERSON CARRIED")
        for s in sizings:
            key = s.accelerator
            price = prices.get(key)
            if price is None:
                continue
            if s.consultants > 0:
                w(
                    f"    {key[:40]:<42} {price:>8,.0f} EUR  /  {s.consultants:>3} people"
                    f"  =  {price / s.consultants:>7,.0f} EUR per person"
                )
            else:
                w(
                    f"    {key[:40]:<42} {price:>8,.0f} EUR  /  0 people  =  "
                    f"no usable capacity at this comfort floor"
                )
    return "\n".join(out)


def render_catalog() -> str:
    """The serving catalogue, with provenance, as a table."""
    cat = load_catalog()
    out: list[str] = []
    w = out.append
    w(_rule(100))
    w(
        f"  {'MODEL':<24} {'ROLE':<7} {'LICENCE':<12} {'QUANT':<6} {'GiB':>6} "
        f"{'CTX':>7} {'BENCH':>7}"
    )
    w(_rule(100))
    for m in cat["models"]:
        q = m.get("recommended_quant", "")
        gib = (m.get("weights") or {}).get(q, 0)
        bench = m.get("benchmarks") or {}
        score = next(iter(bench.values()), None)
        w(
            f"  {m['id']:<24} {m['role']:<7} {m['license']:<12} {q:<6} {gib:>6} "
            f"{m['max_context'] // 1024:>6}k {score if score is not None else '—':>7}"
        )
    w(_rule(100))
    w("")
    w(f"  {'ACCELERATOR':<40} {'VRAM':>6} {'BANDWIDTH':>11} {'FP8':>5} {'CLASS':>14}")
    w(_rule(100))
    for a in cat["accelerators"]:
        w(
            f"  {a['name'][:40]:<40} {a['vram_gib']:>5}G {a['bandwidth_gbs']:>9} GB/s "
            f"{'yes' if a.get('fp8') else 'no':>5} {a.get('class', ''):>14}"
        )
    w(_rule(100))
    return "\n".join(out)


def default_assumptions_from_args(args) -> Assumptions:
    """Build :class:`Assumptions` from parsed CLI arguments."""
    base = Assumptions()
    return Assumptions(
        efficiency=getattr(args, "efficiency", None) or base.efficiency,
        comfort_tps=getattr(args, "comfort_tps", None) or base.comfort_tps,
        avg_live_context=getattr(args, "live_context", None) or base.avg_live_context,
        duty_cycle=getattr(args, "duty_cycle", None) or base.duty_cycle,
        simultaneity=getattr(args, "simultaneity", None) or base.simultaneity,
        vram_overhead_gib=base.vram_overhead_gib,
        declared_fraction=getattr(args, "declared_fraction", None) or base.declared_fraction,
    )


def render_recommendation(
    recs: list[Recommendation], team_size: int, *, plan: str, top: int = 6
) -> str:
    """Which machine to buy for a team of ``team_size``, and why the others lose."""
    from ai_bunker.sizing import Assumptions

    a = Assumptions()
    needed = recs[0].sessions_needed if recs else 0
    out: list[str] = []
    w = out.append

    w("")
    w(_rule(104))
    w(f"  TEAM OF {team_size}   ·   plan: {plan}")
    w(_rule(104))
    w("")
    w("  LOAD MODEL")
    w(
        f"    each person decodes {a.duty_cycle:.0%} of a session, "
        f"{a.simultaneity:.0%} of the team is in session at peak"
    )
    w(f"    → P(any one person decoding right now) = {a.duty_cycle * a.simultaneity:.1%}")
    w(
        f"    → 95th percentile of Binomial({team_size}, {a.duty_cycle * a.simultaneity:.3f})"
        f" = {needed} concurrent sequences"
    )
    w(f"    the machine must sustain {needed} sequence(s) above {a.comfort_tps:.0f} tok/s")
    w("")

    winners = [r for r in recs if r.fits]
    if winners:
        best = winners[0]
        s = best.sizing
        w("  ✔ BUY")
        w(f"      {s.accelerator}")
        w(
            f"      {s.vram_gib:.0f} GiB · {s.bandwidth_gbs:.0f} GB/s · "
            f"{best.batching} · ${best.total_usd:,.0f} "
            f"(card ${best.price_usd:,.0f} + node ${best.node_usd:,.0f})"
        )
        w(
            f"      carries {s.concurrent_sessions} sequences "
            f"(needs {needed}) at {s.per_stream_tps:.0f} tok/s each, "
            f"{s.single_stream_tps:.0f} tok/s alone"
        )
        w(f"      serves {s.served_context:,} tokens, declares {s.declared_context:,}")
        if best.usd_per_person:
            w(f"      ${best.usd_per_person:,.0f} per person")
        w("")
        if len(winners) > 1:
            w("  ALSO FITS, COSTS MORE")
            for r in winners[1:3]:
                w(
                    f"      {r.sizing.accelerator[:46]:<48} ${r.total_usd:>7,.0f}"
                    f"   {r.sizing.concurrent_sessions:>2} seq"
                )
            w("")
    else:
        w("  ✘ NOTHING IN THE CATALOGUE FITS")
        w("      Relax a constraint: drop the co-resident VLM, lower --comfort-tps,")
        w("      shorten --live-context, or plan for more than one machine.")
        w("")

    w("  FULL FIELD")
    w(f"  {'MACHINE':<40} {'$ TOTAL':>9} {'SEQ':>4} {'TOK/S':>7} {'CTX':>7}  WHY NOT")
    w(_rule(104))
    for r in recs[:top]:
        s = r.sizing
        ctx = f"{s.served_context // 1024}k" if s.served_context else "—"
        if r.fits:
            why = "✔ fits"
        elif r.disqualified:
            why = r.disqualified[:44]
        elif s.verdict == "does-not-fit":
            why = "plan exceeds VRAM"
        elif s.concurrent_sessions == 0:
            why = f"bandwidth wall: {s.single_stream_tps:.0f} tok/s max"
        else:
            why = f"only {s.concurrent_sessions} of {needed} sequences"
        w(
            f"  {s.accelerator[:40]:<40} {r.total_usd:>9,.0f} "
            f"{s.concurrent_sessions:>4} {s.single_stream_tps:>7.1f} {ctx:>7}  {why}"
        )
    w(_rule(104))
    return "\n".join(out)


_BUDGET_VERDICT = {
    "ok": "OK       — room to work",
    "tight": "TIGHT    — works, with little slack",
    "unusable": "UNUSABLE — this session cannot work",
}


def render_budget(budget) -> str:
    """Render a :class:`~ai_bunker.budget.Budget` as an itemised bill.

    Shows the chain, not the conclusion: every component, who owns it, and what
    is left. A floor nobody can decompose is a floor nobody can reduce.
    """
    out: list[str] = []
    w = out.append
    floor = budget.floor_tokens or 1

    w(_rule(78))
    trust = "exact" if budget.exact else "ESTIMATE"
    w(f"  SESSION FLOOR   ·   counted by {budget.backend} ({trust})")
    if budget.model:
        w(f"  model: {budget.model}")
    w(_rule(78))
    w("")
    w(f"  {'COMPONENT':<30} {'TOKENS':>8} {'SHARE':>7}  OWNER")
    w(f"  {'-' * 30} {'-' * 8} {'-' * 7}  {'-' * 10}")
    for item in budget.items:
        w(f"  {item.name:<30} {item.tokens:>8,} {item.tokens / floor:>6.0%}  {item.owner}")
    w(f"  {'-' * 30} {'-' * 8} {'-' * 7}")
    w(f"  {'FLOOR — paid on every request':<30} {budget.floor_tokens:>8,}")
    w("")

    w("  BUDGET")
    w(f"    served by the engine            {budget.served_context:>9,}")
    w(
        f"    declared to the client          {budget.declared_context:>9,}"
        f"   ({budget.declared_context / max(budget.served_context, 1):.0%})"
    )
    w(f"    less compaction margin         -{budget.compaction_reserve:>9,}")
    w(f"    = compaction starts at          {budget.compaction_starts_at:>9,}")
    w(f"    less floor                     -{budget.floor_tokens:>9,}")
    w(f"    = CONVERSATION SPACE            {budget.working_tokens:>9,}")
    w("")
    w(f"  VERDICT  {_BUDGET_VERDICT.get(budget.verdict, budget.verdict)}")
    w("")

    for note in budget.warnings:
        # Wrap by hand: a terminal report that scrolls sideways is unread.
        words, line = note.split(), "  ⚠  "
        for word in words:
            if len(line) + len(word) + 1 > 76:
                w(line)
                line = "     " + word
            else:
                line += ("" if line.endswith("  ") else " ") + word
        w(line)
        w("")

    biggest = budget.biggest
    if biggest and budget.verdict != "ok":
        w(
            f"  Attack {biggest.name} first: {biggest.tokens:,} tokens "
            f"({biggest.tokens / floor:.0%}), owned by the {biggest.owner}."
        )
        w("")

    w(_rule(78))
    return "\n".join(out)


def screen_cost_ms(rules) -> float:
    """Milliseconds to screen 100 KB of text through this rule set.

    Published because nothing caps the number of rules. `MAX_SCREEN_CHARS`
    bounds the input and the cost is linear in the rule count, so a deployment
    that imports a large charter pack -- which `ai-bunker skill --import` makes
    easy -- pays proportionally with no warning at all. A figure an operator
    can watch is cheaper than a limit somebody has to argue about.

    Measured on text with no match in it, which is the normal case and the
    honest one: a result that triggers a rule costs more, and quoting the
    cheaper number would understate what a busy session pays.
    """
    import time

    from ai_bunker.rules import screen_output

    sample = ("the quick brown fox jumps over the lazy dog. " * 2400)[:100_000]
    best = float("inf")
    for _ in range(3):
        started = time.perf_counter()
        screen_output(sample, rules)
        best = min(best, (time.perf_counter() - started) * 1000)
    return best


def render_rule_report(report, rules, *, show_cost: bool = False) -> str:
    """Render the result of checking rules against their own examples."""
    out: list[str] = []
    w = out.append
    w(_rule(78))
    w("  RULE EVIDENCE")
    w(_rule(78))
    w("")
    w(f"  rules loaded                      {report.total_rules:>6}")
    w(f"  assertions passed                 {report.passed:>6}")
    w(f"  assertions failed                 {len(report.failed):>6}")
    w(f"  rules carrying evidence           {report.coverage:>5.0%}")
    if show_cost:
        # Behind a flag, and out of the default table on purpose. Seven
        # documents quote this block as real output, and a millisecond figure
        # is machine-dependent: putting it in the default view would give all
        # seven a number that is wrong on every other machine and that no
        # drift guard can check. `--json` always carries it, because a script
        # watching the cost of a growing rule set is the use that matters.
        w(f"  cost to screen 100 KB             {screen_cost_ms(rules):>5.0f} ms")
    w("")

    by_scope: dict[str, list] = {}
    for r in rules:
        by_scope.setdefault(r.scope, []).append(r)
    for scope, group in sorted(by_scope.items()):
        w(f"  {scope.upper()}")
        for r in sorted(group, key=lambda x: x.id):
            marks = []
            if r.entropy:
                marks.append(f"entropy>={r.entropy}")
            if r.allow:
                marks.append(f"{len(r.allow)} allow")
            if not r.tested:
                marks.append("NO EVIDENCE")
            extra = f"  [{', '.join(marks)}]" if marks else ""
            action = "redact" if r.redact else ("refuse" if r.enforces else "note")
            w(
                f"    {r.id:<34} {r.severity:<10} {action:<7} "
                f"{len(r.should_match) + len(r.should_not_match):>3} ex{extra}"
            )
        w("")

    noted = [r for r in rules if getattr(r, "notes", ())]
    if noted:
        w("  DESIGN NOTES — a rule that reads as if it stops something and does not")
        w("  is the failure mode worth catching here rather than in production:")
        for r in sorted(noted, key=lambda x: x.id):
            for note in r.notes:
                w(f"    {r.id}: {note}")
        w("")

    if report.untested:
        w("  ⚠  Rules with no examples. A regular expression that silently stops")
        w("     matching is a guardrail that silently disappears:")
        for rid in report.untested:
            w(f"       {rid}")
        w("")

    for rule_id, expectation, example in report.failed:
        w(f"  ✘  {rule_id} — {expectation}")
        w(f"       {example[:68]}")
    if report.failed:
        w("")

    w(_rule(78))
    return "\n".join(out)


_FALLBACK_VERDICT = {
    "interactive": "INTERACTIVE  — fast enough for an agent, which for streaming is a surprise",
    "batch": "BATCH        — an answer within the hour, for work nobody is watching",
    "overnight": "OVERNIGHT    — start it and come back tomorrow",
    "impractical": "IMPRACTICAL  — the arithmetic says do something else",
}

_ENGINE = {
    "resident": "RESIDENT  — the model fits; serve it the ordinary way",
    "airllm": "AIRLLM    — stream the layers off storage",
    "none": "NONE      — this machine cannot usefully run this model",
}


def render_fallback(choice, *, show_command: bool = True) -> str:
    """The streaming decision, with the chain that produced it.

    Same contract as :func:`render`: the conclusion is last and the numbers
    that forced it come first, because a verdict this negative is only useful
    if the reader can see which figure to attack.
    """
    from ai_bunker.fallback import engine_command, upstream_snippet

    s = choice.streaming
    out: list[str] = []
    w = out.append

    w(_rule())
    w(f"  {choice.machine}  ·  layer-streaming fallback")
    w(f"  {choice.model_id}  ·  mode {choice.mode}  ·  floor {choice.floor}")
    w(_rule())
    w("")

    if s is None:
        w(f"  ENGINE   {_ENGINE.get(choice.engine, choice.engine)}")
        w("")
        w(f"  {choice.reason}")
        return "\n".join(out)

    a = s.assumptions
    # One column width for every label in the report, so a reader comparing
    # two of these side by side is comparing numbers rather than indentation.
    label = 34

    w("  WHAT IS READ, PER GENERATED TOKEN")
    w(f"    {f'checkpoint ({s.quant})':<{label}}{s.checkpoint_gib:>8.1f} GiB")
    w(
        f"    {'of it, out of the page cache':<{label}}{s.cached_gib:>8.1f} GiB"
        f"   at {s.cache_gbs:.1f} GB/s"
    )
    w(
        f"    {f'of it, off {s.storage}':<{label}}{s.streamed_gib:>8.1f} GiB"
        f"   at {s.disk_gbs:.1f} GB/s, {s.disk_source}"
    )
    w("")

    w("  WHAT STAYS ON THE DEVICE")
    w(
        f"    {f'{PREFETCH_SHARDS} layer shards':<{label}}"
        f"{s.shard_gib * PREFETCH_SHARDS:>8.2f} GiB"
        f"   {s.layers} layers{', assumed' if s.layers_assumed else ''}"
    )
    w(f"    {f'KV cache at {s.context:,} tokens':<{label}}{s.kv_gib:>8.2f} GiB   {a['kv_dtype']}")
    w(f"    {'activations and context':<{label}}{a['device_overhead_gib']:>8.2f} GiB")
    w(f"    {'→ needed on the device':<{label}}{s.device_need_gib:>8.2f} GiB")
    w("")

    w("  SPEED")
    w(f"    {'seconds per token':<{label}}{s.seconds_per_token:>8.2f} s")
    w(f"    {'tokens per second':<{label}}{s.tps:>8.3f} tok/s")
    w(f"    {f'a {s.answer_tokens}-token answer':<{label}}{s.answer_seconds / 60:>8.1f} min")
    w(
        f"    {'the prompt, whatever its length':<{label}}{s.prefill_seconds:>8.2f} s"
        "   one pass over the layers, not one per token"
    )
    if s.resident_tps is not None:
        w(f"    {'the same model, resident':<{label}}{s.resident_tps:>8.1f} tok/s")
        w(f"    {'→ streaming is slower by':<{label}}{s.slowdown:>8.0f}x")
    w("")

    w(f"  VERDICT  {_FALLBACK_VERDICT.get(s.verdict, s.verdict)}")
    w(f"  ENGINE   {_ENGINE.get(choice.engine, choice.engine)}")
    w("")
    w(f"  {choice.reason}")
    w("")

    for note in choice.warnings:
        w(f"  ⚠  {note}")
    if choice.warnings:
        w("")

    if show_command and choice.activated:
        w("  RUN IT")
        for line in engine_command(choice).splitlines():
            w(f"    {line}")
        w("")
        w("  THEN TELL THE GATEWAY, as an upstream like any other")
        for line in upstream_snippet(choice).splitlines():
            w(f"    {line}" if line else "")
        w("")

    w(_rule())
    w("  Assumptions, all overridable — change one and the numbers move:")
    w(
        f"    --disk <GB/s>  --disk-efficiency {a['disk_efficiency']}  "
        f"--answer-tokens {a['answer_tokens']}"
    )
    w(f"    --compression {a['compression'] or 'none'}  --context <tokens>  --floor {choice.floor}")
    w("  The one figure here worth measuring rather than assuming:")
    w("    python scripts/bench_disk.py")
    w(_rule())
    return "\n".join(out)
