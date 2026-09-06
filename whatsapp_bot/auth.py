"""
Supabase JWT verification for the FastAPI layer.

WHY THIS EXISTS
---------------
Without it the dashboard login is decorative: a user can sign in, but every
endpoint is equally reachable by someone who never did. This module is what
makes the login actually gate something.

TWO SIGNING SCHEMES
-------------------
Supabase projects issue access tokens under one of two schemes, and which one
you get depends on when the project was created:

  * Asymmetric (current default) — ECC/RSA, verified against the project's
    public JWKS at {SUPABASE_URL}/auth/v1/.well-known/jwks.json. Nothing secret
    lives on our side. Preferred.
  * Shared secret (legacy) — HS256 against SUPABASE_JWT_SECRET.

Both are supported. If SUPABASE_JWT_SECRET is set we use HS256; otherwise we
fall back to JWKS discovery from SUPABASE_URL. JWKS keys are cached in-process
by PyJWKClient, so steady-state verification makes no network call.

FAIL-CLOSED, EXCEPT WHERE WE SAY OTHERWISE
------------------------------------------
`require_user` rejects a request whenever it cannot positively verify a token,
including when auth is misconfigured. It never falls open on error — a
verification bug must lock people out, not let everyone in.

The one deliberate exception is REQUIRE_AUTH=false (the default), which leaves
the public data endpoints open so the offline hackathon demo runs with no
Supabase project attached. Endpoints that expose per-person data
(/billing/status) ignore that flag and always demand a token.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

try:
    import jwt
    from jwt import PyJWKClient
except ImportError as e:  # pragma: no cover - dependency is pinned
    raise RuntimeError(
        "pyjwt is not installed. Run: pip install -r requirements.txt"
    ) from e

from fastapi import Depends, Header, HTTPException, status


# Supabase signs user tokens with this audience claim.
_AUDIENCE = "authenticated"


@dataclass(frozen=True)
class AuthUser:
    """The verified caller. `sub` is the Supabase auth.users.id (a UUID)."""
    sub: str
    email: Optional[str] = None
    role: Optional[str] = None
    claims: Dict[str, Any] = None  # type: ignore[assignment]


def auth_configured() -> bool:
    return bool(os.getenv("SUPABASE_JWT_SECRET") or os.getenv("SUPABASE_URL"))


def require_auth_enabled() -> bool:
    """
    Whether the public data endpoints demand a token.

    Defaults to false so a fresh clone demos without Supabase. Turn it on in
    any deployment that has real subscribers.
    """
    return os.getenv("REQUIRE_AUTH", "false").strip().lower() in {"1", "true", "yes", "on"}


@functools.lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    base = os.environ["SUPABASE_URL"].rstrip("/")
    # PyJWKClient keeps its own key cache, so this is a cold-start cost only.
    return PyJWKClient(f"{base}/auth/v1/.well-known/jwks.json", cache_keys=True)


# Clock skew tolerated on exp/nbf/iat. Supabase tokens live an hour; thirty
# seconds covers a drifted container clock without meaningfully extending it.
_LEEWAY_SECONDS = 30


def _expected_issuer() -> Optional[str]:
    """Supabase issues tokens as {SUPABASE_URL}/auth/v1. None when URL unset."""
    base = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    return f"{base}/auth/v1" if base else None


def _decode(token: str) -> Dict[str, Any]:
    """
    Verify signature, expiry, audience and (when SUPABASE_URL is known) the
    issuer. Raises jwt exceptions on failure.

    Note we do NOT disable any default verification. In particular exp is
    always checked, so a stale token from a long-open browser tab is rejected
    rather than honoured. `exp` and `sub` are required claims: a token that
    never expires or names nobody is refused outright.
    """
    options: Dict[str, Any] = {"require": ["exp", "sub"]}
    issuer = _expected_issuer()
    common: Dict[str, Any] = {
        "audience": _AUDIENCE, "options": options, "leeway": _LEEWAY_SECONDS,
    }
    if issuer:
        common["issuer"] = issuer

    secret = os.getenv("SUPABASE_JWT_SECRET")
    if secret:
        return jwt.decode(token, secret, algorithms=["HS256"], **common)

    if not issuer:
        raise RuntimeError(
            "Auth is not configured: set SUPABASE_JWT_SECRET or SUPABASE_URL."
        )

    signing_key = _jwks_client().get_signing_key_from_jwt(token)
    return jwt.decode(
        token, signing_key.key, algorithms=["RS256", "ES256"], **common,
    )


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _verify(token: str) -> AuthUser:
    claims = _decode(token)
    sub = claims.get("sub")
    if not sub:
        raise jwt.InvalidTokenError("token has no subject")
    return AuthUser(
        sub=sub,
        email=claims.get("email"),
        role=claims.get("role"),
        claims=claims,
    )


# =============================================================================
# FASTAPI DEPENDENCIES
# =============================================================================

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Valid Supabase access token required.",
    headers={"WWW-Authenticate": "Bearer"},
)


async def require_user(
    authorization: Optional[str] = Header(default=None),
) -> AuthUser:
    """
    Hard gate — 401 unless the caller presents a verifiable token.

    Applies regardless of REQUIRE_AUTH. Use for anything that reveals data
    about a specific person.
    """
    token = _extract_bearer(authorization)
    if not token:
        raise _UNAUTHORIZED
    try:
        return _verify(token)
    except Exception:
        # Deliberately opaque: distinguishing "expired" from "bad signature"
        # from "auth misconfigured" hands a probing client a free oracle.
        raise _UNAUTHORIZED


async def optional_user(
    authorization: Optional[str] = Header(default=None),
) -> Optional[AuthUser]:
    """Identify the caller when possible, but never reject them."""
    token = _extract_bearer(authorization)
    if not token:
        return None
    try:
        return _verify(token)
    except Exception:
        return None


async def gated_user(
    authorization: Optional[str] = Header(default=None),
) -> Optional[AuthUser]:
    """
    Soft gate — enforces a token only when REQUIRE_AUTH is on.

    This is the demo seam: with REQUIRE_AUTH unset the public map endpoints stay
    open for judges, and flipping the flag turns them into subscriber-only data
    with no code change.
    """
    if not require_auth_enabled():
        return await optional_user(authorization)
    return await require_user(authorization)


# Re-exported so route signatures read clearly at the call site.
RequireUser = Depends(require_user)
GatedUser = Depends(gated_user)
OptionalUser = Depends(optional_user)
