"""Refuse a payment the user never authorised.

The threat
----------
An agent that can call a payment API can spend money, and the failure is not
theoretical mischief: it is a charge on someone's card, made by software that
misread a page. AP2 -- the Agent Payments Protocol -- answers this with
*mandates*: the user authorises on a **Trusted Surface**, which the protocol
defines as a secure, explicitly **non-agentic** interface, and the result is a
signed credential the agent then carries.

The security property follows from that word. The agent does not produce the
authorisation; it presents one produced somewhere it cannot reach. An agent
initiating a payment with no mandate is not doing AP2 badly, it is doing
something AP2 exists to prevent.

What this checks, and what it cannot
------------------------------------
It checks that a mandate is **present and shaped like one**. It does **not**
verify the signature, and must never be described as if it did: verification
needs the issuer's public keys, a trust list and a revocation check, none of
which a serving gateway has or should have. Saying "the mandate is valid"
would be a lie that someone would build on.

That limit is narrower than it sounds. The overwhelmingly common failure is
not a forged mandate -- forging one requires a key -- it is no mandate at all,
because the agent simply called the API. This catches that, and says plainly
what it leaves to a real verifier.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import cycle avoided at runtime
    from ai_bunker.rules import Rule

#: Tool names that move money. Matched on the whole name, case-insensitively,
#: so `createPayment` and `create_payment` are the same tool.
PAYMENT_TOOLS = re.compile(
    r"\b(?:create|make|submit|initiate|send|issue|authorize|authorise|capture|process)?"
    r"_?(?:payment|charge|transfer|payout|purchase|checkout|order|invoice|refund|"
    r"subscription|wire|remittance)s?\b",
    re.IGNORECASE,
)

#: Hosts whose APIs move money. A tool called `http_post` is not a payment
#: tool by name, and this is how it is caught anyway.
PAYMENT_HOSTS = re.compile(
    r"\b(?:api\.stripe\.com|api\.paypal\.com|api\.adyen\.com|api\.squareup\.com|"
    r"api\.braintreegateway\.com|api\.checkout\.com|api\.mollie\.com|"
    r"api\.razorpay\.com|api-m\.paypal\.com)\b",
    re.IGNORECASE,
)

#: Argument keys that carry a mandate, in AP2's vocabulary and the obvious
#: near-misses an implementation might use.
MANDATE_KEYS = (
    "payment_mandate",
    "paymentMandate",
    "checkout_mandate",
    "checkoutMandate",
    "intent_mandate",
    "intentMandate",
    "cart_mandate",
    "cartMandate",
    "mandate",
    "mandate_receipt",
    "mandateReceipt",
    "authorization",
    "verifiable_presentation",
    "verifiablePresentation",
)

#: A compact JWS: three base64url segments. A Mandate Receipt is one.
JWT = re.compile(r"^[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}$")


@dataclass
class Finding:
    """What a payment-moving tool call carries, and what it is missing."""

    tool: str = ""
    moves_money: bool = False
    mandate_key: str = ""
    shape: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.moves_money or not self.problems


def _find_mandate(arguments: Any, depth: int = 0) -> tuple[str, Any]:
    """The first mandate-looking value, at any reasonable nesting.

    Bounded depth: a tool call is JSON from a model, and walking an arbitrary
    structure on the enforcement path is how a guardrail becomes a stall.
    """
    if depth > 4 or not isinstance(arguments, dict):
        return "", None
    for key in MANDATE_KEYS:
        if key in arguments and arguments[key] not in (None, "", {}, []):
            return key, arguments[key]
    for value in arguments.values():
        if isinstance(value, dict):
            found_key, found = _find_mandate(value, depth + 1)
            if found_key:
                return found_key, found
    return "", None


def _shape_of(mandate: Any) -> tuple[str, list[str]]:
    """Classify a mandate's shape, and say what is wrong with it.

    Shape only. Nothing here is a signature check, and the vocabulary avoids
    the word `valid` for that reason.
    """
    problems: list[str] = []

    if isinstance(mandate, str):
        if JWT.match(mandate.strip()):
            return "jws", _jws_problems(mandate.strip())
        return "opaque", [
            "the mandate is a bare string that is not a compact JWS, so nothing "
            "about it can be checked"
        ]

    if isinstance(mandate, dict):
        has_proof = any(k in mandate for k in ("proof", "signature", "jws", "jwt"))
        if not has_proof:
            problems.append(
                "the mandate carries no proof, signature or jws field, so it is "
                "an unsigned assertion the agent could have written itself"
            )
        return "credential", problems

    return "unknown", ["the mandate is neither a string nor an object"]


def _jws_problems(token: str) -> list[str]:
    """Read a compact JWS payload for expiry. The signature is not checked."""
    problems: list[str] = []
    try:
        payload = token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, binascii.Error, UnicodeDecodeError, json.JSONDecodeError):
        return ["the mandate's payload is not readable JSON"]

    if not isinstance(claims, dict):
        return ["the mandate's payload is not a JSON object"]

    expiry = claims.get("exp")
    if isinstance(expiry, (int, float)) and expiry < time.time():
        problems.append(
            f"the mandate expired at {time.strftime('%Y-%m-%d %H:%M:%SZ', time.gmtime(expiry))}"
        )
    return problems


def inspect(tool_name: str, arguments: Any) -> Finding:
    """Does this tool call move money, and does it carry a mandate?"""
    blob = json.dumps(arguments) if not isinstance(arguments, str) else arguments
    moves = bool(PAYMENT_TOOLS.search(tool_name)) or bool(PAYMENT_HOSTS.search(blob))
    finding = Finding(tool=tool_name, moves_money=moves)
    if not moves:
        return finding

    parsed = arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except (ValueError, json.JSONDecodeError):
            parsed = {}

    key, mandate = _find_mandate(parsed)
    if not key:
        finding.problems.append(
            "no mandate of any kind is attached. Under AP2 the user authorises "
            "on a Trusted Surface the agent does not control, and the agent "
            "presents the result; a payment the agent authorised itself is the "
            "thing the protocol exists to prevent"
        )
        return finding

    finding.mandate_key = key
    finding.shape, problems = _shape_of(mandate)
    finding.problems += problems
    return finding


def refusal_message(finding: Finding) -> str:
    return (
        "This call moves money and will not be forwarded: "
        + "; ".join(finding.problems)
        + ". The gateway checks that a mandate is present and shaped like one. "
        "It does NOT verify the signature -- that needs the issuer's keys, a "
        "trust list and a revocation check, which a serving gateway does not "
        "have. Treat a pass here as 'a mandate was attached', never as 'the "
        "mandate is valid'."
    )


def as_rule(finding: Finding) -> Rule:
    """Express the refusal as a Rule, so nothing downstream needs a second path."""
    from ai_bunker.rules import Rule

    return Rule(
        id="payments.unauthorised",
        severity="BLOCKER",
        scope="command",
        description=refusal_message(finding),
        pattern=re.compile(r"(?!)"),  # never matches: decided in code
        redact=False,
        replacement="",
        source="payments.py",
    )
