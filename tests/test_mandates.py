"""Verifying a mandate's signature against keys this deployment chose to trust.

These tests exist because the module they cover replaced a stated weakness.
The payment check used to read a mandate's shape and say plainly that the
signature was not examined; that was honest and it stopped nothing that
bothered to attach a plausible string.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import pytest

from ai_bunker.mandates import ALGORITHMS, claims_of, load_trust, verify


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils

    key = ec.generate_private_key(ec.SECP256R1())
    numbers = key.public_key().public_numbers()
    directory = tmp_path_factory.mktemp("keys")
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

    def sign(claims: dict, *, kid: str = "k1", alg: str = "ES256") -> str:
        header = _b64(json.dumps({"alg": alg, "kid": kid}).encode())
        payload = _b64(json.dumps(claims).encode())
        der = key.sign(f"{header}.{payload}".encode(), ec.ECDSA(hashes.SHA256()))
        r, s = utils.decode_dss_signature(der)
        return f"{header}.{payload}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"

    return sign, str(jwks), directory


def test_a_genuine_signature_verifies(keys):
    sign, jwks, _d = keys
    verdict = verify(sign({"iss": "a", "exp": time.time() + 60}), load_trust(jwks))
    assert verdict.verified and verdict.algorithm == "ES256" and verdict.key_id == "k1"


def test_a_tampered_payload_does_not(keys):
    sign, jwks, _d = keys
    header, _payload, signature = sign({"amount": 42}).split(".")
    forged = _b64(json.dumps({"amount": 4200}).encode())
    verdict = verify(f"{header}.{forged}.{signature}", load_trust(jwks))
    assert not verdict.verified and any("not valid" in p for p in verdict.problems)


def test_the_none_algorithm_is_never_accepted(keys):
    """An algorithm field an attacker controls must never select a code path
    that skips verification. This is the oldest JWT bug there is."""
    _sign, jwks, _d = keys
    token = f"{_b64(json.dumps({'alg': 'none'}).encode())}.{_b64(b'{}')}.AAAA"
    verdict = verify(token, load_trust(jwks))
    assert not verdict.verified
    assert "none" not in ALGORITHMS


def test_an_unknown_key_is_refused(keys):
    sign, jwks, _d = keys
    verdict = verify(sign({}, kid="k9"), load_trust(jwks))
    assert not verdict.verified and any("no trusted key" in p for p in verdict.problems)


def test_an_issuer_off_the_list_is_refused_even_when_signed(keys):
    """Signed by a key we trust is not the same as signed by somebody we let
    authorise payments."""
    sign, jwks, _d = keys
    trust = load_trust(jwks, issuers=("https://wallet.example",))
    verdict = verify(sign({"iss": "https://elsewhere.example"}), trust)
    assert not verdict.verified and any("issuer list" in p for p in verdict.problems)


def test_no_issuer_list_accepts_any_issuer_with_a_trusted_key(keys):
    sign, jwks, _d = keys
    assert verify(sign({"iss": "https://anyone.example"}), load_trust(jwks)).verified


def test_a_revoked_mandate_is_refused(keys):
    sign, jwks, directory = keys
    revoked = directory / "revoked.txt"
    revoked.write_text("# a comment\nbad-mandate\n", encoding="utf-8")
    trust = load_trust(jwks, revoked_file=str(revoked))
    assert not verify(sign({"jti": "bad-mandate"}), trust).verified
    assert verify(sign({"jti": "fine"}), trust).verified


def test_expiry_and_not_before_are_enforced(keys):
    sign, jwks, _d = keys
    trust = load_trust(jwks)
    assert not verify(sign({"exp": time.time() - 600}), trust).verified
    assert not verify(sign({"nbf": time.time() + 600}), trust).verified
    assert verify(sign({"exp": time.time() + 600, "nbf": time.time() - 10}), trust).verified


def test_clock_skew_is_tolerated(keys):
    """A mandate that expired four seconds ago, on a machine whose clock is a
    few seconds off, is not an attack."""
    sign, jwks, _d = keys
    assert verify(sign({"exp": time.time() - 4}), load_trust(jwks)).verified


# ---------------------------------------------------------------------------
# Could-not-check and failed are different answers.
# ---------------------------------------------------------------------------


def test_no_trust_is_reported_as_unavailable_not_as_failure(keys):
    """Collapsing the two would let an operator read `not verified` as `the
    mandate is bad` when it means `we never looked`."""
    sign, _jwks, _d = keys
    verdict = verify(sign({}), load_trust(""))
    assert verdict.unavailable and not verdict.verified
    assert "NOT verified" in verdict.problems[0]


def test_an_unreadable_key_set_is_reported(tmp_path):
    trust = load_trust(str(tmp_path / "missing.json"))
    assert not trust.available and "could not be read" in trust.reason


def test_an_empty_key_set_is_not_a_trust(tmp_path):
    jwks = tmp_path / "jwks.json"
    jwks.write_text('{"keys": []}', encoding="utf-8")
    assert not load_trust(str(jwks)).available


# ---------------------------------------------------------------------------
# Sovereignty.
# ---------------------------------------------------------------------------


def test_a_file_key_set_needs_no_network(keys):
    """The intended deployment. A gateway whose claim is that nothing leaves
    the network must not fetch a JWKS before it can refuse a payment."""
    _sign, jwks, _d = keys
    assert load_trust(jwks).available
    assert not jwks.startswith("http")


def test_rotating_a_key_is_copying_a_file(keys, tmp_path):
    """A path is re-read every time, so there is no cache to invalidate."""
    _sign, jwks, _d = keys
    rotated = tmp_path / "jwks.json"
    rotated.write_text('{"keys": []}', encoding="utf-8")
    assert not load_trust(str(rotated)).available
    rotated.write_text(Path(jwks).read_text(encoding="utf-8"), encoding="utf-8")
    assert load_trust(str(rotated)).available


def test_claims_of_never_raises_on_rubbish():
    assert claims_of("not-a-token") == {}
    assert claims_of("") == {}
