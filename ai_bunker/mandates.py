"""Verify a mandate's signature, against keys this deployment chose to trust.

What changed, and why it matters
--------------------------------
An earlier version of the payment check read a mandate's shape and said so
plainly: present, parseable, unexpired, signature **not** checked. That was
honest and it was weak. A shape check stops the common failure -- an agent
that simply called the API with no mandate at all -- and stops nothing that
bothers to attach a plausible-looking string.

This closes it. A mandate is verified against a key set the operator
configured, by an issuer on a list the operator wrote, and is rejected if its
identifier appears in a revocation list. Verification that passes here means
the signature was made by a key this deployment trusts.

Sovereignty
-----------
The key set can be a file on disk, which is the intended deployment: a
gateway whose claim is that nothing leaves the network must not need to fetch
a JWKS from the internet before it can refuse a payment. A URL is supported
because real trust lists are published that way, and it is fetched once,
cached, and never on the enforcement path -- a mandate arriving while the
cache is cold is rejected rather than held, because a payment that waits on a
network call is a payment that happens when the network recovers.

What is still not done
----------------------
Only the mandate's own signature is checked. AP2 chains mandates -- a Payment
Mandate references a Checkout Mandate, which references what the user saw on
the Trusted Surface -- and verifying one link says nothing about the others.
Chain verification is a real piece of work and this is not it; the honest
summary is that a verified mandate here is *signed by a trusted key*, not
*proof the user agreed to this cart*. The cart check in `ucp.py` covers the
other half.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import base64
import binascii
import json
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import os_helper as osh

#: Algorithms accepted. `none` is absent on purpose: it is the classic JWT
#: forgery, and an algorithm field an attacker controls must never select a
#: code path that skips verification.
ALGORITHMS = {"ES256", "ES384", "RS256", "RS384", "RS512", "PS256", "EdDSA"}

#: How long a fetched JWKS is reused. Short enough that a rotated key is
#: picked up the same day, long enough that the fetch is never in a request.
JWKS_TTL_SECONDS = 3600

#: Clock skew allowed on `exp` and `nbf`.
LEEWAY_SECONDS = 60


@dataclass
class Trust:
    """What this deployment trusts, and the result of asking it."""

    keys: dict[str, Any] = field(default_factory=dict)
    issuers: tuple[str, ...] = ()
    revoked: frozenset[str] = frozenset()
    source: str = ""
    available: bool = False
    reason: str = ""


@dataclass
class Verdict:
    verified: bool = False
    issuer: str = ""
    key_id: str = ""
    algorithm: str = ""
    problems: list[str] = field(default_factory=list)
    #: True when verification could not be attempted at all, as opposed to
    #: attempted and failed. The two must never be reported as the same thing.
    unavailable: bool = False


def _b64(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def load_trust(
    jwks: str = "",
    *,
    issuers: tuple[str, ...] = (),
    revoked_file: str = "",
) -> Trust:
    """Read the key set, the issuer list and the revocation list.

    `jwks` is a path or a URL. A path is the sovereign case and is read on
    every call, so rotating a key is copying a file; a URL is fetched and
    cached for an hour.
    """
    trust = Trust(issuers=tuple(i for i in issuers if i), source=jwks)

    if not jwks:
        trust.reason = "no key set is configured"
        return trust

    try:
        if jwks.startswith(("http://", "https://")):
            document = _fetch_jwks(jwks)
        else:
            document = json.loads(Path(jwks).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        trust.reason = f"the key set at {jwks} could not be read ({exc})"
        return trust

    keys = document.get("keys") if isinstance(document, dict) else None
    if not isinstance(keys, list) or not keys:
        trust.reason = f"the key set at {jwks} contains no keys"
        return trust

    trust.keys = {str(k.get("kid") or ""): k for k in keys if isinstance(k, dict)}
    trust.available = True

    if revoked_file:
        try:
            lines = Path(revoked_file).read_text(encoding="utf-8").splitlines()
            trust.revoked = frozenset(
                line.strip() for line in lines if line.strip() and not line.startswith("#")
            )
        except OSError as exc:
            osh.warning(f"[mandates] revocation list {revoked_file} unreadable ({exc}).")
    return trust


_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _fetch_jwks(url: str) -> dict[str, Any]:
    """Fetch and cache. Never called on the enforcement path when warm."""
    cached = _JWKS_CACHE.get(url)
    if cached and time.time() - cached[0] < JWKS_TTL_SECONDS:
        return cached[1]
    with urllib.request.urlopen(url, timeout=5) as response:
        document = json.load(response)
    _JWKS_CACHE[url] = (time.time(), document)
    return document


def _public_key(jwk: dict[str, Any]):
    """Turn a JWK into a key object `cryptography` can verify with."""
    from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

    kty = jwk.get("kty")
    if kty == "EC":
        curves = {"P-256": ec.SECP256R1(), "P-384": ec.SECP384R1(), "P-521": ec.SECP521R1()}
        curve = curves.get(str(jwk.get("crv")))
        if curve is None:
            raise ValueError(f"unsupported curve {jwk.get('crv')!r}")
        numbers = ec.EllipticCurvePublicNumbers(
            int.from_bytes(_b64(jwk["x"]), "big"),
            int.from_bytes(_b64(jwk["y"]), "big"),
            curve,
        )
        return numbers.public_key()
    if kty == "RSA":
        rsa_numbers = rsa.RSAPublicNumbers(
            int.from_bytes(_b64(jwk["e"]), "big"),
            int.from_bytes(_b64(jwk["n"]), "big"),
        )
        return rsa_numbers.public_key()
    if kty == "OKP" and jwk.get("crv") == "Ed25519":
        return ed25519.Ed25519PublicKey.from_public_bytes(_b64(jwk["x"]))
    raise ValueError(f"unsupported key type {kty!r}")


def _verify_signature(key: Any, algorithm: str, signed: bytes, signature: bytes) -> None:
    """Raise unless the signature is valid. No boolean: a thrown exception
    cannot be accidentally truthy."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding, utils

    hashes_by_name = {"256": hashes.SHA256(), "384": hashes.SHA384(), "512": hashes.SHA512()}

    if algorithm == "EdDSA":
        key.verify(signature, signed)
        return

    digest = hashes_by_name[algorithm[-3:]]
    if algorithm.startswith("ES"):
        # JWS carries r||s concatenated; `cryptography` wants DER.
        half = len(signature) // 2
        der = utils.encode_dss_signature(
            int.from_bytes(signature[:half], "big"),
            int.from_bytes(signature[half:], "big"),
        )
        key.verify(der, signed, ec.ECDSA(digest))
        return
    if algorithm.startswith("PS"):
        key.verify(
            signature,
            signed,
            padding.PSS(mgf=padding.MGF1(digest), salt_length=digest.digest_size),
            digest,
        )
        return
    key.verify(signature, signed, padding.PKCS1v15(), digest)


