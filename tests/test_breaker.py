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


def test_the_breaker_opens_at_the_threshold_and_not_before(breaker):
    assert breaker.record("s", refusals(1)) is None
    assert breaker.record("s", refusals(1)) is None
    trip = breaker.record("s", refusals(1))
    assert trip is not None
    assert trip.count == 3


def test_a_redaction_does_not_count(breaker):
    """Text arriving with a secret in it is the gateway working as intended on
    somebody else's file. Counting it would stop a session for reading a
    repository that merely contains credentials."""
    assert breaker.record("s", [{"outcome": "redacted", "rule_id": "global.x"}] * 20) is None
    assert breaker.state("s") is None


def test_a_withheld_tool_counts(breaker):
    """A declaration carrying an injection is somebody trying something, and
    three of those in five minutes is the signal this exists to act on."""
    assert breaker.record("s", [{"outcome": "withheld", "rule_id": "tool.x"}] * 3) is not None


def test_sessions_are_counted_separately(breaker):
    breaker.record("a", refusals(3))
    assert breaker.state("a") is not None
    assert breaker.state("b") is None


def test_the_window_slides(breaker, clock):
    """Two refusals now and one in ten minutes is not a loop."""
    breaker.record("s", refusals(2))
    clock.tick(61)
    assert breaker.record("s", refusals(1)) is None, "stale refusals were still counted"


def test_an_open_breaker_closes_on_its_own(breaker, clock):
    breaker.record("s", refusals(3))
    assert breaker.state("s") is not None
    clock.tick(61)
    assert breaker.state("s") is None, "the session never recovered"


def test_a_threshold_of_zero_disables_it():
    """A deployment's choice to make, and it has to actually work."""
    off = Breaker(threshold=0)
    assert not off.enabled
    assert off.record("s", refusals(50)) is None
    assert off.state("s") is None


def test_an_empty_session_identifier_is_never_counted(breaker):
    """Rather than lumping every unidentifiable request into one bucket and
    stopping all of them together."""
    assert breaker.record("", refusals(10)) is None


# ---------------------------------------------------------------------------
# What an open breaker does, and does not do.
# ---------------------------------------------------------------------------


def test_an_open_breaker_refuses_a_tool_call(shipped, breaker):
    for _ in range(3):
        apply_outbound(call("rm -rf ~"), rules=shipped, breaker=breaker, session="s")
    stopped = apply_outbound(call("ls -la"), rules=shipped, breaker=breaker, session="s")
    assert stopped.refusal is not None
    assert stopped.refusal.id == RULE_ID
    assert stopped.refusal.severity == "BLOCKER"


def test_a_stopped_session_can_still_talk(shipped, breaker):
    """The quarantine, not the kill. An answer carrying no tool call is a
    sentence to the user, and stopping that would throw away the explanation
    of what just happened."""
    breaker.record("s", refusals(3))
    prose = {"choices": [{"message": {"content": "I was stopped and here is why."}}]}
    passed = apply_outbound(prose, rules=shipped, breaker=breaker, session="s")
    assert passed.refusal is None
    assert passed.request is prose


def test_another_session_is_untouched(shipped, breaker):
    breaker.record("s", refusals(3))
    other = apply_outbound(call("ls -la"), rules=shipped, breaker=breaker, session="other")
    assert other.refusal is None


def test_the_refusal_is_recorded_as_a_decision(shipped, breaker):
    breaker.record("s", refusals(3))
    stopped = apply_outbound(call("ls"), rules=shipped, breaker=breaker, session="s")
    assert [(d.rule_id, d.outcome) for d in stopped.decisions] == [(RULE_ID, "refused")]


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


def test_the_header_wins_when_a_client_sends_one():
    """The only source that is a fact rather than an inference."""
    request = {"messages": [{"role": "user", "content": "fix the auth bug"}]}
    assert session_of(request, header="abc") != session_of(request)
    assert session_of(request, header="abc") == session_of({}, header="abc")


def test_the_same_conversation_keeps_its_identity_as_it_grows():
    """The inference that has to hold: a coding session's first turn is the
    task statement, and the breaker has to still recognise the session twenty
    turns later."""
    opening = {"role": "user", "content": "fix the authentication bug in gateway.py"}
    early = {"messages": [opening]}
    later = {
        "messages": [
            opening,
            {"role": "assistant", "content": "Looking."},
            {"role": "tool", "content": "..."},
            {"role": "user", "content": "try again"},
        ]
    }
    assert session_of(early) == session_of(later)


def test_whitespace_does_not_change_the_identity():
    a = {"messages": [{"role": "user", "content": "fix  the\n bug"}]}
    b = {"messages": [{"role": "user", "content": "fix the bug"}]}
    assert session_of(a) == session_of(b)


def test_different_conversations_get_different_identities():
    a = {"messages": [{"role": "user", "content": "fix the auth bug"}]}
    b = {"messages": [{"role": "user", "content": "add a changelog entry"}]}
    assert session_of(a) != session_of(b)


def test_the_multipart_content_shape_is_read():
    """Some clients send content as a list of parts. Reading only the string
    shape would silently fall back to the credential for those clients, and
    one breaker shared by every session is not the design."""
    request = {
        "messages": [{"role": "user", "content": [{"type": "text", "text": "fix the auth bug"}]}]
    }
    assert session_of(request).startswith("c:")


def test_the_credential_is_the_last_resort():
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
