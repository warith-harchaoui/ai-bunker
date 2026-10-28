"""
Tests for the circuit breaker.

The behaviour that matters is asymmetric and easy to get backwards: an open
breaker stops the session's ability to **act** and leaves its ability to
**speak** intact. Several tests below exist only to pin that down, because the
obvious implementation -- refuse the request -- destroys the context that
explains what happened and leaves the agent's work half-done.

Time is injected rather than slept through. A test suite that waits out a
300-second window is a test suite people stop running.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import json

import pytest

from ai_bunker.adopt import ROOT
from ai_bunker.breaker import (
    DEFAULT_THRESHOLD,
    DEFAULT_WINDOW,
    RULE_ID,
    Breaker,
    as_rule,
    session_of,
)
from ai_bunker.pipeline import apply_outbound
from ai_bunker.rules import load_rules


@pytest.fixture(scope="module")
def shipped():
    return load_rules(ROOT / "charter" / "rules")


@pytest.fixture
def clock():
    """A clock the test moves on purpose."""

    class Clock:
        now = 1_000.0

        def tick(self, seconds: float) -> None:
            self.now += seconds

    return Clock()


@pytest.fixture
def breaker(clock):
    b = Breaker(threshold=3, window=60)
    b._clock = lambda: clock.now  # type: ignore[method-assign]
    return b


def refusals(count: int, rule: str = "shell.destructive_rm") -> list[dict]:
    return [{"outcome": "refused", "rule_id": rule} for _ in range(count)]


def call(command: str) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "bash",
                                "arguments": json.dumps({"command": command}),
                            }
                        }
                    ]
                }
            }
        ]
    }


# ---------------------------------------------------------------------------
# Opening.
# ---------------------------------------------------------------------------


def test_the_breaker_opens_at_the_threshold_on_the_outcomes_that_mean_intent(breaker):
    """What counts is the whole design, and it is narrower than it looks.

    A **redaction** does not count: text arriving with a secret in it is the
    gateway working as intended on somebody else's file, and counting it would
    stop a session for reading a repository that merely contains credentials.
    A **withheld tool** does: a declaration carrying an injection is somebody
    trying something, and three of those inside the window is exactly the
    signal this exists to act on. The count is per session, so one agent in a
    loop never stops another.
    """
    assert breaker.record("s", refusals(1)) is None
    assert breaker.record("s", refusals(1)) is None
    trip = breaker.record("s", refusals(1))
    assert trip is not None and trip.count == 3

    assert breaker.record("quiet", [{"outcome": "redacted", "rule_id": "global.x"}] * 20) is None
    assert breaker.state("quiet") is None
    assert breaker.record("tried", [{"outcome": "withheld", "rule_id": "tool.x"}] * 3) is not None

    assert breaker.state("s") is not None
    assert breaker.state("untouched") is None, "sessions are counted separately"


def test_the_window_slides_so_a_session_recovers_on_its_own(breaker, clock):
    """Two refusals now and one in ten minutes is not a loop, and a session
    that was stopped has to become workable again without an operator -- the
    breaker is a quarantine with a timer, not a ban list."""
    breaker.record("s", refusals(2))
    clock.tick(61)
    assert breaker.record("s", refusals(1)) is None, "stale refusals were still counted"

    breaker.record("s", refusals(3))
    assert breaker.state("s") is not None
    clock.tick(61)
    assert breaker.state("s") is None, "the session never recovered"


def test_the_breaker_declines_to_count_what_it_cannot_attribute(breaker):
    """Two ways not to act, both deliberate. A threshold of zero is a
    deployment's choice and has to actually disable it. An unidentifiable
    request is not counted at all, rather than lumped with every other one
    into a single bucket that stops all of them together.
    """
    off = Breaker(threshold=0)
    assert not off.enabled
    assert off.record("s", refusals(50)) is None
    assert off.state("s") is None

    assert breaker.record("", refusals(10)) is None


# ---------------------------------------------------------------------------
# What an open breaker does, and does not do.
# ---------------------------------------------------------------------------


def test_an_open_breaker_quarantines_the_session_rather_than_killing_it(shipped, breaker):
    """The distinction this module is built on.

    A tool call from a stopped session is refused, as a BLOCKER, recorded as a
    decision like any other refusal. But an answer carrying no tool call is a
    sentence to the user -- very likely the explanation of what just happened
    -- and stopping that would throw the explanation away. And another session
    is untouched, because the loop belongs to one conversation.
    """
    for _ in range(3):
        apply_outbound(call("rm -rf ~"), rules=shipped, breaker=breaker, session="s")

    stopped = apply_outbound(call("ls -la"), rules=shipped, breaker=breaker, session="s")
    assert stopped.refusal is not None
    assert stopped.refusal.id == RULE_ID
    assert stopped.refusal.severity == "BLOCKER"
    assert [(d.rule_id, d.outcome) for d in stopped.decisions] == [(RULE_ID, "refused")]

    prose = {"choices": [{"message": {"content": "I was stopped and here is why."}}]}
    passed = apply_outbound(prose, rules=shipped, breaker=breaker, session="s")
    assert passed.refusal is None
    assert passed.request is prose

    other = apply_outbound(call("ls -la"), rules=shipped, breaker=breaker, session="other")
    assert other.refusal is None


def test_this_turn_s_refusal_is_part_of_the_evidence(shipped, breaker):
    """Counted after screening, so the third refusal opens the breaker rather
    than the fourth. Off by one here means a session gets one more free loop
    than the operator configured."""
    for index in range(1, 4):
        result = apply_outbound(call("rm -rf ~"), rules=shipped, breaker=breaker, session="s")
        assert result.refusal is not None
        assert result.refusal.id == "shell.destructive_rm", f"turn {index}"
    assert breaker.state("s") is not None


def test_no_breaker_means_no_change(shipped):
    """The parameter is optional, and a deployment that passes nothing must
    behave exactly as it did before this module existed."""
    allowed = apply_outbound(call("ls -la"), rules=shipped)
    assert allowed.refusal is None
    refused = apply_outbound(call("rm -rf ~"), rules=shipped)
    assert refused.refusal is not None and refused.refusal.id == "shell.destructive_rm"


# ---------------------------------------------------------------------------
# What the agent and the operator are told.
# ---------------------------------------------------------------------------


def test_the_refusal_says_why_and_how_to_clear_it(breaker, clock):
    trip = breaker.record("s", refusals(3, rule="shell.pipe_to_shell"))
    rule = as_rule(trip, now=clock.now)
    assert "shell.pipe_to_shell" in rule.description
    assert "ai-bunker breaker --reset" in rule.description
    assert "conversation is still working" in rule.description
    assert rule.source == "breaker.py"
    assert not rule.pattern.search("anything"), "the pattern must never match"


def test_the_contributing_rules_are_deduplicated(breaker, clock):
    """Five of the same refusal is one finding, not a tally."""
    trip = breaker.record("s", refusals(5, rule="shell.destructive_rm"))
    assert as_rule(trip, now=clock.now).description.count("shell.destructive_rm") == 1


def test_the_status_is_readable_by_an_operator(breaker):
    breaker.record("s", refusals(3))
    status = breaker.status()
    assert len(status) == 1
    assert status[0]["refusals"] == 3
    assert status[0]["closes_in_s"] > 0
    assert "shell.destructive_rm" in status[0]["rules"]


def test_a_reset_closes_one_session_or_all(breaker):
    breaker.record("a", refusals(3))
    breaker.record("b", refusals(3))
    assert breaker.reset("a") == 1
    assert breaker.state("a") is None and breaker.state("b") is not None
    assert breaker.reset() == 1
    assert breaker.status() == []


# ---------------------------------------------------------------------------
# Session identity, which is the approximate part.
# ---------------------------------------------------------------------------


def test_a_session_is_identified_by_the_best_evidence_available(shipped):
    """The approximate part of this module, and the order is the design.

    A **header** is the only source that is a fact rather than an inference,
    so it wins outright. Failing that, the **opening turn** is inferred from:
    a coding session starts with a task statement, and the breaker has to
    still recognise the session twenty turns later -- so growth and whitespace
    must not change the identity, while a different task must. The content is
    read in both shapes clients send it, because reading only the string one
    would silently fall back to the credential for every client that sends
    parts, and one breaker shared by every session is not the design. The
    **credential** is the last resort, and with nothing at all there is no
    session rather than a shared one.
    """
    task = {"role": "user", "content": "fix the authentication bug in gateway.py"}
    opening = {"messages": [task]}

    assert session_of(opening, header="abc") != session_of(opening)
    assert session_of(opening, header="abc") == session_of({}, header="abc")

    twenty_turns_in = {
        "messages": [
            task,
            {"role": "assistant", "content": "Looking."},
            {"role": "tool", "content": "..."},
            {"role": "user", "content": "try again"},
        ]
    }
    assert session_of(opening) == session_of(twenty_turns_in)

    spaced = {"messages": [{"role": "user", "content": "fix  the\n bug"}]}
    tidy = {"messages": [{"role": "user", "content": "fix the bug"}]}
    assert session_of(spaced) == session_of(tidy)
    assert session_of(tidy) != session_of(
        {"messages": [{"role": "user", "content": "add a changelog entry"}]}
    )

    parts = {"messages": [{"role": "user", "content": [{"type": "text", "text": "fix it"}]}]}
    assert session_of(parts).startswith("c:")

    assert session_of({}, credential="key").startswith("k:")
    assert session_of({}) == "", "with nothing to go on, there is no session"


def test_the_identifier_never_contains_the_user_s_own_words():
    """It ends up in logs and on a dashboard."""
    secret = "migrate the database at postgres://user:hunter2@prod/db"
    identifier = session_of({"messages": [{"role": "user", "content": secret}]})
    assert "hunter2" not in identifier
    assert "postgres" not in identifier


def test_the_shipped_defaults_are_the_documented_ones():
    """These two numbers are published in the README, so they are asserted
    here rather than left to drift."""
    assert (DEFAULT_THRESHOLD, DEFAULT_WINDOW) == (5, 300)


# ---------------------------------------------------------------------------
# The second day. Nothing in this repository had ever run longer than a test,
# so nothing had asked what a week of sessions costs.
# ---------------------------------------------------------------------------


def _refusal() -> list:
    from ai_bunker.rules import Decision

    return [
        Decision(
            rule_id="shell.destructive_rm",
            severity="BLOCKER",
            scope="command",
            outcome="refused",
            count=1,
        )
    ]


def test_session_history_is_bounded():
    """`_prune` dropped the events in a session older than the window and
    never dropped the session itself.

    Measured before the cap: **1,003 bytes per session, 201 MB across 200,000
    conversations**, held for the gateway's lifetime. Session identity is
    inferred from the request rather than given, so a busy deployment reaches
    those numbers without anybody doing anything unusual.
    """
    breaker = Breaker(threshold=3, window=600)
    breaker.limit = 64
    for i in range(5_000):
        breaker.record(f"session-{i}", _refusal())

    assert len(breaker._seen) <= breaker.limit
    assert len(breaker._why) <= breaker.limit


def test_a_stopped_session_is_never_evicted():
    """The one thing eviction must not do.

    A cap on memory that closed an open breaker would be a way to be
    re-admitted after being deliberately stopped: flood the gateway with
    sessions until yours is forgotten. Tested with two hundred sessions of
    pressure against a cap of eight.
    """
    breaker = Breaker(threshold=3, window=600)
    breaker.limit = 8

    for _ in range(3):
        breaker.record("victim", _refusal())
    assert breaker.state("victim") is not None, "the fixture needs a tripped session"

    for i in range(200):
        breaker.record(f"noise-{i}", _refusal())

    assert breaker.state("victim") is not None, "a stopped session was re-admitted"
    assert len(breaker._seen) <= breaker.limit


def test_the_breaker_still_trips_under_eviction_pressure():
    """A cap that quietly stopped the breaker working would trade a memory
    leak for a missing control."""
    breaker = Breaker(threshold=3, window=600)
    breaker.limit = 8
    for i in range(100):
        breaker.record(f"noise-{i}", _refusal())

    for _ in range(3):
        breaker.record("fresh", _refusal())
    assert breaker.state("fresh") is not None


def test_eviction_takes_the_oldest_first():
    """Oldest-first is what makes eviction nearly free: the session being
    dropped has not been seen in a long time, so its refusals are already
    outside the window and `_prune` would have discarded them anyway."""
    breaker = Breaker(threshold=99, window=600)
    breaker.limit = 3
    for name in ("first", "second", "third"):
        breaker.record(name, _refusal())
    breaker.record("fourth", _refusal())

    assert "first" not in breaker._seen
    assert "fourth" in breaker._seen
