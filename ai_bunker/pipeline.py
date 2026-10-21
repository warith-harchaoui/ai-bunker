"""
The pipeline: charter in, rules both ways, budget enforced.

This is where the three modules meet, and the arrangement is the product. A
gateway sees two things a client-side plugin does not see reliably, and it sees
them for **every** client -- Claude Code, OpenCode, Cursor, Continue, a curl
one-liner -- with no way to opt out by swapping harness.

Four stages, in this order, and the order is load-bearing:

1. **Screen inbound tool results.** A ``role: "tool"`` message is text the
   world just handed the agent: a file, a web page, an issue body, a CI log.
   This is where secrets arrive on their way into the transcript, and where
   indirect prompt injection arrives on its way into the model's instructions.
   It is screened and marked before anything else looks at it.

2. **Inject the charter.** The operating rules and the index, as the first
   system block. First because a serving engine's prefix cache re-serves an
   unchanged prefix almost for free, and a charter that moves position breaks
   that for every request behind it.

3. **Measure and enforce the budget.** Count the real request with the real
   tokenizer. A session with no room to work is refused here, with the
   component responsible named, rather than being allowed to fail later as a
   context-length error the user cannot act on.

4. **Screen outbound tool calls.** When the model answers with a ``tool_call``
   carrying a shell command, that command has not run yet. Refusing it here is
   the only enforcement point that no client can bypass.

Stage 1 and stage 4 are the two scopes of the rule engine, and a gateway is the
first place both of them exist at once.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import os_helper as osh

from ai_bunker.breaker import as_rule as breaker_rule
from ai_bunker.budget import Budget, Counter, measure_request
from ai_bunker.charter import Charter, system_blocks
from ai_bunker.dependencies import as_note as dependency_note
from ai_bunker.dependencies import as_rule as dependency_rule
from ai_bunker.dependencies import check as dependency_check
from ai_bunker.i18n import DEFAULT_LOCALE
from ai_bunker.payments import as_rule as payment_rule
from ai_bunker.payments import inspect as payment_inspect
from ai_bunker.rules import (
    Decision,
    Rule,
    Violation,
    decisions_for,
    refusal_message,
    screen_command,
    screen_output,
    wrap_provenance,
)
from ai_bunker.tools import screen as screen_tools

#: Tool-call function names whose arguments are shell commands. A gateway
#: cannot know every client's tool vocabulary, so this is a default that a
#: deployment overrides rather than a claim to completeness.
SHELL_TOOLS = ("bash", "shell", "run_command", "execute_command", "terminal")

#: Argument keys that carry the command within those calls.
COMMAND_KEYS = ("command", "cmd", "script", "input")


@dataclass
class Applied:
    """What the pipeline did to one request, and why."""

    request: dict[str, Any]
    budget: Budget | None = None
    inbound: list[Violation] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    refusal: Rule | None = None
    refused_command: str | None = None
    #: Tools taken off the table before the model saw them. Named rather than
    #: counted: an agent told "a tool was withheld" cannot tell the user which
    #: capability it has lost.
    withheld_tools: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether the request may proceed to the model."""
        return self.budget is None or self.budget.verdict != "unusable"

    def audit(self) -> list[dict[str, Any]]:
        return [d.as_dict() for d in self.decisions]


# ---------------------------------------------------------------------------
# Stage 1 — inbound tool results
# ---------------------------------------------------------------------------


def _tool_source(message: dict[str, Any]) -> str:
    """A human-readable origin for a tool result, for the provenance marker.

    A reader deciding whether to trust a block wants to know whether it came
    from the repository or from the open web, so the tool's own name is the
    most honest label available at this layer.
    """
    name = message.get("name") or message.get("tool_call_id") or "tool"
    return f"tool:{name}"