def verify(token: str, trust: Trust) -> Verdict:
    """Verify one compact JWS against the configured trust.

    Returns a verdict rather than raising, because the caller reports several
    problems at once, and because an exception escaping onto the enforcement
    path is how a guardrail turns into an outage.
    """
    verdict = Verdict()

    if not trust.available:
        verdict.unavailable = True
        verdict.problems.append(
            f"the signature was NOT verified: {trust.reason or 'no trust configured'}"
        )
        return verdict

    try:
        from cryptography.hazmat.primitives.asymmetric import ec  # noqa: F401
    except ImportError:
        verdict.unavailable = True
        verdict.problems.append(
            "the signature was NOT verified: `cryptography` is not installed "
            "(pip install ai-bunker[mandates])"
        )
        return verdict

    parts = token.split(".")
    if len(parts) != 3:
        verdict.problems.append("the mandate is not a compact JWS")
        return verdict

    try:
        header = json.loads(_b64(parts[0]))
        claims = json.loads(_b64(parts[1]))
        signature = _b64(parts[2])
    except (ValueError, binascii.Error, json.JSONDecodeError) as exc:
        verdict.problems.append(f"the mandate could not be decoded ({exc})")
        return verdict

    algorithm = str(header.get("alg") or "")
    verdict.algorithm = algorithm
    verdict.key_id = str(header.get("kid") or "")
    verdict.issuer = str(claims.get("iss") or "") if isinstance(claims, dict) else ""

    if algorithm not in ALGORITHMS:
        # `none` lands here, which is the point.
        verdict.problems.append(f"algorithm {algorithm!r} is not accepted")
        return verdict

    jwk = trust.keys.get(verdict.key_id) or (
        next(iter(trust.keys.values())) if len(trust.keys) == 1 and not verdict.key_id else None
    )
    if jwk is None:
        verdict.problems.append(
            f"no trusted key matches kid {verdict.key_id!r}; this deployment trusts "
            f"{len(trust.keys)} key(s)"
        )
        return verdict

    try:
        _verify_signature(_public_key(jwk), algorithm, f"{parts[0]}.{parts[1]}".encode(), signature)
    except Exception as exc:
        verdict.problems.append(f"the signature is not valid ({type(exc).__name__})")
        return verdict

    verdict.verified = True

    if trust.issuers and verdict.issuer not in trust.issuers:
        verdict.verified = False
        verdict.problems.append(
            f"issuer {verdict.issuer!r} is signed by a trusted key but is not on "
            "this deployment's issuer list"
        )

    identifier = str(claims.get("jti") or "") if isinstance(claims, dict) else ""
    if identifier and identifier in trust.revoked:
        verdict.verified = False
        verdict.problems.append(f"mandate {identifier} has been revoked")

    now = time.time()
    expiry = claims.get("exp") if isinstance(claims, dict) else None
    if isinstance(expiry, (int, float)) and expiry + LEEWAY_SECONDS < now:
        verdict.verified = False
        verdict.problems.append("the mandate has expired")
    not_before = claims.get("nbf") if isinstance(claims, dict) else None
    if isinstance(not_before, (int, float)) and not_before - LEEWAY_SECONDS > now:
        verdict.verified = False
        verdict.problems.append("the mandate is not valid yet")

    return verdict


def claims_of(token: str) -> dict[str, Any]:
    """The claims, for callers that already verified. Never a substitute."""
    try:
        claims = json.loads(_b64(token.split(".")[1]))
    except (ValueError, IndexError, binascii.Error, json.JSONDecodeError):
        return {}
    return claims if isinstance(claims, dict) else {}
