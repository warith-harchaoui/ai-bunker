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


# ---------------------------------------------------------------------------
# The key material itself. This was the least-covered code in the project and
# the highest-consequence: it turns a key-set entry into the public key a
# payment is verified against. A bug here accepts a mandate signed by the
# wrong key, which is the thing the protocol exists to prevent.
# ---------------------------------------------------------------------------


def _write_jwks(directory, entry: dict) -> str:
    path = directory / f"jwks-{entry.get('kid', 'k')}.json"
    path.write_text(json.dumps({"keys": [entry]}), encoding="utf-8")
    return str(path)


def test_an_rsa_mandate_verifies(tmp_path):
    """RSA keys were constructed by code no test ran. The two integers come
    out of base64 in big-endian order, and getting that wrong yields a key
    that verifies nothing -- or, worse, a different key."""
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()

    def raw(value: int) -> str:
        return _b64(value.to_bytes((value.bit_length() + 7) // 8, "big"))

    jwks = _write_jwks(
        tmp_path, {"kty": "RSA", "kid": "rsa1", "n": raw(numbers.n), "e": raw(numbers.e)}
    )

    header = _b64(json.dumps({"alg": "RS256", "kid": "rsa1"}).encode())
    payload = _b64(json.dumps({"iss": "bank.test", "amount": "10.00"}).encode())
    signature = key.sign(f"{header}.{payload}".encode(), padding.PKCS1v15(), hashes.SHA256())
    token = f"{header}.{payload}.{_b64(signature)}"

    verdict = verify(token, trust=load_trust(jwks))
    assert verdict.verified, verdict.problems


def test_an_ed25519_mandate_verifies(tmp_path):
    """Ed25519 is the curve a sovereign deployment is most likely to pick, and
    its branch had never run."""
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    key = ed25519.Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    jwks = _write_jwks(tmp_path, {"kty": "OKP", "crv": "Ed25519", "kid": "ed1", "x": _b64(public)})

    header = _b64(json.dumps({"alg": "EdDSA", "kid": "ed1"}).encode())
    payload = _b64(json.dumps({"iss": "bank.test"}).encode())
    token = f"{header}.{payload}.{_b64(key.sign(f'{header}.{payload}'.encode()))}"

    verdict = verify(token, trust=load_trust(jwks))
    assert verdict.verified, verdict.problems


@pytest.mark.parametrize(
    "entry",
    [
        {"kty": "EC", "crv": "P-999", "kid": "k", "x": "AA", "y": "AA"},
        {"kty": "WAT", "kid": "k", "x": "AA"},
        {"kty": "OKP", "crv": "X25519", "kid": "k", "x": "AA"},
    ],
)
def test_a_key_type_this_does_not_understand_is_refused(tmp_path, entry):
    """Refusing beats guessing. A key set naming a curve this code does not
    implement must produce a refusal, never a best-effort verification -- a
    payment verified against a misread key is worse than one refused."""
    pytest.importorskip("cryptography")
    header = _b64(json.dumps({"alg": "ES256", "kid": "k"}).encode())
    payload = _b64(json.dumps({"iss": "bank.test"}).encode())
    token = f"{header}.{payload}.{_b64(b'x' * 64)}"

    verdict = verify(token, trust=load_trust(_write_jwks(tmp_path, entry)))
    assert not verdict.verified
    assert verdict.problems


def test_a_malformed_mandate_is_refused_rather_than_raising(tmp_path, keys):
    """A gateway cannot raise while explaining a refusal."""
    _sign, jwks, _directory = keys
    trust = load_trust(jwks)
    for token in ("", "not-a-jws", "a.b", "a.b.c.d", "!!!.###.$$$", "e30.e30.????"):
        verdict = verify(token, trust=trust)
        assert not verdict.verified
        assert verdict.problems, token


def test_an_unreadable_revocation_list_is_reported_not_fatal(tmp_path, keys):
    """A missing revocation list must not stop the gateway starting, and must
    not pass silently either: an operator who configured one believes
    revocations are being honoured."""
    _sign, jwks, _directory = keys
    trust = load_trust(jwks, revoked_file=str(tmp_path / "absent.txt"))
    assert trust is not None


def test_a_key_set_served_over_http_is_fetched_and_cached(monkeypatch, tmp_path):
    """A key set at a URL is how a bank publishes one, and the fetch had never
    run. The cache matters as much: without it every payment verification is a
    network round trip on the request path.
    """
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, utils

    from ai_bunker import mandates

    key = ec.generate_private_key(ec.SECP256R1())
    numbers = key.public_key().public_numbers()
    document = json.dumps(
        {
            "keys": [
                {
                    "kty": "EC",
                    "crv": "P-256",
                    "kid": "web1",
                    "x": _b64(numbers.x.to_bytes(32, "big")),
                    "y": _b64(numbers.y.to_bytes(32, "big")),
                }
            ]
        }
    ).encode()

    fetches = {"n": 0}

    class _Response:
        def read(self):
            return document

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    def fake_urlopen(url, timeout=None):
        fetches["n"] += 1
        return _Response()

    monkeypatch.setattr(mandates.urllib.request, "urlopen", fake_urlopen)
    mandates._JWKS_CACHE.clear()

    header = _b64(json.dumps({"alg": "ES256", "kid": "web1"}).encode())
    payload = _b64(json.dumps({"iss": "bank.test"}).encode())
    der = key.sign(f"{header}.{payload}".encode(), ec.ECDSA(hashes.SHA256()))
    r, s_ = utils.decode_dss_signature(der)
    token = f"{header}.{payload}.{_b64(r.to_bytes(32, 'big') + s_.to_bytes(32, 'big'))}"

    url = "https://keys.bank.test/jwks.json"
    assert verify(token, trust=load_trust(url)).verified
    assert fetches["n"] == 1

    # Second load must come from the cache, not the network.
    assert verify(token, trust=load_trust(url)).verified
    assert fetches["n"] == 1, "the key set was fetched twice"


def test_an_unreachable_key_set_refuses_rather_than_passing(monkeypatch, keys):
    """The direction that matters. A key set that cannot be fetched means the
    signature was not verified, and an unverified mandate must be refused --
    passing it would authorise a payment on the strength of a network error.
    """
    pytest.importorskip("cryptography")
    from ai_bunker import mandates

    sign, _jwks, _directory = keys

    def fail(url, timeout=None):
        raise OSError("connection refused")

    monkeypatch.setattr(mandates.urllib.request, "urlopen", fail)
    mandates._JWKS_CACHE.clear()

    verdict = verify(sign({"iss": "bank.test"}), trust=load_trust("https://down.test/jwks.json"))
    assert not verdict.verified
    assert verdict.problems
