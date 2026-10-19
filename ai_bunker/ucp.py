"""Check the cart being charged against the cart the user authorised.

The hole this fills
-------------------
A mandate-presence check asks "is there an authorisation". It does not ask
"an authorisation for *what*", and the gap between those two questions is the
whole attack. A mandate the user signed for 42 EUR at one merchant passes a
presence check when it is attached to a 4,200 EUR charge at another. The
signature is valid. The mandate is unexpired. The payment is not the one the
user agreed to.

UCP -- the Universal Commerce Protocol -- is the Checkout Object standard
used *with* the Checkout Mandate, and that pairing is the point: the mandate
says what was authorised, the checkout object says what is being charged, and
somebody has to compare them. On an agentic path the agent is the one thing
that cannot be trusted to, because it is the party that would benefit from
the discrepancy.

How the comparison is made
--------------------------
Three ways, strongest first, and the strongest available one decides:

1. **A cart digest in the mandate.** If the mandate carries a hash of the
   cart it authorised, the cart is hashed and compared. This is exact and
   covers fields nobody thought to enumerate.
2. **Field comparison.** Amount, currency and payee, when the mandate states
   them. Amounts are compared in minor units as integers -- comparing money
   as floats is how 4.20 becomes 4.199999999999999 and a check passes that
   should not.
3. **Nothing.** If the mandate states no constraints at all, that is reported
   rather than treated as agreement: an authorisation that constrains nothing
   authorises everything, which is worth saying out loud.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

#: Keys a checkout object uses for the total, in the orders seen in the wild.
AMOUNT_KEYS = ("amount", "total", "total_amount", "totalAmount", "value", "grand_total")
CURRENCY_KEYS = ("currency", "currency_code", "currencyCode")
PAYEE_KEYS = ("payee", "merchant", "merchant_id", "merchantId", "recipient", "destination")

#: Where a mandate records the cart it authorised.
DIGEST_KEYS = ("cart_hash", "cartHash", "checkout_hash", "cart_digest", "sha256")

#: Minor units per major unit. Most currencies are 100; these are not, and
#: charging 1000 JPY as "10.00" would otherwise look like a 100x discrepancy.
MINOR_UNITS = {
    "JPY": 1,
    "KRW": 1,
    "VND": 1,
    "CLP": 1,
    "ISK": 1,
    "BHD": 1000,
    "KWD": 1000,
    "JOD": 1000,
    "OMR": 1000,
    "TND": 1000,
}


@dataclass
class Comparison:
    """What the cart says, what the mandate authorised, and the difference."""

    method: str = "none"
    charged: dict[str, Any] = field(default_factory=dict)
    authorised: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    unconstrained: bool = False

    @property
    def ok(self) -> bool:
        return not self.problems


def _walk(data: Any, keys: tuple[str, ...], depth: int = 0) -> Any:
    """First value under any of `keys`, bounded in depth like everything on
    the enforcement path."""
    if depth > 4 or not isinstance(data, dict):
        return None
    for key in keys:
        if key in data and data[key] not in (None, "", {}, []):
            return data[key]
    for value in data.values():
        if isinstance(value, dict):
            found = _walk(value, keys, depth + 1)
            if found is not None:
                return found
    return None


def minor_units(amount: Any, currency: str = "") -> int | None:
    """Money as an integer count of minor units.

    Floats are not money. `0.1 + 0.2` is not `0.3`, and a comparison that
    passes because two different totals round to the same float is a payment
    nobody authorised.
    """
    if amount is None:
        return None
    scale = MINOR_UNITS.get(currency.upper(), 100)
    if isinstance(amount, int) and not isinstance(amount, bool):
        # An integer is already minor units in every protocol that uses them.
        return amount
    try:
        value = Decimal(str(amount).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return int((value * scale).to_integral_value())


#: Fields that carry the mandate itself. They are stripped before hashing,
#: because a mandate cannot contain a digest of an object that contains the
#: mandate -- the first version did exactly that and the digest path could
#: never match, which is the quiet kind of broken where a check is present and
#: inert.
MANDATE_FIELDS = (
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


def without_mandate(cart: Any) -> Any:
    """The cart as it was before a mandate was attached to it."""
    if not isinstance(cart, dict):
        return cart
    return {key: without_mandate(value) for key, value in cart.items() if key not in MANDATE_FIELDS}


def cart_digest(cart: Any) -> str:
    """A stable hash of a cart, so two sides can agree on what it was.

    Keys are sorted and whitespace is fixed, because a digest that changes
    when a serialiser reorders a dictionary is a digest that always mismatches
    and therefore always gets switched off.
    """
    return hashlib.sha256(
        json.dumps(
            without_mandate(cart), sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()


def _normalise_payee(value: Any) -> str:
    """Compare payees without punctuation and case getting in the way."""
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def compare(cart: Any, claims: dict[str, Any]) -> Comparison:
    """Compare what is being charged against what the mandate authorised."""
    result = Comparison()

    currency = str(_walk(cart, CURRENCY_KEYS) or "")
    amount = _walk(cart, AMOUNT_KEYS)
    payee = _walk(cart, PAYEE_KEYS)
    result.charged = {"amount": amount, "currency": currency, "payee": payee}

    # 1. A digest binds the whole cart, including fields nobody enumerated.
    authorised_digest = _walk(claims, DIGEST_KEYS)
    if authorised_digest:
        result.method = "digest"
        result.authorised = {"cart_hash": authorised_digest}
        actual = cart_digest(cart)
        if actual != str(authorised_digest):
            result.problems.append(
                "the cart does not match the one the mandate authorised "
                f"(authorised {str(authorised_digest)[:16]}..., charging {actual[:16]}...)"
            )
        return result

    # 2. Field comparison, over whatever the mandate actually states.
    authorised_currency = str(_walk(claims, CURRENCY_KEYS) or "")
    authorised_amount = _walk(claims, AMOUNT_KEYS)
    authorised_payee = _walk(claims, PAYEE_KEYS)
    result.authorised = {
        "amount": authorised_amount,
        "currency": authorised_currency,
        "payee": authorised_payee,
    }

    if authorised_amount is None and not authorised_payee and not authorised_currency:
        result.unconstrained = True
        result.problems.append(
            "the mandate states no amount, currency or payee, so it authorises "
            "any charge to anyone. An authorisation that constrains nothing is "
            "not an authorisation for this payment"
        )
        return result

    result.method = "fields"

    if authorised_currency and currency and authorised_currency.upper() != currency.upper():
        result.problems.append(
            f"the mandate authorised {authorised_currency.upper()}, the charge is "
            f"in {currency.upper()}"
        )

    if authorised_amount is not None:
        reference = authorised_currency or currency
        want = minor_units(authorised_amount, reference)
        got = minor_units(amount, currency or reference)
        if want is None or got is None:
            result.problems.append("the amount could not be read as a number")
        elif got > want:
            result.problems.append(
                f"the charge exceeds what was authorised: {got} > {want} "
                f"minor units of {(currency or reference).upper() or 'the currency'}"
            )

    if authorised_payee and payee and _normalise_payee(authorised_payee) != _normalise_payee(payee):
        result.problems.append(
            f"the mandate authorised a payment to {authorised_payee!r}, the charge is to {payee!r}"
        )

    return result
