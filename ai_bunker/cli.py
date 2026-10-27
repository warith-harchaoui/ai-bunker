"""
``ai-bunker`` command line.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import os_helper as osh

from ai_bunker import __version__, i18n
from ai_bunker.adopt import ALL_CLIENTS, CLIENTS, FRAMEWORKS, adopt, plan_adopt
from ai_bunker.budget import (
    DECLARED_FRACTION,
    MIN_WORKING_TOKENS,
    Counter,
    load_request,
    measure_request,
)
from ai_bunker.charter import build_index, load_charter, read_page, system_blocks
from ai_bunker.config import load_settings
from ai_bunker.fallback import (
    MODE_ALIASES,
    VERDICTS,
    StreamingAssumptions,
    choose_engine,
    machine_from_catalog,
    machine_from_host,
    storage_classes,
)
from ai_bunker.i18n import DEFAULT_LOCALE
from ai_bunker.report import (
    default_assumptions_from_args,
    render,
    render_budget,
    render_catalog,
    render_comparison,
    render_fallback,
    render_recommendation,
    render_rule_report,
    screen_cost_ms,
)
from ai_bunker.rules import (
    load_rules,
    refusal_message,
    screen_command,
    screen_output,
    test_rules,
    wrap_provenance,
)
from ai_bunker.sizing import (
    detect_machine,
    load_catalog,
    recommend_for_team,
    size_machine,
)
from ai_bunker.skill import (
    CLIENT_PATHS,
    as_charter_pack,
    build_skill,
    import_skills,
    read_catalog,
    read_skill,
    validate,
    warnings,
    write_charter_pack,
    write_skill,
)
from ai_bunker.spec import export as spec_export
from ai_bunker.spec import load as spec_load
from ai_bunker.spec import run as spec_run

# Indicative EUR for a complete, rack-ready node — not quotes. Orders of
# magnitude exist here so "cost per person carried" can be computed at all;
# override with --price.
NODE_PRICE_EUR = {
    "NVIDIA RTX PRO 6000 Blackwell Server Edition": 14000,
    "NVIDIA H100 80GB (SXM)": 32000,
    "NVIDIA A100 80GB": 18000,
    "NVIDIA L40S": 11000,
    "NVIDIA RTX 6000 Ada": 10000,
    "NVIDIA RTX A6000 / A40": 9000,
    "NVIDIA GeForce RTX 4090": 4500,
    "NVIDIA DGX Spark (GB10)": 5000,
}


def _add_assumption_flags(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("assumptions (all overridable)")
    g.add_argument("--efficiency", type=float, help="Fraction of peak bandwidth reached (0.70).")
    g.add_argument("--comfort-tps", type=float, help="Per-stream tok/s floor (20).")
    g.add_argument("--live-context", type=int, help="Average live context per session (65536).")
    g.add_argument("--duty-cycle", type=float, help="Decoding share of a session (0.25).")
    g.add_argument("--simultaneity", type=float, help="Team share in session at once (0.50).")
    g.add_argument("--declared-fraction", type=float, help="Declared / served context (0.80).")


def _add_plan_flags(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("deployment plan")
    g.add_argument("--model", default="devstral-small-2-24b", help="Primary code model id.")
    g.add_argument("--vision", default="qwen3-vl-32b", help="Co-resident VLM id, or 'none'.")
    g.add_argument("--embeddings", default="bge-m3", help="Co-resident embedder id, or 'none'.")
    g.add_argument("--context", type=int, help="Context to serve (default: the model's max).")
    g.add_argument("--kv-dtype", default="fp8", choices=["fp8", "bf16"])


def _none(v: str | None) -> str | None:
    return None if (v or "").strip().lower() in ("", "none", "no", "off") else v


def cmd_sizing(args) -> int:
    a = default_assumptions_from_args(args)
    kw = dict(
        primary=args.model,
        with_vision=_none(args.vision),
        with_embeddings=_none(args.embeddings),
        served_context=args.context,
        kv_dtype=args.kv_dtype,
        assumptions=a,
    )

    if args.accelerator:
        s = size_machine(accelerator=args.accelerator, **kw)
    elif args.vram:
        s = size_machine(vram_gib=args.vram, bandwidth_gbs=args.bandwidth or 1000.0, **kw)
    else:
        machine = detect_machine()
        if machine["role"] != "server":
            osh.warning(
                f"This machine is a {machine['role']}: "
                f"{machine.get('apple_chip') or machine['cpu']}, "
                f"{machine['ram_gb']} GB RAM, GPU vendor {machine['gpu_vendor']}. "
                "Sizing the recommended server instead — pass --accelerator or "
                "--vram/--bandwidth to size something else."
            )
        s = size_machine(accelerator="rtx-pro-6000-blackwell", **kw)

    print(json.dumps(s.to_dict(), indent=2) if args.json else render(s))
    return 0


def cmd_compare(args) -> int:
    a = default_assumptions_from_args(args)
    cat = load_catalog()
    ids = args.accelerators or [x["id"] for x in cat["accelerators"]]
    sizings = [
        size_machine(
            accelerator=i,
            primary=args.model,
            with_vision=_none(args.vision),
            with_embeddings=_none(args.embeddings),
            served_context=args.context,
            kv_dtype=args.kv_dtype,
            assumptions=a,
            catalog=cat,
        )
        for i in ids
    ]
    if args.json:
        print(json.dumps([s.to_dict() for s in sizings], indent=2))
        return 0
    plan = ", ".join(x for x in [args.model, _none(args.vision), _none(args.embeddings)] if x)
    print(f"\n  PLAN: {plan}\n")
    print(render_comparison(sizings, prices=None if args.no_prices else NODE_PRICE_EUR))
    print()
    return 0


def cmd_recommend(args) -> int:
    a = default_assumptions_from_args(args)
    recs = recommend_for_team(
        args.team,
        primary=args.model,
        with_vision=_none(args.vision),
        with_embeddings=_none(args.embeddings),
        served_context=args.context,
        kv_dtype=args.kv_dtype,
        assumptions=a,
        shared_server=not args.personal,
    )
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "accelerator": r.accelerator_id,
                        "fits": r.fits,
                        "total_usd": r.total_usd,
                        "usd_per_person": r.usd_per_person,
                        "sessions_needed": r.sessions_needed,
                        "disqualified": r.disqualified,
                        "sizing": r.sizing.to_dict(),
                    }
                    for r in recs
                ],
                indent=2,
            )
        )
        return 0
    plan = ", ".join(x for x in [args.model, _none(args.vision), _none(args.embeddings)] if x)
    print(render_recommendation(recs, args.team, plan=plan, top=args.top))
    print()
    return 0


def cmd_fallback(args) -> int:
    """Whether to stream this model off storage, on this machine, and what it costs."""
    if args.accelerator:
        machine = machine_from_catalog(args.accelerator, ram_gib=args.ram)
    else:
        machine = machine_from_host()
        if args.ram:
            machine.ram_gib = args.ram
    if args.bandwidth:
        machine.memory_gbs = args.bandwidth
    if args.storage:
        machine.storage = args.storage
    if args.disk:
        machine.disk_gbs = args.disk
    if args.cached:
        machine.cache_gbs = args.cached

    assumptions = StreamingAssumptions(
        disk_efficiency=args.disk_efficiency,
        answer_tokens=args.answer_tokens,
        compression=_none(args.compression),
        kv_dtype=args.kv_dtype,
    )
    choice = choose_engine(
        model=args.model,
        machine=machine,
        mode=args.mode or None,
        floor=args.floor,
        context=args.context,
        quant=_none(args.quant),
        shards_dir=args.shards or None,
        assumptions=assumptions,
    )
    if args.json:
        print(json.dumps(choice.to_dict(), indent=2))
    else:
        print(render_fallback(choice))
    # Non-zero when the decision is "do not run this here", so the command
    # works as a gate in a script rather than only as something to read.
    return 0 if (choice.engine != "none") else 1


def cmd_airllm(args) -> int:
    """Run the layer-streaming engine behind an OpenAI-compatible socket."""
    from ai_bunker.airllm import serve

    serve(
        model=args.model,
        host=args.host,
        port=args.port,
        context=args.context,
        compression=_none(args.compression),
        shards_dir=args.shards or None,
        eager=args.eager,
        allow_download=args.allow_download,
    )
    return 0


def cmd_budget(args) -> int:
    request = load_request(args.request)
    charter = Path(args.charter).read_text(encoding="utf-8") if args.charter else None
    index = Path(args.index).read_text(encoding="utf-8") if args.index else None

    counter = Counter(
        base_url=args.base_url,
        model=args.model_name,
        allow_ratio=not args.exact,
    )
    budget = measure_request(
        request,
        counter=counter,
        served_context=args.served_context,
        charter=charter,
        knowledge_index=index,
        compaction_reserve=args.reserve,
        max_output=args.max_output,
        declared_context=args.declared_context,
        min_working=args.min_working,
    )
    print(json.dumps(budget.to_dict(), indent=2) if args.json else render_budget(budget))

    # A gate that reports a failure and exits 0 is not a gate. `--gate` makes
    # the verdict the exit code, so CI can refuse a deployment on it.
    if args.gate and budget.verdict == "unusable":
        return 1
    return 0


def cmd_rules(args) -> int:
    rules = load_rules(args.directory)

    if args.check:
        report = test_rules(rules)
        if args.json:
            print(
                json.dumps(
                    {
                        "rules": report.total_rules,
                        "passed": report.passed,
                        "failed": [
                            {"rule": r, "expectation": e, "example": x} for r, e, x in report.failed
                        ],
                        "untested": report.untested,
                        "coverage": report.coverage,
                        # Always in the machine-readable output: nothing caps
                        # the rule count, the cost is linear in it, and a
                        # script is what would notice a pack doubling it.
                        "screen_cost_ms_per_100kb": round(screen_cost_ms(rules), 1),
                    },
                    indent=2,
                )
            )
        else:
            print(render_rule_report(report, rules, show_cost=args.cost))
        # Evidence that does not gate anything is documentation, not evidence.
        return 0 if report.ok else 1

    if args.command:
        refusal, notes = screen_command(args.command, rules)
        if refusal:
            print(refusal_message(refusal))
        for note in notes:
            if refusal is None or note.rule.id != refusal.id:
                print(f"[rules] {note.rule.id} ({note.rule.severity}): {note.rule.description}")
        if not notes:
            print("[rules] no rule matched; the command would run.")
        return 1 if refusal else 0

    # `-` is stdin, the way every other tool spells it. Without this the help
    # said "default: stdin" and the conventional way of asking for it crashed
    # with a FileNotFoundError on a file literally named `-`, which reads as a
    # broken tool rather than as an unsupported spelling.
    if args.screen and args.screen != "-":
        text = Path(args.screen).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    result = screen_output(text, rules)
    if args.provenance:
        text_out = wrap_provenance(result.text, source=args.provenance)
    else:
        text_out = result.text
    print(text_out + result.note)
    return 0


def cmd_charter(args) -> int:
    charter = load_charter(args.directory, locale=args.lang)
    if args.page:
        print(read_page(charter, args.page))
        return 0
    if args.index:
        print(build_index(charter))
        return 0
    if args.json:
        print(
            json.dumps(
                {
                    "root": str(charter.root),
                    "locale": charter.locale,
                    "fingerprint": charter.fingerprint,
                    "operating_rules_chars": len(charter.operating_rules),
                    "packs": {k: [p.name for p in v] for k, v in charter.packs.items()},
                    "untranslated": [p.ref for p in charter.pages if not p.translated],
                    "warnings": charter.warnings,
                },
                indent=2,
            )
        )
        return 0

    counter = Counter(allow_ratio=True)
    blocks = system_blocks(charter)
    cost = sum(counter.count(b) for b in blocks)
    print(f"charter      {charter.root}")
    # Before the fingerprint, because the fingerprint now depends on it: two
    # runs of this command showing two digests should say why on the line above
    # rather than look like a charter that changed on disk.
    print(f"language     {charter.locale}")
    print(f"fingerprint  {charter.fingerprint}")
    print(f"packs        {len(charter.packs)}  ({', '.join(charter.packs)})")
    print(f"pages        {len(charter.pages)}")
    print(f"floor cost   {cost:,} tokens  (operating rules + index, every request)")
    unopened = sum(p.chars for p in charter.pages)
    print(f"not loaded   {unopened:,} characters across the pages, read on demand")

    # The thesis, measured on the charter in front of the reader rather than
    # on the one it was discovered against.
    #
    # `charter.py` quotes a real measurement -- 37 pages, 1,088 tokens indexed
    # against roughly 18,000 concatenated -- from the deployment this was built
    # for. It is honest and a reader cannot reach it: clone this repository and
    # you get five pages. A number with provenance nobody can reproduce is the
    # weakest kind this project allows itself, so the ratio is computed here,
    # live, on whatever charter is loaded. Five pages show 4.6x; a real one
    # shows an order of magnitude, which is the claim.
    concatenated = sum(
        counter.count(page.path.read_text(encoding="utf-8")) for page in charter.pages
    )
    index_only = counter.count(build_index(charter)) or 1
    print(
        f"index vs all {concatenated / index_only:>5.1f}x  "
        f"({concatenated:,} tokens if every page were pasted in, "
        f"{index_only:,} as an index)"
    )
    for warning in charter.warnings:
        print(f"⚠  {warning}")
    return 0


def cmd_serve(args) -> int:
    from ai_bunker.gateway import serve

    settings = load_settings(args.config)
    if args.host != "127.0.0.1":
        osh.warning(
            f"[gateway] binding {args.host}: the gateway will accept connections from "
            "off this machine. Make sure the API key is set and the network is one you "
            "trust."
        )
    serve(settings, host=args.host, port=args.port)
    return 0


def cmd_doctor(args) -> int:
    """Check that everything the deployment claims is actually true."""
    settings = load_settings(args.config)
    charter = load_charter(settings.charter_dir, locale=settings.language)
    rules = load_rules(settings.rules_dir)
    report = test_rules(rules)

    # (ok, label, detail, fatal). The fourth field is the round-11 addition:
    # this command printed WARN for nine of its ten checks and returned 0
    # unless a rule's own example failed, so the continuous-integration step
    # named "Deployment claims" tested the one thing `rules --check` already
    # tested one step earlier.
    #
    # The original reasoning is kept because it is right about most of them:
    # "an open gateway on a trusted network is a choice, a rule whose own
    # example fails is a bug." A *choice* should be reported and not refused.
    # What it does not cover is a **mistake** -- and a key the loader does not
    # read is never a choice, because an operator who writes one believes it
    # is in effect.
    checks: list[tuple[bool, str, str, bool]] = []

    def check(ok: bool, label: str, detail: str = "", *, fatal: bool = False) -> None:
        checks.append((ok, label, detail, fatal))

    # First, because every check below is measured against the settings this
    # file produced. A key the loader does not read is not a tidiness problem:
    # `served_kontext: 32768` parsed, loaded, and left the gateway declaring
    # 104,857 tokens to clients against an engine serving 32,768 -- the
    # incident this project was built after, by one letter and in silence. It
    # warned on load, and `doctor` still exited 0.
    check(
        not settings.config_strays,
        "every key in the configuration is read",
        "; ".join(settings.config_strays),
        fatal=True,
    )

    check(
        bool(charter.operating_rules),
        "charter carries operating rules",
        ""
        if charter.operating_rules
        else f"no AGENTS.md under {settings.charter_dir}: the model gets an index and no "
        "instruction to consult it",
    )
    check(len(charter.pages) > 0, f"charter has {len(charter.pages)} pages")
    check(
        not [w for w in charter.warnings if "over the" in w or "no pack" in w],
        "every page is within its budget and in a pack",
        "; ".join(charter.warnings),
    )

    check(
        len(rules) > 0,
        f"{len(rules)} rules loaded",
        "" if rules else f"no rules under {settings.rules_dir}",
    )
    check(
        report.ok,
        f"{report.passed} rule assertions pass",
        f"failing: {report.failed[:3]}" if report.failed else "",
    )
    check(
        report.coverage == 1.0,
        f"{report.coverage:.0%} of rules carry evidence",
        f"no examples: {', '.join(report.untested)}" if report.untested else "",
    )
    check(
        any(r.scope == "command" and r.enforces for r in rules),
        "at least one rule can refuse a command",
    )

    # A catalogue that has quietly fallen behind is the normal failure mode of
    # any translation, and the only one worth automating against.
    locale = i18n.negotiate(configured=settings.language)
    absent, extra = i18n.missing(locale)
    untranslated = [r.id for r in rules if locale != "en" and locale not in r.translations]
    check(
        not absent and not extra and not untranslated,
        f"answering in {locale!r}, catalogue complete",
        "; ".join(
            part
            for part in (
                f"{len(absent)} message(s) missing" if absent else "",
                f"{len(extra)} message(s) no longer used" if extra else "",
                f"{len(untranslated)} rule(s) untranslated" if untranslated else "",
            )
            if part
        ),
    )

    check(
        bool(settings.upstreams),
        f"{len(settings.upstreams)} upstream(s) configured",
        "" if settings.upstreams else "nothing to route to",
    )
    for up in settings.upstreams.values():
        reachable = osh.is_working_url(up.tokenize_url + "/v1/models")
        check(
            reachable,
            f"upstream {up.name} answers at {up.base_url}",
            "" if reachable else "not reachable: start the engine, or check the VPN",
        )

    check(
        bool(settings.api_key),
        "an API key is configured",
        "no key: this gateway is open to anyone who can reach it. Fine on a trusted "
        "network, a decision either way",
    )
    check(
        settings.sovereign,
        "no route leaves this network",
        ""
        if settings.sovereign
        else "remote: " + ", ".join(u.name for u in settings.upstreams.values() if u.remote),
    )
    check(
        bool(settings.audit_log),
        "decisions are logged",
        "no audit_log: a governance deployment without an audit trail is not one",
    )
    check(
        settings.enforce_budget,
        "the budget is enforced",
        "budget enforcement is off: a session with no room to work will be served",
    )
    check(
        settings.enforce_commands,
        "commands are screened",
        "command screening is off: a refused command would run",
    )

    width = max(len(label) for _, label, _, _ in checks) + 2
    failed = 0
    fatal = 0
    for ok, label, detail, is_fatal in checks:
        mark = "ok  " if ok else ("FAIL" if is_fatal else "WARN")
        print(f"  [{mark}] {label:<{width}} {detail if not ok else ''}".rstrip())
        failed += 0 if ok else 1
        fatal += 0 if ok or not is_fatal else 1
    print()
    print(f"  {len(checks) - failed}/{len(checks)} checks pass")
    # Said out loud rather than left to be inferred from an exit code. A
    # reader who sees "9/10 checks pass" next to a zero exit is entitled to
    # know which of the two numbers the gate is actually made of.
    if failed and not fatal:
        print("  WARN is a report, not a refusal: these are deployment choices.")
    return 1 if fatal or not report.ok else 0


def cmd_skill(args: argparse.Namespace) -> int:
    """Publish the charter in the Agent Skills format.

    The gateway serves the charter to anything that speaks OpenAI. This serves
    it to everything else: the format is read natively by Claude Code,
    OpenCode, Cursor, Goose, Amp, Roo, Codex, Copilot and Gemini CLI, so a team
    gets its standards into a client this project has no kit for without
    waiting for one.
    """
    if args.import_:
        catalog = read_catalog(args.import_)
        skills = import_skills(args.import_)
        if not skills:
            return 1
        source = args.source or catalog.get("repository", "") or str(args.import_)
        pages = as_charter_pack(
            skills,
            pack=args.pack,
            source=source,
            catalog=catalog,
        )
        if args.print_:
            for rel in sorted(pages):
                print(f"packs/{rel}  ({len(pages[rel]):,} chars)")
            return 0
        written = write_charter_pack(pages, args.directory, force=args.force)
        for path in written:
            print(f"  {path}")
        print(
            f"{len(written)} page(s) from {len(skills)} skill(s) into "
            f"{args.directory}/packs/{args.pack}/"
        )
        if catalog.get("catalog_hash"):
            print(f"  source catalogue hash: {catalog['catalog_hash']}")
        return 0

    if args.check:
        skill = read_skill(args.check)
        problems = validate(skill)
        for problem in problems:
            print(f"  [fail] {problem}")
        for warning in warnings(skill):
            print(f"  [warn] {warning}")
        if not problems:
            print(f"{args.check}: valid Agent Skill ({len(skill.references)} reference file(s))")
        return 1 if problems else 0

    charter = load_charter(args.directory)
    skill = build_skill(
        charter,
        name=args.name,
        description=args.description,
        license_=args.license_,
    )

    if args.print_:
        print(skill.skill_md())
        return 0

    out = args.out or CLIENT_PATHS[args.client]
    written = write_skill(skill, out, force=args.force)
    for path in written:
        print(f"  {path}")
    for warning in warnings(skill):
        print(f"  [warn] {warning}")

    print(f"\n{len(written)} file(s) under {out}/{skill.name}/")
    print(f"fingerprint {charter.fingerprint} -- the charter this copy was made from.")
    # Only when the path came from --client. An explicit --out means the
    # caller already knows where their client looks, and telling them about
    # ours would be noise dressed as help.
    if args.out is None:
        others = ", ".join(
            f"{name} ({path})" for name, path in sorted(CLIENT_PATHS.items()) if path != out
        )
        if args.client == "claude":
            print("Read by Claude Code and by OpenCode, which documents this path as")
            print("Claude-compatible.")
        print(f"Other locations: {others}.")
    return 0


def cmd_spec(args: argparse.Namespace) -> int:
    """Render the rules as Gherkin, or run Gherkin against the rules.

    The second direction is the one that earns its keep. A scenario nobody
    generated is a specification somebody wrote, and an implementation that
    fails it has a gap -- which is how seven of them were found, including
    injection rules that were English-only in a bilingual project.
    """
    rules = load_rules(args.rules)

    if args.export or args.print_:
        sources = sorted({r.source for r in rules})
        out = Path(args.export) if args.export else None
        if out:
            osh.make_directory(str(out))
        for source in sources:
            text = spec_export(rules, source=source)
            if args.print_:
                print(text)
                continue
            assert out is not None
            path = out / (source.removesuffix(".yaml") + ".feature")
            path.write_text(text, encoding="utf-8")
            print(f"  {path}")
        return 0

    directory = args.run or "features"
    if not Path(directory).is_dir():
        print(f"ai-bunker: no scenarios under {directory}/", file=sys.stderr)
        return 2

    try:
        scenarios = spec_load(directory)
    except ValueError as exc:
        print(f"ai-bunker: {exc}", file=sys.stderr)
        return 2

    results = spec_run(scenarios, rules)
    failed = [r for r in results if not r.passed]
    for result in failed:
        print(f"  [fail] {result.scenario.feature} / {result.scenario.name}")
        print(f"         {result.detail}")
    print(f"\n{len(results)} scenario(s), {len(results) - len(failed)} passed")
    if failed:
        print(f"{len(failed)} scenario(s) describe behaviour this deployment does not have.")
    return 1 if failed else 0


def cmd_tools(args: argparse.Namespace) -> int:
    """Read a captured request's tool list, and approve it or compare it.

    Captured rather than fetched, for the same reason the dashboard asks for a
    pasted request body: the gateway sees whatever a client declares, and what
    a client declares is the only honest source for what to approve.
    """
    from ai_bunker.tools import approved_fingerprints, declared_tools, fingerprint, write_lock

    try:
        body = json.loads(Path(args.request).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ai-bunker: cannot read {args.request}: {exc}", file=sys.stderr)
        return 2

    tools = declared_tools(body if isinstance(body, dict) else {})
    if not tools:
        print(f"ai-bunker: {args.request} declares no tools", file=sys.stderr)
        return 2

    if args.pin:
        count = write_lock(tools, args.out)
        print(f"  {count} tool contract(s) approved in {args.out}")
        print("  Commit the diff: that diff is the review.")
        return 0

    approved = approved_fingerprints(args.out)
    if not approved:
        print(f"  {args.out} approves nothing yet; run with --pin to write it")
        for tool in sorted(tools, key=lambda t: t.name):
            print(f"    {fingerprint(tool)}  {tool.name}")
        return 0

    drifted = 0
    for tool in sorted(tools, key=lambda t: t.name):
        now, was = fingerprint(tool), approved.get(tool.name)
        if was is None:
            print(f"  [new ] {tool.name}: {now} (never approved)")
            drifted += 1
        elif was != now:
            print(f"  [DIFF] {tool.name}: approved {was}, declared {now}")
            drifted += 1
        else:
            print(f"  [ok  ] {tool.name}: {now}")
    for name in sorted(set(approved) - {t.name for t in tools}):
        print(f"  [gone] {name}: approved but not declared")
    return 1 if drifted else 0


def cmd_breaker(args: argparse.Namespace) -> int:
    """Read or clear the circuit breakers on a running gateway.

    Over HTTP rather than in process, because the state is in the gateway's
    memory and this is a different process. That is the honest shape: a
    command that pretended to reset a breaker it cannot reach would be worse
    than no command, and the refusal message points an operator here.
    """
    import httpx

    root = args.server.rstrip("/")
    headers = {"authorization": f"Bearer {args.key}"} if args.key else {}
    try:
        if args.reset:
            response = httpx.post(
                f"{root}/v1/breaker/reset",
                params={"session": args.session} if args.session else None,
                headers=headers,
                timeout=10,
            )
        else:
            response = httpx.get(f"{root}/v1/breaker", headers=headers, timeout=10)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"ai-bunker: cannot reach the gateway at {root}: {exc}", file=sys.stderr)
        return 2

    body = response.json()
    if args.reset:
        print(f"  {body.get('closed', 0)} breaker(s) closed")
        return 0

    if not body.get("enabled"):
        print("  the breaker is disabled (breaker.refusals is 0)")
        return 0
    print(f"  {body['refusals']} refusal(s) within {body['window_s']}s stops a session")
    stopped = body.get("open") or []
    if not stopped:
        print("  no session is currently stopped")
        return 0
    for entry in stopped:
        rules = ", ".join(entry.get("rules") or []) or "repeated refusals"
        print(
            f"  {entry['session']}  {entry['refusals']} refusal(s)  "
            f"closes in {entry['closes_in_s']}s  ({rules})"
        )
    return 0


def cmd_adopt(args) -> int:
    settings = load_settings(args.config)
    upstream = (
        settings.upstreams.get(settings.default_upstream) if settings.default_upstream else None
    )
    served = upstream.served_context if upstream else 131_072
    declared = args.declared_context or int(served * settings.declared_fraction)

    clients = tuple(args.client) if args.client else CLIENTS

    if args.list:
        print(
            plan_adopt(
                args.target,
                clients=clients,
                charter=not args.no_charter,
                force=args.force,
            ).summary()
        )
        return 0

    plan = adopt(
        args.target,
        url=args.url,
        api_key=args.api_key or settings.api_key,
        model=args.model,
        declared_context=declared,
        compaction_reserve=args.reserve or settings.compaction_reserve,
        temperature=args.temperature,
        clients=clients,
        charter=not args.no_charter,
        force=args.force,
    )
    print(plan.summary())
    print()
    print(f"Next: cd {plan.target} and start your client.")
    print("      ai-bunker doctor      # check the gateway side")
    return 0


def cmd_detect(args) -> int:
    m = detect_machine()
    print(json.dumps(m, indent=2, default=str))
    return 0


def cmd_catalog(args) -> int:
    print(render_catalog())
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ai-bunker",
        description="Sovereign serving layer for coding agents.",
    )
    p.add_argument("--version", action="version", version=f"ai-bunker {__version__}")
    p.add_argument("-v", "--verbose", action="count", default=0)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("sizing", help="Size a machine: what it holds, how fast, how many people.")
    s.add_argument("--accelerator", help="Catalogue accelerator id (see `ai-bunker catalog`).")
    s.add_argument("--vram", type=float, help="VRAM in GiB, for a machine not in the catalogue.")
    s.add_argument("--bandwidth", type=float, help="Memory bandwidth in GB/s.")
    s.add_argument("--json", action="store_true")
    _add_plan_flags(s)
    _add_assumption_flags(s)
    s.set_defaults(func=cmd_sizing)

    c = sub.add_parser("compare", help="Size several machines side by side.")
    c.add_argument("accelerators", nargs="*", help="Accelerator ids; default: all of them.")
    c.add_argument("--json", action="store_true")
    c.add_argument("--no-prices", action="store_true", help="Omit the cost-per-person block.")
    _add_plan_flags(c)
    _add_assumption_flags(c)
    c.set_defaults(func=cmd_compare)

    r = sub.add_parser("recommend", help="Which machine to buy for a team of N.")
    r.add_argument("--team", type=int, required=True, help="Number of people to serve.")
    r.add_argument(
        "--personal",
        action="store_true",
        help="Size a single-person workstation: do not disqualify "
        "accelerators that lack continuous batching.",
    )
    r.add_argument("--top", type=int, default=6, help="Rows in the full field (6).")
    r.add_argument("--json", action="store_true")
    _add_plan_flags(r)
    _add_assumption_flags(r)
    r.set_defaults(func=cmd_recommend)

    b = sub.add_parser(
        "budget",
        help="What a session costs before it starts working, counted by the server.",
    )
    b.add_argument("request", help="Captured OpenAI-format request body (JSON).")
    b.add_argument(
        "--served-context",
        type=int,
        required=True,
        help="What the engine actually serves (vLLM --max-model-len).",
    )
    b.add_argument(
        "--declared-context",
        type=int,
        # The literal percent is doubled: argparse runs every help string
        # through %-formatting, so a bare "80%" makes `--help` raise rather
        # than print. Found by running the command while writing the examples;
        # no test covered --help until one did.
        help=f"What the client is told (default: {DECLARED_FRACTION:.0%} of served).".replace(
            "%", "%%"
        ),
    )
    b.add_argument("--reserve", type=int, default=0, help="Client compaction margin.")
    b.add_argument("--max-output", type=int, default=4096)
    b.add_argument(
        "--min-working",
        type=int,
        default=MIN_WORKING_TOKENS,
        help=f"Conversation space below which the verdict is unusable ({MIN_WORKING_TOKENS}).",
    )
    b.add_argument("--base-url", help="Serving endpoint, for the exact /tokenize count.")
    b.add_argument("--model-name", help="Model to tokenize against.")
    b.add_argument("--charter", help="Charter file, so its cost is attributed to us.")
    b.add_argument("--index", help="Knowledge index file, likewise.")
    b.add_argument(
        "--exact", action="store_true", help="Fail rather than fall back to a ratio estimate."
    )
    b.add_argument(
        "--gate", action="store_true", help="Exit non-zero when the verdict is unusable, for CI."
    )
    b.add_argument("--json", action="store_true")
    b.set_defaults(func=cmd_budget)

    r = sub.add_parser("rules", help="Load, check, or apply the rules.")
    r.add_argument("--directory", default="charter/rules")
    r.add_argument(
        "--check",
        action="store_true",
        help="Run every rule against its own examples; exit non-zero on failure.",
    )
    r.add_argument("--command", help="Screen one shell command.")
    r.add_argument("--screen", help="Screen a file's content, or `-` for stdin (the default).")
    r.add_argument(
        "--cost",
        action="store_true",
        help=(
            "With --check, also measure what this rule set costs to screen "
            "100 KB. Machine-dependent, which is why it is not in the default "
            "table; --json always carries it."
        ),
    )
    r.add_argument(
        "--provenance",
        metavar="SOURCE",
        help="Also wrap the screened text as untrusted data from SOURCE.",
    )
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_rules)

    ch = sub.add_parser("charter", help="Inspect the charter and what it costs.")
    ch.add_argument("--directory", default="charter")
    ch.add_argument("--index", action="store_true", help="Print the index as injected.")
    ch.add_argument(
        "--lang",
        default=DEFAULT_LOCALE,
        help=(
            "Render the index in this language, to see what a deployment with "
            "that `language:` actually injects. Default: en."
        ),
    )
    ch.add_argument("--page", help="Print one page by its index reference.")
    ch.add_argument("--json", action="store_true")
    ch.set_defaults(func=cmd_charter)

    ad = sub.add_parser("adopt", help="Equip a repository with the charter and a client kit.")
    ad.add_argument("target", help="The repository to equip.")
    ad.add_argument(
        "--client",
        action="append",
        choices=list(ALL_CLIENTS),
        help=(
            "Which kit(s) to write. Repeatable. Default: "
            + ", ".join(CLIENTS)
            + " -- the code agents. The frameworks ("
            + ", ".join(FRAMEWORKS)
            + ") are opt-in, because their kit is a Python module and writing "
            "application code into a repository by default is not this "
            "command's job."
        ),
    )
    ad.add_argument(
        "--no-charter",
        action="store_true",
        help="Only write the client kit; the repository keeps its own charter.",
    )
    ad.add_argument("--url", default="http://127.0.0.1:8000/v1", help="Gateway base URL.")
    ad.add_argument("--api-key", default="", help="Gateway key (default: the one in config).")
    ad.add_argument("--model", default="devstral")
    ad.add_argument(
        "--declared-context",
        type=int,
        help="Default: the configured upstream's served context x declared_fraction.",
    )
    ad.add_argument("--reserve", type=int, help="Client compaction margin.")
    ad.add_argument("--temperature", type=float, default=0.15)
    ad.add_argument("--force", action="store_true", help="Replace files that already exist.")
    ad.add_argument("--list", action="store_true", help="Show what would be written.")
    ad.add_argument("--config", default=None)
    ad.set_defaults(func=cmd_adopt)

    sk = sub.add_parser(
        "skill",
        help="Publish the charter as an Agent Skill, for clients with no kit.",
    )
    sk.add_argument("--directory", default="charter", help="Charter to publish.")
    sk.add_argument(
        "--out",
        default=None,
        help="Where to write it. Default: the path for --client.",
    )
    sk.add_argument(
        "--client",
        default="claude",
        choices=sorted(CLIENT_PATHS),
        help=(
            "Which client's skills directory to target. 'claude' by default "
            "because OpenCode reads that path too, so one copy serves both."
        ),
    )
    sk.add_argument("--name", default="team-charter", help="Skill name and directory name.")
    sk.add_argument("--description", default="", help="Override the generated description.")
    sk.add_argument("--license", dest="license_", default="", help="License field.")
    sk.add_argument("--force", action="store_true", help="Replace files that already exist.")
    sk.add_argument("--check", metavar="DIR", help="Validate an existing skill instead.")
    sk.add_argument(
        "--import",
        dest="import_",
        metavar="DIR",
        help=(
            "Read a skills tree someone else wrote and write it into this "
            "charter as a pack. The inverse of the export: the gateway then "
            "serves those pages as an index, counted by the budget."
        ),
    )
    sk.add_argument(
        "--pack",
        default="imported",
        help="Pack name the imported pages land under. Used with --import.",
    )
    sk.add_argument(
        "--source",
        default="",
        help=(
            "Provenance recorded on every imported page. Defaults to the "
            "source catalogue's repository, then to the path."
        ),
    )
    sk.add_argument(
        "--print", dest="print_", action="store_true", help="Print SKILL.md, write nothing."
    )
    sk.set_defaults(func=cmd_skill)

    sp = sub.add_parser(
        "spec",
        help="The rule set as Gherkin a non-programmer can read and approve.",
    )
    sp.add_argument("--rules", default="charter/rules", help="Rules to read.")
    sp.add_argument(
        "--export",
        metavar="DIR",
        help="Write one .feature per rules file into DIR.",
    )
    sp.add_argument(
        "--run",
        metavar="DIR",
        default=None,
        help="Run every scenario under DIR against the engine (default: features/).",
    )
    sp.add_argument("--print", dest="print_", action="store_true", help="Print, write nothing.")
    sp.set_defaults(func=cmd_spec)

    sv = sub.add_parser("serve", help="Run the gateway.")
    sv.add_argument("--config", default=None, help="Gateway config (default: config/gateway.yaml).")
    sv.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address. Localhost by default: a sovereignty tool that "
        "listens on every interface has made its user's decision.",
    )
    sv.add_argument("--port", type=int, default=8000)
    sv.set_defaults(func=cmd_serve)

    dr = sub.add_parser("doctor", help="Check that everything the deployment claims is true.")
    dr.add_argument("--config", default=None)
    dr.set_defaults(func=cmd_doctor)

    tl = sub.add_parser(
        "tools",
        help="Approve the tool contracts a captured request declares, or check them.",
    )
    tl.add_argument("request", help="A captured request body, as JSON.")
    tl.add_argument("--pin", action="store_true", help="Write the approvals instead of checking.")
    tl.add_argument("--out", default="config/tools.lock", help="The approval file.")
    tl.set_defaults(func=cmd_tools)

    bk = sub.add_parser(
        "breaker",
        help="Which sessions a gateway has stopped, and clear them.",
    )
    bk.add_argument("--server", default="http://127.0.0.1:8000", help="Gateway root URL.")
    bk.add_argument("--key", default="", help="Gateway API key, if it requires one.")
    bk.add_argument("--reset", action="store_true", help="Close the breakers instead.")
    bk.add_argument("--session", default="", help="Only this session, rather than all.")
    bk.set_defaults(func=cmd_breaker)

    fb = sub.add_parser(
        "fallback",
        help="When the model does not fit: should it be streamed off storage, and at what cost.",
    )
    fb.add_argument("--model", default="devstral-small-2-24b", help="Catalogue model id.")
    fb.add_argument(
        "--mode",
        # Every spelling the suite accepts, so `--mode off` keeps working and
        # `--mode never` reads the same as `airllm: never` does next door.
        choices=sorted(set(MODE_ALIASES)),
        default="",
        metavar="{auto,always,never}",
        help="never: do not stream, only report what it would cost. auto: stream when it does "
        "not fit and clears --floor. always: stream because you said so. Spelled the way "
        "best-engine-ai-helper spells it; `off`/`on` are aliases. Default: $BEST_ENGINE_AIRLLM, "
        "else auto.",
    )
    fb.add_argument(
        "--floor",
        choices=list(VERDICTS),
        default="batch",
        help="Worst verdict --mode auto will accept. (batch)",
    )
    fb.add_argument("--accelerator", help="Catalogue accelerator id; default is this machine.")
    fb.add_argument("--ram", type=float, help="System memory in GiB, where the page cache lives.")
    fb.add_argument("--bandwidth", type=float, help="Memory bandwidth in GB/s, for the comparison.")
    fb.add_argument(
        "--storage",
        help="Catalogue storage class: " + ", ".join(sorted(storage_classes())),
    )
    fb.add_argument(
        "--disk",
        type=float,
        help="Measured uncached read bandwidth in GB/s. Beats any class: "
        "python scripts/bench_disk.py",
    )
    fb.add_argument(
        "--cached",
        type=float,
        help="Measured page-cache re-read rate in GB/s, from the same script. Measuring the "
        "drive does not measure this.",
    )
    fb.add_argument("--disk-efficiency", type=float, default=0.85)
    fb.add_argument(
        "--answer-tokens", type=int, default=500, help="Answer the verdict judges (500)."
    )
    fb.add_argument("--context", type=int, help="Context to serve; default is the model's maximum.")
    fb.add_argument("--quant", default="", help="Weight table to hand the engine.")
    fb.add_argument(
        "--compression",
        default="",
        choices=["", "none", "4bit", "8bit"],
        help="AirLLM block-wise compression of the shards: fewer bytes per layer is the only "
        "knob with real leverage here.",
    )
    fb.add_argument("--kv-dtype", default="bf16", choices=["bf16", "fp8"])
    fb.add_argument(
        "--shards",
        default="~/.cache/ai-bunker/shards",
        help="Where the split checkpoint would go. The free space there is read and compared "
        "against what the split needs, which is the one figure here that is checked rather "
        "than projected. Empty to skip the check.",
    )
    fb.add_argument("--json", action="store_true")
    fb.set_defaults(func=cmd_fallback)

    al = sub.add_parser(
        "airllm",
        help="Run the layer-streaming engine as an upstream the gateway can proxy.",
    )
    al.add_argument(
        "action",
        choices=["serve"],
        help="Only `serve` today. The decision of whether to is `ai-bunker fallback`.",
    )
    al.add_argument("--model", required=True, help="Hugging Face repository id, or a local path.")
    al.add_argument("--host", default="127.0.0.1")
    al.add_argument("--port", type=int, default=8003)
    al.add_argument("--context", type=int, default=8192, help="Maximum sequence length (8192).")
    al.add_argument("--compression", default="", choices=["", "none", "4bit", "8bit"])
    al.add_argument(
        "--shards",
        default="",
        help="Where to keep the split checkpoint. Worth setting: it wants as much room as the "
        "original.",
    )
    al.add_argument(
        "--allow-download",
        action="store_true",
        help="Permit fetching the checkpoint from a model hub. Off by default: a repository id "
        "is refused rather than quietly downloaded, because a deployment whose argument is that "
        "nothing leaves the local network does not reach a third party on a default.",
    )
    al.add_argument(
        "--eager",
        action="store_true",
        help="Split and load before the socket opens, so a scripted deployment fails at start "
        "rather than on the first request.",
    )
    al.set_defaults(func=cmd_airllm)

    d = sub.add_parser("detect", help="What os-helper sees about this machine.")
    d.set_defaults(func=cmd_detect)

    k = sub.add_parser("catalog", help="Print the serving catalogue.")
    k.set_defaults(func=cmd_catalog)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    osh.verbosity(1 + args.verbose)
    try:
        return int(args.func(args))
    except AssertionError as exc:  # osh.check failures are user-facing
        print(f"ai-bunker: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
