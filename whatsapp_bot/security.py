"""
Transport-level hardening for the AgriFlow API.

Three middlewares plus a startup posture check, all independent of the
business logic in server.py:

  SecurityHeadersMiddleware   security headers on every response. JSON and
                              CSV answers get a deny-everything CSP and
                              Cache-Control: no-store; the HTML billing pages
                              get a CSP that only allows their own inline
                              style and a same-origin form post.
  BodySizeLimitMiddleware     413 for any request body above MAX_BODY_BYTES
                              (default 64 KiB). Nothing this API accepts is
                              larger than a few hundred bytes.
  RateLimitMiddleware         fixed-window limiter keyed by client IP. Two
                              tiers: a general one and a stricter one for
                              the routes that run the engine, call the LLM,
                              or touch billing state. In-process, so it is
                              per replica; that is enough to stop a single
                              client from monopolising a worker, which is the
                              failure mode a public Space actually sees.

  check_production_posture()  refuses to boot with APP_ENV=production while a
                              demo-only default is still active (mock mode,
                              unsigned Twilio webhooks, unmetered /chat
                              impersonation, mock billing, unsalted phone
                              hashes). In development the same findings are
                              logged as warnings so nobody forgets them.

Env:
    APP_ENV                 development (default) | production
    TRUST_PROXY             true (default): take the client IP from the first
                            X-Forwarded-For hop. Both known hosts (Hugging Face
                            Spaces, Vercel) sit behind a reverse proxy.
    MAX_BODY_BYTES          default 65536
    RATE_LIMIT_ENABLED      default true
    RATE_LIMIT_PER_MINUTE   general tier, default 240
    RATE_LIMIT_HEAVY_PER_MINUTE
                            heavy tier, default 30
    SECURITY_POSTURE_STRICT true (default): production posture failures abort
                            startup; false downgrades them to warnings.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from . import request_log


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def app_env() -> str:
    return os.getenv("APP_ENV", "development").strip().lower() or "development"


def is_production() -> bool:
    return app_env() == "production"


# =============================================================================
# CLIENT ADDRESS
# =============================================================================

def client_ip(request: Request) -> str:
    """
    Best-effort client address for rate limiting.

    Behind a reverse proxy the socket peer is the proxy, so the first hop of
    X-Forwarded-For is the client. That header is attacker-controlled when the
    app is reached directly, hence the TRUST_PROXY switch for bare deployments.
    """
    if _env_bool("TRUST_PROXY", True):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


# =============================================================================
# SECURITY HEADERS
# =============================================================================

_HTML_CSP = (
    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
    "frame-ancestors 'none'; base-uri 'none'"
)
_DATA_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"

# Paths whose responses carry an interactive UI (Swagger, ReDoc) and therefore
# need scripts. They are only mounted when API_DOCS_ENABLED is true.
_DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        headers.setdefault("Cross-Origin-Resource-Policy", "cross-origin")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")

        path = request.url.path
        content_type = headers.get("content-type", "")
        if path.startswith(_DOC_PATHS):
            pass  # Swagger UI ships its own inline scripts; leave CSP unset there.
        elif content_type.startswith("text/html"):
            headers.setdefault("Content-Security-Policy", _HTML_CSP)
        else:
            headers.setdefault("Content-Security-Policy", _DATA_CSP)

        # Nothing served here is cacheable by a shared cache: engine answers
        # change on redeploy and billing pages are per order.
        if not path.startswith(_DOC_PATHS):
            headers.setdefault("Cache-Control", "no-store")

        # HSTS only makes sense on an HTTPS origin. The proxies set the
        # forwarded proto; a bare local run stays without it.
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        if proto == "https":
            headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return response


# =============================================================================
# BODY SIZE
# =============================================================================

class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        limit = _env_int("MAX_BODY_BYTES", 65536)
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    return JSONResponse(
                        status_code=413,
                        content={"error": "payload_too_large", "limit_bytes": limit},
                    )
            except ValueError:
                return JSONResponse(status_code=400, content={"error": "bad_content_length"})
        return await call_next(request)


# =============================================================================
# RATE LIMIT
# =============================================================================

# Routes that run the matching engine, call the LLM, or mutate billing state.
HEAVY_PREFIXES: Tuple[str, ...] = (
    "/chat", "/whatsapp", "/billing/",
    "/api/v1/simulate", "/api/v1/matches/explain", "/api/v1/report.csv",
    "/api/v1/events",
)


class _FixedWindow:
    """Per-key counters in one-minute windows, pruned lazily."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: Dict[Tuple[str, str], List[int]] = {}
        self._last_prune = 0.0

    def hit(self, key: Tuple[str, str], limit: int, now: Optional[float] = None) -> Tuple[bool, int]:
        """Record one request. Returns (allowed, seconds_until_window_resets)."""
        now = time.time() if now is None else now
        window = int(now // 60)
        with self._lock:
            if now - self._last_prune > 120:
                stale = [k for k, (w, _) in self._hits.items() if w < window - 1]
                for k in stale:
                    del self._hits[k]
                self._last_prune = now
            entry = self._hits.get(key)
            if entry is None or entry[0] != window:
                entry = [window, 0]
                self._hits[key] = entry
            entry[1] += 1
            allowed = entry[1] <= limit
        retry_after = max(1, int(60 - (now % 60)))
        return allowed, retry_after

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


_window = _FixedWindow()


def reset_rate_limits() -> None:
    """Test hook."""
    _window.reset()


def _tier_for(path: str) -> Tuple[str, int]:
    if path == "/health" or path.startswith(_DOC_PATHS):
        return "general", _env_int("RATE_LIMIT_PER_MINUTE", 240)
    if path.startswith(HEAVY_PREFIXES):
        return "heavy", _env_int("RATE_LIMIT_HEAVY_PER_MINUTE", 30)
    return "general", _env_int("RATE_LIMIT_PER_MINUTE", 240)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not _env_bool("RATE_LIMIT_ENABLED", True) or request.method == "OPTIONS":
            return await call_next(request)
        tier, limit = _tier_for(request.url.path)
        ip = client_ip(request)
        allowed, retry_after = _window.hit((ip, tier), limit)
        if not allowed:
            request_log.log(
                logging.WARNING, "request.rate_limited",
                path=request.url.path, tier=tier, limit=limit,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limited",
                    "detail": "Terlalu banyak permintaan. Coba lagi sebentar.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        return response


# =============================================================================
# PRODUCTION POSTURE
# =============================================================================

class InsecureProductionConfig(RuntimeError):
    pass


def posture_findings(settings) -> List[str]:
    """
    Demo-only defaults that must be off before real traffic. Each string is a
    complete sentence naming the env var to change.
    """
    findings: List[str] = []
    if settings.mock_mode:
        findings.append("MOCK_MODE is on; Gemini and Twilio are stubbed and webhook signatures are skipped.")
    if not settings.twilio_validate_signature:
        findings.append("TWILIO_VALIDATE_SIGNATURE is off; anyone can POST /whatsapp as any number.")
    if settings.debug_chat_enabled and not is_production():
        findings.append("DEBUG_CHAT_ENABLED honours a caller-supplied sender on /chat (development only).")
    if settings.billing_mock:
        findings.append("BILLING_MOCK is on; orders settle without a payment provider.")
    if not settings.phone_hash_salt:
        findings.append("PHONE_HASH_SALT is unset; phone hashes are reversible by brute force.")
    if not settings.manychat_webhook_secret:
        findings.append("MANYCHAT_WEBHOOK_SECRET is unset; POST /manychat/webhook refuses every request until it is set (fails closed, not open).")
    if os.getenv("API_DOCS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}:
        findings.append("API_DOCS_ENABLED exposes the OpenAPI schema and Swagger UI.")
    return findings


def check_production_posture(settings) -> List[str]:
    """
    Log every finding. In production with SECURITY_POSTURE_STRICT (default)
    raise so the process does not come up half-secured.
    """
    findings = posture_findings(settings)
    env = app_env()
    for f in findings:
        request_log.log(
            logging.ERROR if is_production() else logging.WARNING,
            "security.posture", app_env=env, finding=f,
        )
    if findings and is_production() and _env_bool("SECURITY_POSTURE_STRICT", True):
        raise InsecureProductionConfig(
            "Refusing to start with APP_ENV=production: " + " | ".join(findings)
        )
    return findings


def install(app) -> None:
    """
    Mount the three middlewares. Starlette wraps in reverse order of
    add_middleware, so the headers middleware is added last to sit outermost
    and stamp even the 413 and 429 responses the other two produce.
    """
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
