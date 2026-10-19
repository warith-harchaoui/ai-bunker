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
    how most agents would actually charge a card."""
    assert inspect("http_post", {"url": "https://api.stripe.com/v1/charges"}).moves_money


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
# A mandate has to be there at all.
# ---------------------------------------------------------------------------


def test_a_payment_with_no_mandate_is_refused(signer):
    _sign, trust = signer
    finding = inspect("create_payment", {"amount": 4200, "currency": "EUR"}, trust)
    assert not finding.ok and "no mandate" in finding.problems[0]


def test_an_unsigned_assertion_is_not_a_mandate(signer):
    """Without a proof it is a JSON object the agent could have written
    itself, which is the authorisation AP2 does not accept."""
    _sign, trust = signer
    finding = inspect("create_payment", {"amount": 10, "mandate": {"intent": "buy"}}, trust)
    assert not finding.ok and "no proof" in finding.problems[0]


def test_a_bare_string_that_is_not_a_jws_is_refused(signer):
    _sign, trust = signer
    assert not inspect("create_payment", {"mandate": "approved-by-the-user"}, trust).ok


# ---------------------------------------------------------------------------
# The signature, now actually checked.
# ---------------------------------------------------------------------------


def test_a_properly_signed_mandate_for_this_charge_passes(signer):
    sign, trust = signer
    finding = inspect(
        "create_payment",
        {
            "amount": "42.00",
            "currency": "EUR",
            "payee": "Acme",
            "payment_mandate": sign(**_authorised()),
        },
        trust,
    )
    assert finding.ok and finding.verified
    assert finding.issuer == "https://wallet.example"


def test_a_tampered_payload_fails_verification(signer):
    sign, trust = signer
    token = sign(**_authorised())
    header, _payload, signature = token.split(".")
    forged = _b64(json.dumps(_authorised(amount="99999.00")).encode())
    finding = inspect(
        "create_payment",
        {
            "amount": "99999.00",
            "currency": "EUR",
            "payee": "Acme",
            "payment_mandate": f"{header}.{forged}.{signature}",
        },
        trust,
    )
    assert not finding.ok and not finding.verified
    assert any("not valid" in p for p in finding.problems)


def test_the_none_algorithm_is_refused(signer):
    """The classic JWT forgery. An algorithm field an attacker controls must
    never select a code path that skips verification."""
    _sign, trust = signer
    from ai_bunker.mandates import verify

    none_header = _b64(json.dumps({"alg": "none"}).encode())
    token = f"{none_header}.{_b64(json.dumps(_authorised()).encode())}.AAAA"
    verdict = verify(token, trust)
    assert not verdict.verified
    assert any("not accepted" in p for p in verdict.problems)

    # And through the whole check, where it is refused either way.
    finding = inspect("create_payment", {"amount": "42.00", "payment_mandate": token}, trust)
    assert not finding.ok


def test_an_untrusted_issuer_is_refused(signer):
    """Signed by a key we trust is not the same as signed by somebody we let
    authorise payments."""
    sign, trust = signer
    finding = inspect(
        "create_payment",
        {
            "amount": "42.00",
            "currency": "EUR",
            "payee": "Acme",
            "payment_mandate": sign(**_authorised(iss="https://elsewhere.example")),
        },
        trust,
    )
    assert not finding.ok and any("issuer list" in p for p in finding.problems)


def test_a_revoked_mandate_is_refused(signer):
    sign, trust = signer
    finding = inspect(
        "create_payment",
        {
            "amount": "42.00",
            "currency": "EUR",
            "payee": "Acme",
            "payment_mandate": sign(**_authorised(jti="revoked-mandate")),
        },
        trust,
    )
    assert not finding.ok and any("revoked" in p for p in finding.problems)


def test_an_expired_mandate_is_refused(signer):
    sign, trust = signer
    finding = inspect(
        "create_payment",
        {
            "amount": "42.00",
            "currency": "EUR",
            "payee": "Acme",
            "payment_mandate": sign(**_authorised(exp=time.time() - 600)),
        },
        trust,
    )
    assert not finding.ok and any("expired" in p for p in finding.problems)


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


def test_an_inflated_amount_is_refused_despite_a_valid_signature(signer):
    """The attack this whole module exists for. The mandate is genuine, the
    signature verifies, and the charge is a hundred times what was agreed."""
    sign, trust = signer
    finding = inspect(
        "create_payment",
        {
            "amount": "4200.00",
            "currency": "EUR",
            "payee": "Acme",
            "payment_mandate": sign(**_authorised()),
        },
        trust,
    )
    assert finding.verified, "the signature really is valid"
    assert not finding.ok, "and the payment is still not the authorised one"
    assert any("exceeds what was authorised" in p for p in finding.problems)


def test_a_substituted_payee_is_refused(signer):
    sign, trust = signer
    finding = inspect(
        "create_payment",
        {
            "amount": "42.00",
            "currency": "EUR",
            "payee": "Evil Ltd",
            "payment_mandate": sign(**_authorised()),
        },
        trust,
    )
    assert finding.verified and not finding.ok


def test_a_substituted_currency_is_refused(signer):
    sign, trust = signer
    finding = inspect(
        "create_payment",
        {
            "amount": "42.00",
            "currency": "USD",
            "payee": "Acme",
            "payment_mandate": sign(**_authorised()),
        },
        trust,
    )
    assert not finding.ok


def test_charging_less_than_authorised_is_allowed(signer):
    """A mandate is a ceiling, not an instruction. Refusing a smaller charge
    would break every legitimate partial capture."""
    sign, trust = signer
    finding = inspect(
        "create_payment",
        {
            "amount": "20.00",
            "currency": "EUR",
            "payee": "Acme",
            "payment_mandate": sign(**_authorised()),
        },
        trust,
    )
    assert finding.ok


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


def test_the_message_states_that_chains_are_not_verified(signer):
    """AP2 links a Payment Mandate to a Checkout Mandate to what the user saw.
    Verifying one link says nothing about the others, and the refusal says so
    rather than letting a reader assume otherwise."""
    _sign, trust = signer
    message = refusal_message(inspect("create_payment", {"amount": 1}, trust))
    assert "CHAINS are not" in message
    assert "Trusted Surface" in message


def test_the_rule_carries_the_caveat_into_the_audit_log(signer):
    _sign, trust = signer
    rule = as_rule(inspect("create_payment", {"amount": 1}, trust))
    assert rule.id == "payments.unauthorised" and rule.severity == "BLOCKER"
    assert "CHAINS are not" in rule.description
    assert not rule.pattern.search("create_payment")


# ---------------------------------------------------------------------------
# Shape handling that must not regress.
# ---------------------------------------------------------------------------


def test_arguments_arrive_as_a_json_string_too(signer):
    """OpenAI tool calls carry `arguments` as a string, not an object."""
    sign, trust = signer
    args = json.dumps(
        {
            "amount": "42.00",
            "currency": "EUR",
            "payee": "Acme",
            "payment_mandate": sign(**_authorised()),
        }
    )
    assert inspect("create_payment", args, trust).ok


def test_a_nested_mandate_is_found(signer):
    sign, trust = signer
    finding = inspect(
        "create_payment",
        {
            "amount": "42.00",
            "currency": "EUR",
            "payee": "Acme",
            "body": {"payment": {"payment_mandate": sign(**_authorised())}},
        },
        trust,
    )
    assert finding.ok


def test_walking_arguments_is_depth_bounded(signer):
    """A guardrail that walks an arbitrary structure on the enforcement path
    is a guardrail that becomes a stall."""
    sign, trust = signer
    deep: dict = {"payment_mandate": sign(**_authorised())}
    for _ in range(12):
        deep = {"nested": deep}
    assert not inspect("create_payment", deep, trust).ok


def test_a_finding_on_a_non_payment_is_vacuously_ok():
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


def test_stage_four_refuses_an_unauthorised_payment(signer):
    from ai_bunker.adopt import ROOT
    from ai_bunker.pipeline import screen_outbound
    from ai_bunker.rules import load_rules

    _sign, trust = signer
    rules = load_rules(ROOT / "charter" / "rules")
    refusal, _c, _n = screen_outbound(_call("create_payment", {"amount": 4200}), rules, trust=trust)
    assert refusal is not None and refusal.id == "payments.unauthorised"


def test_stage_four_forwards_an_authorised_one(signer):
    from ai_bunker.adopt import ROOT
    from ai_bunker.pipeline import screen_outbound
    from ai_bunker.rules import load_rules

    sign, trust = signer
    rules = load_rules(ROOT / "charter" / "rules")
    refusal, _c, _n = screen_outbound(
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
    assert refusal is None


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
