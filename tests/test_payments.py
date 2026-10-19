"""Refusing a payment the user never authorised.

AP2 defines the Trusted Surface as a secure, explicitly **non-agentic**
interface: the user authorises there, and the agent presents the result. An
agent that initiates a payment with no mandate is not doing AP2 badly -- it is
doing the thing AP2 exists to prevent.

What these tests hold the implementation to, above all, is honesty about its
own limit. The gateway checks that a mandate is present and shaped like one.
It does not verify signatures, and nothing in the code or the message it
returns may suggest otherwise.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import base64
import json
import time

import pytest

from ai_bunker.payments import Finding, as_rule, inspect, refusal_message


def _jws(**claims) -> str:
    """A compact JWS with a readable payload. The signature is nonsense, which
    is the point: nothing here verifies it."""
    header = base64.urlsafe_b64encode(b'{"alg":"ES256"}').decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"{header}.{payload}.c2lnbmF0dXJlLW5vdC1jaGVja2Vk"


# ---------------------------------------------------------------------------
# What counts as moving money.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool",
    [
        "create_payment",
        "createPayment",
        "submit_order",
        "charge",
        "transfer",
        "initiate_payout",
        "process_refund",
        "checkout",
    ],
)
def test_a_payment_tool_is_recognised_by_name(tool):
    assert inspect(tool, {"amount": 100}).moves_money


def test_a_generic_http_tool_pointed_at_a_processor_is_recognised():
    """A tool called `http_post` is not a payment tool by name. It is still
    the way most agents would actually charge a card."""
    finding = inspect("http_post", {"url": "https://api.stripe.com/v1/charges"})
    assert finding.moves_money


@pytest.mark.parametrize(
    "tool, args",
    [
        ("read_file", {"path": "README.md"}),
        ("bash", {"command": "ls -la"}),
        ("search", {"query": "how to charge a battery"}),
        ("http_post", {"url": "https://api.github.com/repos/x/y/issues"}),
    ],
)
def test_ordinary_calls_are_left_alone(tool, args):
    finding = inspect(tool, args)
    assert not finding.moves_money and finding.ok


# ---------------------------------------------------------------------------
# The mandate.
# ---------------------------------------------------------------------------


def test_a_payment_with_no_mandate_is_refused():
    finding = inspect("create_payment", {"amount": 4200, "currency": "EUR"})
    assert not finding.ok
    assert "no mandate" in finding.problems[0]


def test_a_payment_with_a_live_mandate_passes():
    finding = inspect(
        "create_payment",
        {"amount": 4200, "payment_mandate": _jws(exp=time.time() + 3600)},
    )
    assert finding.ok and finding.shape == "jws"


def test_an_expired_mandate_is_refused():
    finding = inspect(
        "create_payment", {"amount": 4200, "payment_mandate": _jws(exp=time.time() - 60)}
    )
    assert not finding.ok
    assert "expired" in finding.problems[0]


def test_an_unsigned_assertion_is_not_a_mandate():
    """Without a proof it is a JSON object the agent could have written
    itself, which is exactly the authorisation AP2 does not accept."""
    finding = inspect("create_payment", {"amount": 10, "mandate": {"intent": "buy a thing"}})
    assert not finding.ok
    assert "no proof" in finding.problems[0]


def test_a_signed_credential_object_passes():
    finding = inspect(
        "create_payment",
        {"amount": 10, "cart_mandate": {"intent": "buy", "proof": {"type": "DataIntegrityProof"}}},
    )
    assert finding.ok and finding.shape == "credential"


def test_a_bare_string_that_is_not_a_jws_is_refused():
    finding = inspect("create_payment", {"amount": 10, "mandate": "approved-by-the-user"})
    assert not finding.ok


@pytest.mark.parametrize(
    "key", ["payment_mandate", "checkoutMandate", "intent_mandate", "mandate_receipt"]
)
def test_the_vocabulary_ap2_actually_uses_is_accepted(key):
    assert inspect("create_payment", {key: _jws(exp=time.time() + 60)}).ok


def test_a_nested_mandate_is_found():
    """Agents nest. A mandate one level down is still attached."""
    finding = inspect(
        "create_payment",
        {"body": {"payment": {"payment_mandate": _jws(exp=time.time() + 60)}}},
    )
    assert finding.ok


def test_arguments_arrive_as_a_json_string_too():
    """OpenAI tool calls carry `arguments` as a string, not an object."""
    args = json.dumps({"amount": 10, "payment_mandate": _jws(exp=time.time() + 60)})
    assert inspect("create_payment", args).ok


def test_walking_arguments_is_depth_bounded():
    """A guardrail that walks an arbitrary structure on the enforcement path
    is a guardrail that becomes a stall."""
    deep: dict = {"payment_mandate": _jws(exp=time.time() + 60)}
    for _ in range(12):
        deep = {"nested": deep}
    finding = inspect("create_payment", deep)
    assert not finding.ok, "a mandate buried twelve levels down should not count as attached"


# ---------------------------------------------------------------------------
# Honesty about the limit. This is the part that matters most.
# ---------------------------------------------------------------------------


def test_the_message_refuses_to_claim_the_mandate_is_valid():
    """Verification needs the issuer's keys, a trust list and a revocation
    check. Saying `valid` would be a lie somebody builds on."""
    message = refusal_message(inspect("create_payment", {"amount": 1}))
    assert "does NOT verify the signature" in message
    assert "never as 'the mandate is valid'" in message


def test_a_forged_signature_passes_and_that_is_stated():
    """Nothing here checks a signature, so a mandate with a garbage signature
    is accepted. The test exists so the limit is recorded rather than
    discovered."""
    finding = inspect("create_payment", {"payment_mandate": _jws(exp=time.time() + 60)})
    assert finding.ok, "shape-only checking accepts an unverifiable signature, by design"


def test_the_rule_carries_the_caveat_into_the_audit_log():
    rule = as_rule(inspect("create_payment", {"amount": 1}))
    assert rule.id == "payments.unauthorised"
    assert rule.severity == "BLOCKER"
    assert "does NOT verify" in rule.description
    assert not rule.pattern.search("create_payment")


# ---------------------------------------------------------------------------
# Through the pipeline.
# ---------------------------------------------------------------------------


def _call(name: str, arguments: dict) -> list[dict]:
    return [
        {
            "id": "c1",
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }
    ]


def test_stage_four_refuses_an_unauthorised_payment():
    from ai_bunker.adopt import ROOT
    from ai_bunker.pipeline import screen_outbound
    from ai_bunker.rules import load_rules

    rules = load_rules(ROOT / "charter" / "rules")
    refusal, _c, _n = screen_outbound(_call("create_payment", {"amount": 4200}), rules)
    assert refusal is not None and refusal.id == "payments.unauthorised"


def test_payments_are_screened_outside_the_shell_tools():
    """A payment never arrives as a shell command, so restricting this to
    SHELL_TOOLS would check the one place it does not happen."""
    from ai_bunker.adopt import ROOT
    from ai_bunker.pipeline import SHELL_TOOLS, screen_outbound
    from ai_bunker.rules import load_rules

    assert "create_payment" not in SHELL_TOOLS
    rules = load_rules(ROOT / "charter" / "rules")
    refusal, _c, _n = screen_outbound(_call("create_payment", {"amount": 1}), rules)
    assert refusal is not None


def test_the_check_can_be_turned_off():
    from ai_bunker.adopt import ROOT
    from ai_bunker.pipeline import screen_outbound
    from ai_bunker.rules import load_rules

    rules = load_rules(ROOT / "charter" / "rules")
    refusal, _c, _n = screen_outbound(
        _call("create_payment", {"amount": 1}), rules, check_payments=False
    )
    assert refusal is None


def test_an_authorised_payment_is_forwarded():
    from ai_bunker.adopt import ROOT
    from ai_bunker.pipeline import screen_outbound
    from ai_bunker.rules import load_rules

    rules = load_rules(ROOT / "charter" / "rules")
    refusal, _c, _n = screen_outbound(
        _call("create_payment", {"amount": 1, "payment_mandate": _jws(exp=time.time() + 60)}),
        rules,
    )
    assert refusal is None


def test_a_finding_on_a_non_payment_is_vacuously_ok():
    assert Finding(tool="read_file", moves_money=False).ok