def screen_inbound(
    messages: list[dict[str, Any]],
    rules: list[Rule],
    *,
    mark_provenance: bool = True,
    preamble: bool = False,
) -> tuple[list[dict[str, Any]], list[Violation]]:
    """Screen every tool result on its way into the conversation.

    Only ``role: "tool"`` messages are touched. User and assistant turns are
    the conversation itself: redacting a user's own words would be both
    surprising and useless, since the user already has them.

    Parameters
    ----------
    messages : list of dict
        The conversation, as an OpenAI-format request carries it.
    rules : list of Rule
        Rules of any scope; only ``output`` rules apply here.
    mark_provenance : bool
        Wrap each screened result so the model is told, structurally, that it
        is data rather than instruction. This is the defence that holds when
        the patterns miss.
    preamble : bool
        Whether each marked block repeats the full explanation. Off by
        default: the charter already carries it, and paying for it on every
        tool result in a long session is exactly the kind of waste this
        project exists to measure.

    Returns
    -------
    (messages, violations)
        A new message list; the input is not mutated.
    """
    out: list[dict[str, Any]] = []
    fired: dict[str, Violation] = {}

    for message in messages:
        if message.get("role") != "tool" or not isinstance(message.get("content"), str):
            out.append(message)
            continue

        screened = screen_output(message["content"], rules)
        for violation in screened.violations:
            if violation.rule.id in fired:
                fired[violation.rule.id].count += violation.count
            else:
                fired[violation.rule.id] = Violation(rule=violation.rule, count=violation.count)

        content = screened.text
        if screened.violations:
            content += screened.note
        if mark_provenance:
            content = wrap_provenance(content, source=_tool_source(message), preamble=preamble)
        out.append({**message, "content": content})

    return out, list(fired.values())


# ---------------------------------------------------------------------------
# Stage 2 — the charter
# ---------------------------------------------------------------------------


def inject_charter(messages: list[dict[str, Any]], charter: Charter) -> list[dict[str, Any]]:
    """Put the charter's blocks at the head of the conversation.

    Prepended rather than appended to the client's own system message, and
    kept in a stable position, because a serving engine's prefix cache only
    helps while the head of the prompt is byte-identical between requests.
    Moving the charter would invalidate the cache for everything behind it --
    measured elsewhere as the difference between a near-free system prompt and
    one re-processed on every turn.

    Idempotent: a conversation that already carries these blocks is returned
    unchanged, so a request replayed through the gateway does not accumulate
    copies of the charter.
    """
    blocks = system_blocks(charter)
    if not blocks:
        return messages

    existing = "\n".join(str(m.get("content") or "") for m in messages if m.get("role") == "system")
    missing = [b for b in blocks if b not in existing]
    if not missing:
        return messages

    return [{"role": "system", "content": b} for b in missing] + list(messages)


# ---------------------------------------------------------------------------
# Stage 4 — outbound tool calls
# ---------------------------------------------------------------------------


def _commands_in(
    tool_calls: list[dict[str, Any]], shell_tools: tuple[str, ...]
) -> list[tuple[int, str]]:
    """Extract (index, command) for every shell-shaped call."""
    found: list[tuple[int, str]] = []
    for i, call in enumerate(tool_calls or []):
        function = call.get("function") or {}
        name = str(function.get("name") or "").lower()
        if name not in shell_tools:
            continue
        raw = function.get("arguments")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                # A client that sends unparseable arguments is not a reason to
                # wave the call through: screen the raw string instead.
                found.append((i, str(function.get("arguments"))))
                continue
        if isinstance(raw, dict):
            for key in COMMAND_KEYS:
                if isinstance(raw.get(key), str):
                    found.append((i, raw[key]))
                    break
    return found


