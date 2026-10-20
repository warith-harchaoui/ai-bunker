"""Stop a session that keeps asking for refused things.

The threat
----------
Every refusal this gateway issues says, in as many words, *this is a decision,
not a transient failure, do not retry it unchanged*. That sentence is the only
thing standing between a refused command and a loop, and it is a request. The
agent may comply. It may also retry the same command two hundred times, each
attempt paying for a full context window of prefill on a graphics processor
somebody owns.

The Day 4 whitepaper of Google's agents course names both ends of this. The
cheap end is **Denial of Wallet**: an adversary triggers expensive loops to
run up somebody's inference bill. Self-hosting does not make that harmless, it
changes the currency -- the loop burns the throughput of the one card the team
has. The expensive end is a probe: an agent under indirect injection trying
variation after variation until one gets past the rules. In both cases the
decision log already records every attempt, and nobody is reading it in real
time. The signal exists and nothing acts on it.

What this does
--------------
Counts refusals per session in a sliding window. Past a threshold the breaker
opens and **every tool call is refused**, with a message that says why and how
to clear it. The conversation itself keeps working.

That asymmetry is the design, and it is the paper's "stateful quarantine"
rather than its circuit breaker: killing the session would destroy the context
that explains what happened, and an agent terminated mid-turn leaves whatever
it was doing half-done. Freezing its ability to *act* while it keeps its
ability to *speak* means it can tell the user it has been stopped, and the
operator still has the transcript.

Honest limits, because an operator relying on this deserves them
----------------------------------------------------------------
**It is in-process and per-gateway.** State lives in memory. Restart the
gateway and every breaker is closed again. Run two gateways behind a load
balancer and each counts its own half. Fixing that means a shared store, which
means a dependency and a network hop on the enforcement path -- not worth it
for the deployment this project is for, and the limit is published rather than
discovered.

**Session identity is approximate.** An OpenAI-shaped request carries no
session id, so one is derived: the ``X-AI-Bunker-Session`` header if the client
sends one, otherwise a fingerprint of the first user turn, otherwise the
credential. The middle case is the usual one and it is a guess -- a good guess,
since a coding agent's first turn is the task statement and survives
compaction, but a guess. Two sessions that happen to start with the same
sentence share a breaker.

**It only sees what crosses the gateway.** An agent that runs a command
locally without asking is outside this boundary, as it is outside every other
control here.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import cycle avoided at runtime
    from ai_bunker.rules import Decision, Rule

#: Header a client can send to identify its own session, which is better than
#: anything this module can infer. Named like `X-AI-Bunker-Need`, which is the
#: convention the gateway already uses for things the client knows and the
#: server cannot.
SESSION_HEADER = "x-ai-bunker-session"

#: Refusals in the window before the breaker opens. Five is deliberately
#: generous: a legitimate session hits a BLOCKER rarely, and each refusal
#: already tells the agent not to retry. Five means the agent is either
#: looping or probing, and both are worth stopping.
DEFAULT_THRESHOLD = 5

#: Seconds the window spans, and how long an open breaker stays open. Short
#: enough that a stopped session recovers without an operator, long enough
#: that a loop cannot simply wait it out and continue at the same rate.
DEFAULT_WINDOW = 300

#: Outcomes that count against a session. A redaction does not: text arriving
#: with a secret in it is the gateway working as intended on somebody else's
#: file, and counting it would trip the breaker on a repository that merely
#: contains credentials.
COUNTED = ("refused", "withheld")

RULE_ID = "breaker.tripped"


@dataclass
class Trip:
    """An open breaker, and the evidence for it."""

    session: str
    count: int
    window: int
    opened_at: float
    rules: tuple[str, ...] = ()

    def remaining(self, now: float) -> int:
        """Seconds until it closes on its own."""
        return max(0, int(self.opened_at + self.window - now))


@dataclass
class Breaker:
    """Refusals per session, and the decision to stop.

    Parameters
    ----------
    threshold : int
        Refusals within the window before opening. Zero disables the breaker
        entirely, which is a deployment's choice to make.
    window : int
        Width of the sliding window, in seconds.
    """

    threshold: int = DEFAULT_THRESHOLD
    window: int = DEFAULT_WINDOW
    #: session -> timestamps of counted outcomes, oldest first.
    _seen: dict[str, deque[float]] = field(default_factory=dict, repr=False)
    #: session -> the rule ids that contributed, for the message.
    _why: dict[str, list[str]] = field(default_factory=dict, repr=False)
    _open: dict[str, Trip] = field(default_factory=dict, repr=False)

    @property
    def enabled(self) -> bool:
        return self.threshold > 0

    def _clock(self) -> float:
        """Monotonic on purpose: a breaker must not be reopened or extended by
        the system clock stepping backwards over a leap second or an update."""
        return time.monotonic()

    def record(self, session: str, decisions: list[Decision] | list[dict[str, Any]]) -> Trip | None:
        """Count what a turn refused, and open the breaker if it is time.

        Accepts either ``Decision`` objects or the dictionaries the audit log
        stores, because both callers exist and neither should have to convert.
        """
        if not self.enabled or not session:
            return None
        now = self._clock()
        counted = []
        for decision in decisions:
            outcome = (
                decision.get("outcome")
                if isinstance(decision, dict)
                else getattr(decision, "outcome", None)
            )
            if outcome in COUNTED:
                identifier = (
                    decision.get("rule_id")
                    if isinstance(decision, dict)
                    else getattr(decision, "rule_id", "")
                )
                counted.append(identifier or "")
        if not counted:
            return self.state(session)

        seen = self._seen.setdefault(session, deque())
        why = self._why.setdefault(session, [])
        for identifier in counted:
            seen.append(now)
            why.append(identifier)
        self._prune(session, now)

        if len(seen) >= self.threshold and session not in self._open:
            # Deduplicated and ordered so the message reads as a finding
            # rather than as a tally of the same rule five times.
            contributing = tuple(dict.fromkeys(w for w in why if w))
            self._open[session] = Trip(
                session=session,
                count=len(seen),
                window=self.window,
                opened_at=now,
                rules=contributing,
            )
        return self.state(session)

    def _prune(self, session: str, now: float) -> None:
        seen = self._seen.get(session)
        if not seen:
            return
        cutoff = now - self.window
        dropped = 0
        while seen and seen[0] < cutoff:
            seen.popleft()
            dropped += 1
        if dropped:
            del self._why.setdefault(session, [])[:dropped]

    def state(self, session: str) -> Trip | None:
        """The open breaker for a session, or None.

        Closing is lazy: an expired breaker is cleared when somebody asks,
        rather than by a timer. A background task would have to be owned,
        shut down and tested, to do nothing a read cannot do.
        """
        if not self.enabled or not session:
            return None
        trip = self._open.get(session)
        if trip is None:
            return None
        now = self._clock()
        if trip.remaining(now) <= 0:
            del self._open[session]
            self._seen.pop(session, None)
            self._why.pop(session, None)
            return None
        return trip

    def reset(self, session: str | None = None) -> int:
        """Close one breaker, or all of them. Returns how many were open."""
        if session is None:
            closed = len(self._open)
            self._open.clear()
            self._seen.clear()
            self._why.clear()
            return closed
        closed = 1 if self._open.pop(session, None) else 0
        self._seen.pop(session, None)
        self._why.pop(session, None)
        return closed

    def status(self) -> list[dict[str, Any]]:
        """Every open breaker, for the operator's dashboard."""
        now = self._clock()
        return [
            {
                "session": trip.session,
                "refusals": trip.count,
                "rules": list(trip.rules),
                "closes_in_s": trip.remaining(now),
            }
            for trip in list(self._open.values())
            if trip.remaining(now) > 0
        ]


