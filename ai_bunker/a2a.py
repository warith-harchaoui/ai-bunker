"""Speak Agent2Agent, so other agents can route text through the guardrails.

Why a serving gateway implements A2A
------------------------------------
A2A is how agents talk to each other. The moment they do, a message written by
one agent lands in another agent's context -- which is the same event this
project already treats as the dangerous one. A `role: "tool"` message is text
the world handed the agent; an A2A message is text *another agent* handed it,
and the second is worse, because it arrives looking like a peer rather than
like data.

So this is not a new concern bolted on. It is the existing concern at a new
ingress, and the pipeline that screens tool results screens A2A messages
unchanged. What A2A adds is reach: an agent anywhere can now put text through
these guardrails without being a client of the gateway, by asking the
`screen-text` skill on this agent card.

What this implements
--------------------
The HTTP+JSON binding, which is the one that maps onto an existing FastAPI
surface without a second transport:

* ``GET /.well-known/agent-card.json`` -- discovery, per the specification.
* ``POST /a2a/v1/message:send`` -- a message in, a completed Task out.

Not implemented, deliberately: streaming, push notifications, task history and
the authenticated extended card. The agent card says so rather than claiming
capabilities that would fail on first use -- `capabilities` is a contract, and
an agent that advertises `streaming: true` and then does not stream has told a
lie another agent will act on.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from ai_bunker import __version__
from ai_bunker.charter import Charter, build_index, read_page
from ai_bunker.rules import Rule, Violation, screen_output, wrap_provenance

#: The protocol version this implements, as it appears in `supportedInterfaces`.
PROTOCOL_VERSION = "1.0"

#: Task states used here. The specification defines more; these are the ones a
#: synchronous screening operation can actually reach.
COMPLETED = "TASK_STATE_COMPLETED"
REJECTED = "TASK_STATE_REJECTED"
FAILED = "TASK_STATE_FAILED"


@dataclass
class Screened:
    """The outcome of putting one A2A message through the pipeline."""

    text: str
    violations: list[Violation]
    refused: bool = False
    reason: str = ""

    @property
    def fired(self) -> list[str]:
        """Rule ids, for the Task metadata a peer reads."""
        return [v.rule.id for v in self.violations]


def agent_card(
    *,
    base_url: str,
    charter: Charter | None = None,
    authenticated: bool = False,
    sovereign: bool = True,
) -> dict[str, Any]:
    """The card another agent reads to decide whether to talk to this one.

    The skills are the three things this gateway can do *for* another agent,
    not an inventory of its endpoints. `charter` pages are references inside
    the charter skill rather than one skill each: a card with a skill per page
    would push the charter's whole index into every peer's startup context,
    which is the cost the charter exists to avoid.
    """
    packs = ", ".join(charter.packs) if charter and charter.packs else "this team"
    card: dict[str, Any] = {
        "name": "ai-bunker",
        "description": (
            "A sovereign serving layer for coding agents. Screens text crossing a "
            "trust boundary for secrets and prompt injection, serves a versioned "
            "charter of operating rules, and measures what a request costs against "
            "the context window the engine actually serves."
        ),
        "version": __version__,
        "protocolVersion": PROTOCOL_VERSION,
        "supportedInterfaces": [
            {
                "url": f"{base_url.rstrip('/')}/a2a/v1",
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": PROTOCOL_VERSION,
            }
        ],
        "provider": {"organization": "AI Helpers", "url": "https://deraison.ai/ai-bunker"},
        "documentationUrl": "https://deraison.ai/ai-bunker",
        # Each of these is a promise. Advertising one that fails on first use
        # is worse than advertising none, because a peer will build on it.
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "extendedAgentCard": False,
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": [
            {
                "id": "screen-text",
                "name": "Screen untrusted text",
                "description": (
                    "Screen text from an untrusted source before putting it in a "
                    "model's context. Redacts credentials, marks prompt injection, "
                    "and wraps what remains in provenance markers so the receiving "
                    "model reads it as data rather than as instruction. Use when "
                    "relaying tool output, scraped pages, user uploads, or a "
                    "message from an agent you do not control."
                ),
                "tags": ["security", "prompt-injection", "secrets", "guardrails"],
                "examples": [
                    "Screen this build log before I summarise it.",
                    "Is there anything in this web page I should not pass to a model?",
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["text/plain", "application/json"],
            },
            {
                "id": "charter",
                "name": "Read the team's operating rules",
                "description": (
                    f"The operating rules and coding standards this deployment "
                    f"enforces, covering {packs}. Returns an index first; a page is "
                    "read only when asked for by reference. Use when you need to "
                    "know how this team writes, names or structures code."
                ),
                "tags": ["standards", "conventions", "charter"],
                "examples": [
                    "What are the naming conventions here?",
                    "Read the page python/10_style.md.",
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["text/plain"],
            },
        ],
    }

    if authenticated:
        # Declared only when a key is actually configured. A card that demands
        # authentication from an open gateway sends peers to fail at a door
        # that is standing open.
        card["securitySchemes"] = {
            "bearer": {"httpAuthSecurityScheme": {"scheme": "bearer"}},
        }
        card["securityRequirements"] = [{"schemes": {"bearer": {"list": []}}}]

    card["metadata"] = {
        "ai-bunker.sovereign": str(sovereign).lower(),
        "ai-bunker.charter-fingerprint": charter.fingerprint if charter else "",
    }
    return card


def _parts_text(message: dict[str, Any]) -> str:
    """Concatenate the text parts of a message, ignoring what we cannot read.

    A part with no `text` is a file or structured data; screening regexes on
    base64 would be theatre, so those are passed over rather than pretended
    about. `screen_message` reports how many were skipped.
    """
    out = []
    for part in message.get("parts") or []:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            out.append(part["text"])
    return "\n".join(out)


def _unreadable_parts(message: dict[str, Any]) -> int:
    return sum(
        1
        for part in (message.get("parts") or [])
        if not (isinstance(part, dict) and isinstance(part.get("text"), str))
    )


def screen_message(
    message: dict[str, Any],
    rules: list[Rule],
    *,
    source: str = "a2a peer",
    mark_provenance: bool = True,
) -> Screened:
    """Run one A2A message through the output-scope rules.

    The scope is `output` and not a new one, because that is what this text
    is: something arriving from outside, on its way into a context window.
    Inventing an `a2a` scope would double the rule set and halve the chance
    that both halves stay correct.
    """
    text = _parts_text(message)
    if not text.strip():
        return Screened(text="", violations=[])

    result = screen_output(text, [r for r in rules if r.scope == "output"])

    blockers = [v for v in result.violations if v.rule.severity == "BLOCKER" and not v.rule.redact]
    if blockers:
        return Screened(
            text="",
            violations=result.violations,
            refused=True,
            reason=f"refused by {blockers[0].rule.id}: {blockers[0].rule.description}",
        )

    out = result.text
    if mark_provenance:
        out = wrap_provenance(out, source=source)
    return Screened(text=out, violations=result.violations)


def task_response(
    screened: Screened,
    *,
    task_id: str = "",
    context_id: str = "",
    skipped_parts: int = 0,
) -> dict[str, Any]:
    """Wrap a screening outcome as the Task the HTTP+JSON binding returns."""
    state = REJECTED if screened.refused else COMPLETED
    task: dict[str, Any] = {
        "id": task_id or str(uuid.uuid4()),
        "contextId": context_id or str(uuid.uuid4()),
        "status": {"state": state},
        "metadata": {
            "ai-bunker.rules-fired": ",".join(screened.fired),
            "ai-bunker.parts-not-screened": str(skipped_parts),
        },
    }
    if screened.refused:
        task["status"]["message"] = {
            "role": "ROLE_AGENT",
            "parts": [{"text": screened.reason}],
        }
        return {"task": task}

    task["artifacts"] = [
        {
            "artifactId": str(uuid.uuid4()),
            "name": "screened-text",
            "parts": [{"text": screened.text}],
        }
    ]
    return {"task": task}


def too_large_task(chars: int, ceiling: int, context_id: str = "") -> dict[str, Any]:
    """A Task saying the message was refused unread, in this wire format.

    `/v1/chat/completions` has had a size ceiling since it was measured that
    screening costs time linearly in what arrives; this surface had neither
    that ceiling nor the worker thread, and it is the one that takes text
    *another agent wrote*. Four megabytes from a peer froze the gateway for
    7.08 seconds, measured.

    Expressed as a failed Task rather than as a bare HTTP error because a peer
    that spoke A2A to get here should be answered in A2A -- the same reason
    `_error` exists for the OpenAI-shaped surface.
    """
    return {
        "task": {
            "id": str(uuid.uuid4()),
            "contextId": context_id or str(uuid.uuid4()),
            "status": {"state": FAILED},
            "metadata": {
                "ai-bunker.error": (
                    f"this message carries {chars:,} characters and this gateway "
                    f"reads at most {ceiling:,}"
                ),
                "ai-bunker.characters": str(chars),
                "ai-bunker.ceiling": str(ceiling),
            },
        }
    }


def handle_message_send(
    body: dict[str, Any],
    rules: list[Rule],
    charter: Charter | None = None,
    *,
    mark_provenance: bool = True,
) -> dict[str, Any]:
    """The `message:send` operation.

    Two skills share one operation, which the specification allows: the skill
    is chosen by `metadata."ai-bunker.skill"`, defaulting to screening, since
    that is the one a peer reaches for without reading the card closely.
    """
    message = body.get("message") or {}
    meta = message.get("metadata") or {}
    skill = str(meta.get("ai-bunker.skill") or "screen-text")
    context_id = str(body.get("contextId") or message.get("contextId") or "")

    if skill == "charter":
        if charter is None:
            return {
                "task": {
                    "id": str(uuid.uuid4()),
                    "contextId": context_id or str(uuid.uuid4()),
                    "status": {"state": FAILED},
                    "metadata": {"ai-bunker.error": "no charter is loaded"},
                }
            }
        ref = str(meta.get("ai-bunker.page") or "").strip()
        text = read_page(charter, ref) if ref else build_index(charter)
        return task_response(Screened(text=text, violations=[]), context_id=context_id)

    screened = screen_message(message, rules, mark_provenance=mark_provenance)
    response = task_response(
        screened, context_id=context_id, skipped_parts=_unreadable_parts(message)
    )
    # The caller needs the violations themselves, not their names, to write the
    # same audit records the HTTP pipeline writes. Carried out of band, under a
    # key the caller pops, so the wire format stays exactly what the
    # specification describes.
    response["_violations"] = screened.violations
    return response