def screen_outbound(
    tool_calls: list[dict[str, Any]],
    rules: list[Rule],
    *,
    shell_tools: tuple[str, ...] = SHELL_TOOLS,
    project_root: str | None = None,
    check_payments: bool = True,
    trust: Any = None,
    locale: str = DEFAULT_LOCALE,
) -> tuple[Rule | None, str | None, list[Violation]]:
    """Screen the shell commands a model is asking to run.

    The command has not executed yet. This is the enforcement point no client
    can bypass -- a client-side hook can be disabled by editing a config file,
    and a different harness simply never had it.

    Returns
    -------
    (refusal, command, notes)
        The first BLOCKER that refuses a call, the command it refused, and
        every rule that matched across all calls.
    """
    notes: list[Violation] = []
    refusal: Rule | None = None
    refused: str | None = None

    for _, command in _commands_in(tool_calls, shell_tools):
        blocked, matched = screen_command(command, rules)
        # A purpose is the one piece of agent-authored text the decision log
        # keeps, so it goes through the output rules first. The log exists
        # because the engine redacts secrets; a gate that wrote an agent's
        # unscreened sentence into it would hand back a place to put one.
        for note in matched:
            if note.purpose:
                note.purpose = screen_output(note.purpose, rules).text
        notes.extend(matched)
        if blocked is not None and refusal is None:
            refusal, refused = blocked, command

        # A package name the project never declared is either a hallucination
        # or a dependency nobody approved. Decided in code rather than by a
        # pattern, because the answer depends on the repository, not on the
        # shape of the command.
        if project_root and refusal is None:
            result = dependency_check(command, project_root)
            if not result.ok:
                refusal, refused = dependency_rule(result), command
                notes.append(
                    Violation(
                        rule=refusal,
                        count=len(result.undeclared) or len(result.mismatched),
                    )
                )
            elif result.unpinned:
                # Noted, not refused: installing a pinned package without
                # naming its version is usually a human typing the obvious
                # thing, and the cost of refusing it would exceed the risk.
                notes.append(
                    Violation(rule=dependency_note(result, locale), count=len(result.unpinned))
                )

    # Payments are screened over EVERY tool call, not only the shell ones. A
    # payment does not arrive as a command -- it arrives as `create_payment`,
    # or as an HTTP tool pointed at a card processor -- so restricting this to
    # SHELL_TOOLS would check the one place it never happens.
    if check_payments:
        for call in tool_calls:
            function = call.get("function") or {}
            finding = payment_inspect(
                str(function.get("name") or ""), function.get("arguments") or {}, trust
            )
            if finding.ok:
                continue
            rule = payment_rule(finding, locale)
            notes.append(Violation(rule=rule, count=1))
            if refusal is None:
                refusal, refused = rule, str(function.get("name") or "")

    return refusal, refused, notes


def refusal_as_tool_result(
    call: dict[str, Any], rule: Rule, locale: str = DEFAULT_LOCALE
) -> dict[str, Any]:
    """The message an agent gets back instead of running a refused command.

    Shaped as a tool result rather than an HTTP error on purpose. An agent that
    receives a 4xx has no idea what to do and usually retries the same call; an
    agent that receives a tool result reads it, and the text tells it this was
    a decision rather than a transient failure.
    """
    return {
        "role": "tool",
        "tool_call_id": call.get("id", ""),
        "name": (call.get("function") or {}).get("name", "bash"),
        "content": refusal_message(rule, locale),
    }


# ---------------------------------------------------------------------------
# The whole pipeline
# ---------------------------------------------------------------------------