# ---------------------------------------------------------------------------
# Session identity
# ---------------------------------------------------------------------------

_WHITESPACE = re.compile(r"\s+")


def _first_user_turn(request: dict[str, Any]) -> str:
    for message in request.get("messages") or []:
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
            if isinstance(content, list):
                # The multipart shape: take the text parts, in order.
                parts = [
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and isinstance(p.get("text"), str)
                ]
                joined = " ".join(parts).strip()
                if joined:
                    return joined
    return ""


def session_of(
    request: dict[str, Any],
    *,
    header: str = "",
    credential: str = "",
) -> str:
    """A stable identifier for the conversation this request belongs to.

    Three sources, best first. The header is the only one that is a fact; the
    other two are inferences, and the docstring of this module says so.

    The first user turn is hashed rather than stored, because it is the user's
    own prose and this identifier ends up in logs and in the dashboard. The
    credential is hashed for the same reason, with more force.
    """
    if header.strip():
        return "h:" + hashlib.sha256(header.strip().encode("utf-8")).hexdigest()[:16]
    opening = _first_user_turn(request)
    if opening:
        normalised = _WHITESPACE.sub(" ", opening).strip()[:512]
        return "c:" + hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:16]
    if credential:
        return "k:" + hashlib.sha256(credential.encode("utf-8")).hexdigest()[:16]
    return ""


# ---------------------------------------------------------------------------
# Expressed as a rule, so nothing downstream needs to know
# ---------------------------------------------------------------------------


def as_rule(trip: Trip, *, now: float | None = None) -> Rule:
    """Express an open breaker as the rule that refuses a command."""
    from ai_bunker.rules import Rule

    seconds = trip.remaining(time.monotonic() if now is None else now)
    because = ", ".join(trip.rules[:3]) if trip.rules else "repeated refusals"
    if len(trip.rules) > 3:
        because += f", and {len(trip.rules) - 3} other rule(s)"
    return Rule(
        id=RULE_ID,
        severity="BLOCKER",
        scope="command",
        description=(
            f"This session has had {trip.count} action(s) refused within "
            f"{trip.window}s ({because}), so tool calls are now stopped for "
            f"{seconds}s. Refusals are decisions and retrying them costs a full "
            f"context window each time. The conversation is still working: say what "
            f"you were trying to do and what was refused, and let the user decide. "
            f"An operator can clear this with `ai-bunker breaker --reset`."
        ),
        pattern=re.compile(r"(?!)"),  # never matches: decided in code
        redact=False,
        replacement="",
        source="breaker.py",
    )
