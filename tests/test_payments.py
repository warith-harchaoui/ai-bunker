"""Refusing a payment that is not the one the user authorised.

Three things have to hold before a payment is forwarded: a mandate is
attached, its signature verifies against a key this deployment trusts, and
what it authorises matches what is being charged. The third is the one a
presence check misses and an attacker uses -- a mandate signed for 42 EUR at
one merchant is genuine, unexpired, and wrong on a 4,200 EUR charge elsewhere.

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
from ai_bunker.ucp import cart_digest


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


@pytest.fixture(scope="module")
def signer(tmp_path_factory):
    """A real key, a real JWKS on disk, and a function that really signs.

    Sovereign by construction: the key set is a file, which is the intended
    deployment -- a gateway that must not reach the internet before it can
    refuse a payment.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils

    from ai_bunker.mandates import load_trust

    key = ec.generate_private_key(ec.SECP256R1())
    numbers = key.public_key().public_numbers()
    directory = tmp_path_factory.mktemp("trust")
    jwks = directory / "jwks.json"
    jwks.write_text(
        json.dumps(
            {
                "keys": [
                    {
                        "kty": "EC",
                        "crv": "P-256",
                        "kid": "k1",
                        "x": _b64(numbers.x.to_bytes(32, "big")),
                        "y": _b64(numbers.y.to_bytes(32, "big")),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (directory / "revoked.txt").write_text("revoked-mandate\n", encoding="utf-8")

    def sign(**claims) -> str:
        header = _b64(json.dumps({"alg": "ES256", "kid": "k1"}).encode())
        payload = _b64(json.dumps(claims).encode())
        der = key.sign(f"{header}.{payload}".encode(), ec.ECDSA(hashes.SHA256()))
        r, s = utils.decode_dss_signature(der)
        return f"{header}.{payload}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"

    trust = load_trust(
        str(jwks),
        issuers=("https://wallet.example",),
        revoked_file=str(directory / "revoked.txt"),
    )
    return sign, trust


def _authorised(**over):
    base = {
        "iss": "https://wallet.example",
        "exp": time.time() + 600,
        "amount": "42.00",
        "currency": "EUR",
        "payee": "Acme",
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# What counts as moving money.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool, args, moves_money",
    [
        # By name, in the spellings an agent framework actually emits.
        ("create_payment", {"amount": 100}, True),
        ("createPayment", {"amount": 100}, True),
        ("submit_order", {"amount": 100}, True),
        ("charge", {"amount": 100}, True),
        ("transfer", {"amount": 100}, True),
        ("initiate_payout", {"amount": 100}, True),
        ("process_refund", {"amount": 100}, True),
        ("checkout", {"amount": 100}, True),
        # And by destination. A tool called `http_post` is not a payment tool
        # by name; it is still how most agents would actually charge a card.
        ("http_post", {"url": "https://api.stripe.com/v1/charges"}, True),
        # Beside them, the ordinary work that must stay ordinary -- including
        # the same generic tool pointed somewhere that takes no money, and a
        # search whose words would fool a keyword match.
        ("read_file", {"path": "README.md"}, False),
        ("bash", {"command": "ls -la"}, False),
        ("search", {"query": "how to charge a battery"}, False),
        ("http_post", {"url": "https://api.github.com/repos/x/y/issues"}, False),
    ],
)
def test_what_counts_as_moving_money_and_what_does_not(tool, args, moves_money):
    """The two halves in one table, because the second is what keeps the first
    deployable: a check that fires on `search` for the word "charge" is a
    check an operator turns off within the hour."""
    finding = inspect(tool, args)
    assert finding.moves_money is moves_money
    if not moves_money:
        assert finding.ok


# ---------------------------------------------------------------------------
# A mandate has to be there at all.
# ---------------------------------------------------------------------------


def test_a_payment_without_a_real_mandate_is_refused(signer):
    """Three ways to arrive with nothing, and each gets the same answer.

    **No mandate at all** is the common case and the reason the check exists.
    An **unsigned assertion** is worse than nothing: without a proof it is a
    JSON object the agent could have written itself, which is precisely the
    authorisation AP2 does not accept. And a **bare string** that is not a JWS
    is a claim shaped like a credential, which is how an agent would bluff.
    """
    _sign, trust = signer

    absent = inspect("create_payment", {"amount": 4200, "currency": "EUR"}, trust)
    assert not absent.ok and "no mandate" in absent.problems[0]

    unsigned = inspect("create_payment", {"amount": 10, "mandate": {"intent": "buy"}}, trust)
    assert not unsigned.ok and "no proof" in unsigned.problems[0]

    assert not inspect("create_payment", {"mandate": "approved-by-the-user"}, trust).ok


# ---------------------------------------------------------------------------
# The signature, now actually checked.
# ---------------------------------------------------------------------------


def _charge(sign, trust, **over):
    """Run the whole check over a charge of 42 EUR to Acme."""
    claims = _authorised(**over)
    return inspect(
        "create_payment",
        {
            "amount": claims["amount"],
            "currency": claims["currency"],
            "payee": claims["payee"],
            "payment_mandate": sign(**claims),
        },
        trust,
    )


def test_a_signed_mandate_passes_and_every_way_of_faking_one_does_not(signer):
    """The presence check this replaced let any string through, so each of
    these is a forgery that used to work.

    The **payload** cannot be swapped under a valid signature. The
    **algorithm** cannot be chosen by the token -- `alg: none` selecting a
    path that skips verification is the classic JWT forgery, and it is refused
    both at the verifier and through the whole check. The **issuer** has to be
    one this deployment lets authorise payments, which is not the same as one
    whose key we hold. And a mandate that was genuine stops counting once it
    is **revoked** or **expired**.
    """
    sign, trust = signer

    good = _charge(sign, trust)
    assert good.ok and good.verified
    assert good.issuer == "https://wallet.example"

    token = sign(**_authorised())
    header, _payload, signature = token.split(".")
    forged = _b64(json.dumps(_authorised(amount="99999.00")).encode())
    tampered = inspect(
        "create_payment",
        {
            "amount": "99999.00",
            "currency": "EUR",
            "payee": "Acme",
            "payment_mandate": f"{header}.{forged}.{signature}",
        },
        trust,
    )
    assert not tampered.ok and not tampered.verified
    assert any("not valid" in p for p in tampered.problems)

    from ai_bunker.mandates import verify

    none_header = _b64(json.dumps({"alg": "none"}).encode())
    none_token = f"{none_header}.{_b64(json.dumps(_authorised()).encode())}.AAAA"
    verdict = verify(none_token, trust)
    assert not verdict.verified and any("not accepted" in p for p in verdict.problems)
    assert not inspect(
        "create_payment", {"amount": "42.00", "payment_mandate": none_token}, trust
    ).ok

    off_list = _charge(sign, trust, iss="https://elsewhere.example")
    assert not off_list.ok and any("issuer list" in p for p in off_list.problems)

    revoked = _charge(sign, trust, jti="revoked-mandate")
    assert not revoked.ok and any("revoked" in p for p in revoked.problems)

    expired = _charge(sign, trust, exp=time.time() - 600)
    assert not expired.ok and any("expired" in p for p in expired.problems)


def test_without_a_trust_a_mandate_is_refused_not_believed(signer):
    """The behaviour that changed. A mandate used to pass a shape check with
    its signature unexamined; now an unverifiable mandate is refused, and the
    refusal distinguishes "could not be attempted" from "failed"."""
    sign, _trust = signer
    finding = inspect(
        "create_payment", {"amount": "42.00", "payment_mandate": sign(**_authorised())}
    )
    assert not finding.ok and not finding.verified
    assert "NOT verified" in finding.problems[0]


# ---------------------------------------------------------------------------
# Signed for WHAT. The gap a presence check leaves open.
# ---------------------------------------------------------------------------


def test_a_valid_signature_only_authorises_the_charge_it_was_signed_for(signer):
    """The attack this whole module exists for, in its three shapes.

    In each one the mandate is genuine and the signature verifies -- the
    presence check this replaced would have waved all three through. What is
    checked is *what* was signed: a charge a hundred times the agreed amount,
    to a different payee, or in a different currency, is not the payment the
    user authorised however real the token is.

    Charging **less** is allowed, because a mandate is a ceiling rather than
    an instruction, and refusing a smaller charge would break every
    legitimate partial capture.
    """
    sign, trust = signer

    inflated = inspect(
        "create_payment",
        {
            "amount": "4200.00",
            "currency": "EUR",
            "payee": "Acme",
            "payment_mandate": sign(**_authorised()),
        },
        trust,
    )
    assert inflated.verified, "the signature really is valid"
    assert not inflated.ok, "and the payment is still not the authorised one"
    assert any("exceeds what was authorised" in p for p in inflated.problems)

    for field, value in (("payee", "Evil Ltd"), ("currency", "USD")):
        arguments = {
            "amount": "42.00",
            "currency": "EUR",
            "payee": "Acme",
            "payment_mandate": sign(**_authorised()),
        }
        arguments[field] = value
        substituted = inspect("create_payment", arguments, trust)
        assert substituted.verified and not substituted.ok, field

    partial = inspect(
        "create_payment",
        {
            "amount": "20.00",
            "currency": "EUR",
            "payee": "Acme",
            "payment_mandate": sign(**_authorised()),
        },
        trust,
    )
    assert partial.ok, "a mandate is a ceiling, not an instruction"


def test_a_mandate_that_constrains_nothing_is_refused(signer):
    """An authorisation that constrains nothing authorises everything, which
    is worth saying out loud rather than treating as agreement."""
    sign, trust = signer
    finding = inspect(
        "create_payment",
        {
            "amount": "4200.00",
            "currency": "EUR",
            "payment_mandate": sign(iss="https://wallet.example", exp=time.time() + 600),
        },
        trust,
    )
    assert not finding.ok and any("constrains nothing" in p for p in finding.problems)


def test_a_cart_digest_binds_fields_nobody_enumerated(signer):
    sign, trust = signer
    cart = {"items": [{"sku": "a", "qty": 2}], "amount": "42.00", "currency": "EUR"}
    good = dict(cart, payment_mandate=sign(**_authorised(cart_hash=cart_digest(cart))))
    assert inspect("create_payment", good, trust).ok

    tampered = dict(cart, qty=99)
    bad = dict(tampered, payment_mandate=sign(**_authorised(cart_hash=cart_digest(cart))))
    finding = inspect("create_payment", bad, trust)
    assert not finding.ok and any("does not match" in p for p in finding.problems)


def test_money_is_compared_as_integers_not_floats(signer):
    """0.1 + 0.2 is not 0.3. A comparison that passes because two totals round
    to the same float is a payment nobody authorised."""
    from ai_bunker.ucp import minor_units

    assert minor_units("42.00", "EUR") == 4200
    assert minor_units("0.30", "EUR") == 30
    assert minor_units(1000, "JPY") == 1000, "JPY has no minor unit"
    assert minor_units("4.20", "EUR") == 420


# ---------------------------------------------------------------------------
# Honesty about what is still not done.
# ---------------------------------------------------------------------------


def test_the_caveat_reaches_both_the_agent_and_the_audit_log(signer):
    """AP2 links a Payment Mandate to a Checkout Mandate to what the user
    actually saw. Verifying one link says nothing about the others, so the
    refusal says so rather than letting a reader assume otherwise -- and says
    it in both places it is read: the message the agent gets back, and the
    rule description the audit log keeps.

    The rule's pattern never matches on its own, because the decision is made
    in code and a pattern that could fire alone would be a second, weaker copy
    of it.
    """
    _sign, trust = signer
    finding = inspect("create_payment", {"amount": 1}, trust)

    message = refusal_message(finding)
    assert "CHAINS are not" in message
    assert "Trusted Surface" in message

    rule = as_rule(finding)
    assert rule.id == "payments.unauthorised" and rule.severity == "BLOCKER"
    assert "CHAINS are not" in rule.description
    assert not rule.pattern.search("create_payment")


# ---------------------------------------------------------------------------
# Shape handling that must not regress.
# ---------------------------------------------------------------------------


def test_a_mandate_is_found_in_every_shape_a_tool_call_carries_one(signer):
    """Where the mandate can be, and where the search has to stop.

    OpenAI tool calls carry `arguments` as a **JSON string**, not an object,
    so a check that only reads dictionaries would wave through every real
    request. A mandate **nested** inside a request body is found, because
    agents wrap payloads. But the walk is **depth bounded**: a guardrail that
    walks an arbitrary structure on the enforcement path is a guardrail that
    becomes a stall, so a mandate buried too deep is not found -- and not
    finding it is a refusal, which is the safe direction to be wrong in.

    A finding on something that never moved money is vacuously ok, which is
    what lets the pipeline call this on every tool call without branching.
    """
    sign, trust = signer

    as_string = json.dumps(
        {
            "amount": "42.00",
            "currency": "EUR",
            "payee": "Acme",
            "payment_mandate": sign(**_authorised()),
        }
    )
    assert inspect("create_payment", as_string, trust).ok

    nested = inspect(
        "create_payment",
        {
            "amount": "42.00",
            "currency": "EUR",
            "payee": "Acme",
            "body": {"payment": {"payment_mandate": sign(**_authorised())}},
        },
        trust,
    )
    assert nested.ok

    deep: dict = {"payment_mandate": sign(**_authorised())}
    for _ in range(12):
        deep = {"nested": deep}
    assert not inspect("create_payment", deep, trust).ok

    assert Finding(tool="read_file", moves_money=False).ok


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


def test_stage_four_refuses_an_unauthorised_payment_and_forwards_an_authorised_one(signer):
    """The check only matters where it runs, and four things have to hold
    there.

    An **unauthorised** charge is refused by `payments.unauthorised`, and an
    **authorised** one goes through -- a gate that refuses everything is
    indistinguishable from a broken endpoint. It runs **outside
    `SHELL_TOOLS`**, because a payment never arrives as a shell command and
    restricting it to those would check the one place this does not happen.
    And it can be **turned off**, like every other protection here: an
    operator who has their own authorisation layer should not have to route
    around this one.
    """
    from ai_bunker.adopt import ROOT
    from ai_bunker.pipeline import SHELL_TOOLS, screen_outbound
    from ai_bunker.rules import load_rules

    sign, trust = signer
    rules = load_rules(ROOT / "charter" / "rules")

    refused, _c, _n = screen_outbound(_call("create_payment", {"amount": 4200}), rules, trust=trust)
    assert refused is not None and refused.id == "payments.unauthorised"

    allowed, _c, _n = screen_outbound(
        _call(
            "create_payment",
            {
                "amount": "42.00",
                "currency": "EUR",
                "payee": "Acme",
                "payment_mandate": sign(**_authorised()),
            },
        ),
        rules,
        trust=trust,
    )
    assert allowed is None

    assert "create_payment" not in SHELL_TOOLS
    outside, _c, _n = screen_outbound(_call("create_payment", {"amount": 1}), rules)
    assert outside is not None

    off, _c, _n = screen_outbound(
        _call("create_payment", {"amount": 1}), rules, check_payments=False
    )
    assert off is None