def apply_inbound(
    request: dict[str, Any],
    *,
    charter: Charter,
    rules: list[Rule],
    counter: Counter,
    served_context: int,
    compaction_reserve: int = 0,
    declared_context: int | None = None,
    min_working: int | None = None,
    mark_provenance: bool = True,
    locale: str = DEFAULT_LOCALE,
    pins: Any = None,
    session: str = "",
    approved_tools: dict[str, str] | None = None,
) -> Applied:
    """Run stages 1 to 3 over an inbound request.

    Returns
    -------
    Applied
        The rewritten request, the measured budget, what fired, and the audit
        records. Check :attr:`Applied.ok` before forwarding: a request whose
        budget leaves no room to work must be refused here, where the reason
        can be named, rather than downstream as an opaque context-length error.
    """
    messages = list(request.get("messages") or [])

    # Stage 0, in effect: the tool list. It is read before the tool results
    # because a declaration is read by the planner on every turn, where a
    # result is read once -- and because a withheld tool must be gone before
    # the budget is measured, or the request is costed for a tool the model
    # will never be offered.
    with_tools, declarations, withheld = screen_tools(
        request, rules, locale, pins=pins, session=session, approved=approved_tools
    )

    screened, inbound = screen_inbound(messages, rules, mark_provenance=mark_provenance)
    with_charter = inject_charter(screened, charter)

    prepared = {**with_tools, "messages": with_charter}

    blocks = system_blocks(charter)
    budget_kwargs: dict[str, Any] = {
        "counter": counter,
        "served_context": served_context,
        "charter": blocks[0] if blocks else None,
        "knowledge_index": blocks[1] if len(blocks) > 1 else None,
        "compaction_reserve": compaction_reserve,
        "declared_context": declared_context,
    }
    if min_working is not None:
        budget_kwargs["min_working"] = min_working
    budget = measure_request(prepared, **budget_kwargs)

    fingerprint = charter.fingerprint[:16] if charter.pages or charter.operating_rules else ""
    return Applied(
        request=prepared,
        budget=budget,
        inbound=inbound + declarations,
        decisions=decisions_for(inbound + declarations, charter=fingerprint),
        withheld_tools=[tool.name for tool in withheld],
    )


def apply_outbound(
    response: dict[str, Any],
    *,
    rules: list[Rule],
    charter_fingerprint: str = "",
    shell_tools: tuple[str, ...] = SHELL_TOOLS,
    project_root: str | None = None,
    check_payments: bool = True,
    trust: Any = None,
    breaker: Any = None,
    session: str = "",
    locale: str = DEFAULT_LOCALE,
) -> Applied:
    """Run stage 4 over a model response.

    The response is returned unchanged when nothing fires. When a command is
    refused, :attr:`Applied.refusal` carries the rule and the caller turns it
    into a tool result with :func:`refusal_as_tool_result`.
    """
    choices = response.get("choices") or []
    calls: list[dict[str, Any]] = []
    for choice in choices:
        message = choice.get("message") or {}
        calls.extend(message.get("tool_calls") or [])

    # An open breaker is consulted before the rules, and refuses every tool
    # call regardless of what it is. That is the point: the session has
    # already been told no enough times, and the next thing to establish is
    # not whether this particular command is allowed.
    if breaker is not None and calls:
        trip = breaker.state(session)
        if trip is not None:
            stopped = breaker_rule(trip, locale=locale)
            return Applied(
                request=response,
                refusal=stopped,
                refused_command=_first_command(calls, shell_tools),
                decisions=decisions_for(
                    [Violation(rule=stopped)], refusal=stopped, charter=charter_fingerprint
                ),
            )

    refusal, command, notes = screen_outbound(
        calls,
        rules,
        shell_tools=shell_tools,
        project_root=project_root,
        check_payments=check_payments,
        trust=trust,
        locale=locale,
    )
    if refusal is not None:
        osh.warning(f"[gateway] {refusal.id} refused a tool call: {refusal.description}")

    decisions = decisions_for(notes, refusal=refusal, charter=charter_fingerprint)

    # Counted after screening, so this turn's refusal is part of the evidence
    # that opens the breaker rather than the one after it.
    if breaker is not None and session:
        breaker.record(session, decisions)

    return Applied(
        request=response,
        refusal=refusal,
        refused_command=command,
        decisions=decisions,
    )


def _first_command(calls: list[dict[str, Any]], shell_tools: tuple[str, ...]) -> str | None:
    """The command a stopped turn was going to run, for the audit record.

    Best effort: a breaker refuses every tool call, including ones that carry
    no command at all, and naming the first shell command is more use to the
    reader of a log than naming nothing.
    """
    for call in calls:
        function = call.get("function") or {}
        if function.get("name") not in shell_tools:
            continue
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except (ValueError, TypeError):
                continue
        if isinstance(arguments, dict):
            for key in COMMAND_KEYS:
                value = arguments.get(key)
                if isinstance(value, str) and value.strip():
                    return value
    return None
