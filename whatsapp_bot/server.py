"""
FastAPI app — Twilio WhatsApp webhook + health endpoint.

Endpoints:
    GET  /health              — liveness check, returns engine + bot status
    POST /whatsapp            — Twilio webhook (form-encoded); returns TwiML XML
    POST /chat                — debug JSON endpoint (no Twilio); useful for curl

    Dashboard API (v1.1):
    GET  /api/v1/commodities, /kabupaten, /surplus-deficit, /matches
    GET  /api/v1/matches/explain   — ranked suppliers for one deficit, why chosen
    GET  /api/v1/forecast, /anomalies (city accepts id or name)
    GET  /api/v1/meta              — "data per" provenance for every panel
    GET  /api/v1/summary           — KPIs computed from the engine run
    GET  /api/v1/report.csv        — downloadable match list
    POST /api/v1/simulate          — what-if scenarios (presets: semeru, ramadan, ...)
    GET  /api/v1/simulate/presets

    Env knobs added in v1.1:
    ALLOCATOR=lp|greedy            (default lp: exact capacitated transportation optimum)
    ANOMALY_GATE_WINDOW_DAYS=14    (batch anomalies newer than this exclude a node)

Run locally:
    uvicorn whatsapp_bot.server:app --reload --port 8000
"""

from __future__ import annotations
import sys
import os
from contextlib import asynccontextmanager
from typing import Any, Dict

# Make project-root imports work when running `uvicorn whatsapp_bot.server:app`
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from fastapi import Depends, FastAPI, Form, Header, HTTPException, Query, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, Response
except ImportError as e:
    raise RuntimeError(
        "fastapi not installed. Run: pip install -r requirements.txt"
    ) from e

import csv as _csv
import logging
import dataclasses
import datetime as _dt
import glob as _glob
import html as _html
import io as _io
import re as _re
import subprocess as _subprocess
from typing import Annotated, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

from matching_engine import LogisticsContext, run_matching
from matching_engine.constraints import generate_candidates
from matching_engine.models import EmergencyMode, RouteBlackout
from matching_engine import scoring as _scoring
from matching_engine.allocation import equity_multiplier_value, segment_multiplier_value
from analysis.anomaly_gate import load_anomaly_keys, latest_anomaly_date
from sample_data.loader import load_all_sample_data as _load_csv
from sample_data.loader import load_real_data as _load_real
from whatsapp_bot import request_log, security

# Precomputed data paths (resolved relative to project root so they work
# both locally and inside the Docker container)
_HERE_SERVER = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE_SERVER)
_ANOMALIES_PATH = os.path.join(_PROJECT_ROOT, "sample_data", "anomalies", "anomalies_all.json")
_ANOMALIES_META_PATH = os.path.join(_PROJECT_ROOT, "sample_data", "anomalies", "meta.json")
_FORECASTS_PATH = os.path.join(_PROJECT_ROOT, "sample_data", "forecasts", "forecast_all.json")
_PRICE_HISTORY_DIR = os.path.join(_PROJECT_ROOT, "sample_data", "price_history")

# v1.1 constants
ENGINE_VERSION = "1.1.0"
ANOMALY_METHOD = "hampel_mad_v2"     # was "shesd_v2" (audit F3: the code is Hampel/MAD, not S-H-ESD)
BPS_REFERENCE_YEAR = 2022
IPM_YEAR = 2024
ROAD_DISTANCE_SOURCE = "OSRM /table, OpenStreetMap, precomputed 2026-05"


def _allocator_strategy() -> str:
    """
    Layer 3 strategy the API serves. ALLOCATOR=lp (default) solves the exact
    capacitated transportation optimum; ALLOCATOR=greedy restores v1.0.
    """
    return os.environ.get("ALLOCATOR", "lp").strip().lower() or "lp"


def _anomaly_window_days() -> int:
    return int(os.environ.get("ANOMALY_GATE_WINDOW_DAYS", "14"))


import functools as _functools


@_functools.lru_cache(maxsize=1)
def _anomaly_keys() -> frozenset:
    """(kab_id, commodity_code) pairs currently anomalous per the batch scanner."""
    return frozenset(load_anomaly_keys(_ANOMALIES_PATH, window_days=_anomaly_window_days()))


@_functools.lru_cache(maxsize=1)
def _price_history_end() -> Optional[str]:
    """Newest observation date across the vendored PIHPS files, ISO string."""
    newest: Optional[str] = None
    for path in _glob.glob(os.path.join(_PRICE_HISTORY_DIR, "*.csv")):
        try:
            with open(path, encoding="utf-8-sig", newline="") as fh:
                reader = _csv.DictReader(fh)
                for row in reader:
                    d = (row.get("date") or "")[:10]
                    if d and (newest is None or d > newest):
                        newest = d
        except OSError:
            continue
    return newest


@_functools.lru_cache(maxsize=1)
def _git_commit() -> Optional[str]:
    env = os.environ.get("AGRIFLOW_COMMIT")
    if env:
        return env
    try:
        out = _subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=_PROJECT_ROOT,
            capture_output=True, text=True, timeout=3,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _load_data_backend() -> dict:
    """
    Select the data backend via the DATA_BACKEND env var.

    DATA_BACKEND=csv      (default) — REAL BPS Jawa Timur 2022 data from
                                      sample_data/surplus_deficit_real.csv.
                                      Offline-safe.
    DATA_BACKEND=demo                — the synthetic 19-commodity fixture. Test
                                      data only; never serve it to users.
    DATA_BACKEND=postgres            — load from Supabase/Postgres via db.db_loader.

    WHY THE DEFAULT IS REAL DATA
    ----------------------------
    This used to call load_all_sample_data(), whose default file is the
    synthetic surplus_deficit.csv. Every served response — dashboard map,
    WhatsApp reply, API — was therefore built on invented numbers while the
    real BPS-derived file sat unused beside it.

    That also caused a visible failure. The synthetic file prices rice demand
    in consumer cities at Rp16,400-17,000/kg against a 2022 farmgate-derived
    threshold whose 3-sigma ceiling is Rp15,100, so the D3 gate excluded EVERY
    rice deficit node and both beras commodities returned zero matches. On real
    data there are no anomaly exclusions at all, and matches go from 23 to 84.

    The synthetic fixture is still what 13 test files load directly, which is
    fine: it exercises engine logic across more commodities than the real data
    covers. It just must not be what users see.

    The Postgres path raises RuntimeError if SUPABASE_DB_URL is not set, so
    misconfiguration is loud rather than silent.
    """
    import os
    backend = os.environ.get("DATA_BACKEND", "csv").strip().lower()
    if backend == "postgres":
        from db.db_loader import load_all as _load_pg
        return _load_pg()
    if backend == "demo":
        return _load_csv()
    # Default: real BPS data (offline-safe)
    return _load_real()


from . import billing
from .auth import AuthUser, GatedUser, OptionalUser, RequireUser, auth_configured, require_auth_enabled
from .config import settings
from .gemini_client import GeminiClient
from .handlers import (
    MISSING_SLOT_PREFIX, OUT_OF_COVERAGE_PREFIX, EngineData, dispatch,
)
from .intent import (
    INTENT_ANOMALI, INTENT_CARI_PEMBELI, INTENT_CARI_PENJUAL,
    INTENT_FORECAST, INTENT_HARGA_LOOKUP, classify,
)
from .subscription import SubscriptionService, hash_phone
from .twilio_client import make_twiml_response, validate_signature


# Intents that consume free-tier quota. The fallback intent is excluded on
# purpose: a Gemini chit-chat answer is not the product, and charging for it
# would let a vague question burn the user's daily allowance.
METERED_INTENTS = frozenset({
    INTENT_HARGA_LOOKUP, INTENT_CARI_PEMBELI, INTENT_CARI_PENJUAL,
    INTENT_FORECAST, INTENT_ANOMALI,
})


# =============================================================================
# APP STATE — loaded once at startup
# =============================================================================

class AppState:
    data: EngineData | None = None
    gemini: GeminiClient | None = None
    subs: SubscriptionService | None = None
    orchestrator: "Orchestrator | None" = None


state = AppState()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Refuses to come up in APP_ENV=production while a demo default is still
    # active; logs the same findings as warnings in development.
    security.check_production_posture(settings)
    state.data = EngineData(_load_data_backend())
    state.gemini = GeminiClient()
    state.subs = SubscriptionService()
    yield
    # No teardown needed


# Swagger UI and the OpenAPI schema are a map of the attack surface. They
# stay on in development and go dark in production unless API_DOCS_ENABLED
# says otherwise (see config.Settings.api_docs_enabled).
app = FastAPI(
    title="AgriFlow WhatsApp Bot",
    version="0.1.0",
    description="Twilio webhook + Gemini RAG over the AgriFlow matching engine.",
    lifespan=lifespan,
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
)


def _cors_config() -> Dict[str, Any]:
    """
    Browser origins allowed to call /api/v1/*.

    The previous regex admitted every *.vercel.app and *.hf.space host, which
    is every Vercel and Hugging Face customer. The default is now the
    production dashboard plus this project's own preview URLs; anything else
    is opt-in through CORS_ALLOWED_ORIGINS (comma separated) and
    CORS_ALLOWED_ORIGIN_REGEX. Credentials are never allowed, so the browser
    only ever attaches the Authorization header the dashboard's own JS sets.
    """
    origins = [
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3001", "http://127.0.0.1:3001",
        "https://agriflow-engine.vercel.app",
    ]
    extra = os.environ.get("CORS_ALLOWED_ORIGINS", "")
    origins += [o.strip().rstrip("/") for o in extra.split(",") if o.strip()]
    regex = os.environ.get(
        "CORS_ALLOWED_ORIGIN_REGEX",
        r"^https://agriflow-engine(-[a-z0-9-]+)?\.vercel\.app$",
    )
    return {
        "allow_origins": origins,
        "allow_origin_regex": regex or None,
        "allow_methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Authorization", "Content-Type"],
        "allow_credentials": False,
        "max_age": 600,
    }


app.add_middleware(CORSMiddleware, **_cors_config())

# One JSON line per request on stderr, plus an X-Request-ID header so a user
# report ties back to an exact log line. Set AGRIFLOW_LOG_FILE to also archive
# the run to disk. Never logs phone numbers or request bodies.
request_log.install(app)

# Security headers, request body cap, and the per-IP rate limiter. Added after
# request_log so they wrap it and stamp even the 413/429 short-circuits.
security.install(app)


# =============================================================================
# CORE — pure function (no Twilio coupling), reused by /whatsapp and /chat
# =============================================================================

def _ensure_state() -> None:
    """Eager init for non-FastAPI callers (CLI, tests not using TestClient)."""
    if state.data is None:
        state.data = EngineData(_load_data_backend())
    if state.gemini is None:
        state.gemini = GeminiClient()
    if state.subs is None:
        state.subs = SubscriptionService()


def handle_message(message: str, sender: str | None = None) -> str:
    """
    Pure pipeline: text in → text out. Easy to unit-test.

    `sender` is the raw WhatsApp identifier ('whatsapp:+62...'). When it is
    absent the message is treated as anonymous and no quota is applied — that
    is the debug path (/chat, CLI). The Twilio webhook always passes a sender,
    so real users are always metered.

    Order of operations matters here:
      1. Billing/help commands run first and are never metered, so a user at
         their limit can still reach STATUS and UPGRADE.
      2. The quota check runs before dispatch, so an over-limit user gets the
         upgrade offer instead of an answer.
      3. Quota is consumed only *after* a metered intent produced a real
         answer, so incomplete questions cost nothing.
    """
    _ensure_state()
    assert state.data is not None and state.gemini is not None and state.subs is not None

    phone_hash = hash_phone(sender) if sender else ""

    # 1. Commands — free, and available even at zero remaining quota.
    #    Skipped entirely when the paywall is off: with no quota there is no
    #    billing surface, and a STATUS reply quoting a limit nobody enforces
    #    would be a lie.
    if settings.quota_enabled and phone_hash:
        command = billing.parse_command(message)
        if command is not None:
            return billing.handle_command(command, phone_hash, state.subs)

    intent = classify(
        message, state.gemini,
        state.data.kabupaten, state.data.komoditas,
    )
    metered = (
        settings.quota_enabled
        and bool(phone_hash)
        and intent.name in METERED_INTENTS
    )

    # 2. Paywall.
    if metered:
        decision = state.subs.check(phone_hash)
        if not decision.allowed:
            order = state.subs.start_upgrade(phone_hash)
            return billing.quota_exceeded(decision, order)

    reply = dispatch(intent, state.data, state.gemini)

    # 3. Bill only a query we actually answered. Asking the user to rephrase
    #    is free, and so is telling them a commodity is outside our data —
    #    neither delivered the thing they asked for.
    if metered and not reply.startswith((MISSING_SLOT_PREFIX, OUT_OF_COVERAGE_PREFIX)):
        state.subs.consume(phone_hash)

    return reply


# =============================================================================
# ROUTES
# =============================================================================

@app.get("/health")
async def health() -> Dict[str, Any]:
    data_loaded = state.data is not None
    if settings.is_production:
        # Liveness only. The configuration posture below (auth on or off,
        # salt present, mock flags) is exactly what an attacker would want to
        # read first, so production answers with the minimum an uptime probe
        # needs. Operators read the posture from the startup log instead.
        return {
            "status": "ok",
            "version": ENGINE_VERSION,
            "data_loaded": data_loaded,
        }
    return {
        "status": "ok",
        "version": ENGINE_VERSION,
        "engine_version": ENGINE_VERSION,
        "git_commit": _git_commit(),
        "allocator": _allocator_strategy(),
        "anomaly_gate": "batch_hampel_mad",
        "anomaly_method": ANOMALY_METHOD,
        "data_as_of": {
            "price_history_end": _price_history_end(),
            "bps_reference_year": BPS_REFERENCE_YEAR,
            "ipm_year": IPM_YEAR,
        },
        "mock_mode": settings.mock_mode,
        "data_loaded": data_loaded,
        "kabupaten_count": len(state.data.kabupaten) if data_loaded else 0,
        "komoditas_count": len(state.data.komoditas) if data_loaded else 0,
        "gemini_mock": state.gemini.mock if state.gemini else None,
        "auth_configured": auth_configured(),
        "require_auth": require_auth_enabled(),
        "quota_enabled": settings.quota_enabled,
        "free_daily_quota": settings.free_daily_quota,
        "quota_backend": settings.quota_backend,
        "billing_mock": settings.billing_mock,
        # Surfaced so a deployment check can catch an unsalted hash without
        # exposing the salt itself.
        "phone_hash_salted": bool(settings.phone_hash_salt),
    }


@app.post("/whatsapp")
async def whatsapp_webhook(
    request: Request,
    Body: str = Form(...),
    From: str = Form(...),
    x_twilio_signature: str | None = Header(default=None),
) -> Response:
    """
    Twilio WhatsApp webhook entrypoint.
    Body  — message text from user
    From  — 'whatsapp:+62xxx' sender
    Returns TwiML XML that Twilio will send back to the user.
    """
    # Optional signature validation — enable once webhook is reachable from Twilio
    if settings.twilio_validate_signature and not settings.mock_mode:
        form = await request.form()
        url = str(request.url)
        if not validate_signature(
            settings.twilio_auth_token, x_twilio_signature or "",
            url, form,
        ):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    if len(Body) > settings.max_message_chars:
        raise HTTPException(status_code=413, detail="message too long")
    reply = handle_message(Body, sender=From)
    return Response(content=make_twiml_response(reply), media_type="application/xml")


@app.post("/chat")
async def chat_debug(payload: Dict[str, str]) -> JSONResponse:
    """
    Debug endpoint — bypasses Twilio. Useful for local curl testing:
        curl -X POST localhost:8000/chat -H 'Content-Type: application/json' \\
             -d '{"message": "Harga cabai di Malang"}'

    Pass an optional "from" field to exercise the quota flow end to end:
             -d '{"message": "Harga cabai di Malang", "from": "whatsapp:+628123"}'

    WITHOUT "from" this endpoint is unmetered, so it bypasses the paywall by
    design. Set DEBUG_CHAT_ENABLED=false in any deployment where that matters —
    the Twilio webhook is the metered path, this one is a development tool.
    """
    if not settings.debug_chat_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    message = str(payload.get("message", "") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="message field required")
    if len(message) > settings.max_message_chars:
        raise HTTPException(status_code=413, detail="message too long")
    # The caller-supplied sender lets a test exercise the quota flow for an
    # arbitrary number. In production that is impersonation (STATUS, UPGRADE
    # and BAYAR run as whoever you name), so the field is ignored there and
    # the web chat is always anonymous.
    sender = None if settings.is_production else payload.get("from")
    reply = handle_message(message, sender=sender)
    return JSONResponse({"reply": reply})


# =============================================================================
# BILLING — upgrade flow
#
# The payment page and confirm endpoint form the gateway seam. In mock mode
# they are self-contained; to go live, point PUBLIC_BASE_URL's payment link at
# Midtrans/Xendit and have their webhook POST /billing/confirm with the order id
# after verifying the provider signature.
# =============================================================================

def _ensure_subs() -> SubscriptionService:
    if state.subs is None:
        state.subs = SubscriptionService()
    return state.subs


_ORDER_ID_RE = _re.compile(r"^AF-[0-9A-Fa-f]{8}$")


@app.get("/billing/pay/{order_id}")
async def billing_pay_page(order_id: str) -> Response:
    """
    Minimal payment page the WhatsApp link opens.

    In mock mode this renders a confirm button that settles the order. With a
    real gateway this route would instead redirect to the provider's hosted
    checkout for this order.
    """
    subs = _ensure_subs()
    # Order ids are minted as AF-<8 hex>. Anything else never hits the store.
    order = subs.store.get_order(order_id) if _ORDER_ID_RE.match(order_id) else None
    if order is None:
        return Response(
            content="<h1>Pesanan tidak ditemukan</h1>"
                    "<p>Silakan balas UPGRADE di WhatsApp untuk membuat pesanan baru.</p>",
            media_type="text/html", status_code=404,
        )

    amount = f"Rp {order.amount_idr:,.0f}".replace(",", ".")
    # Escaped even though the id is store-generated: the page is the only
    # HTML this API renders and the habit costs nothing.
    order_id = _html.escape(order.order_id)
    if order.status == "PAID":
        body = "<p class=ok>Pesanan ini sudah dibayar. Akun Anda sudah PRO.</p>"
    elif billing.billing_mock_enabled():
        body = (
            f"<form method='post' action='/billing/confirm'>"
            f"<input type='hidden' name='order_id' value='{order_id}'>"
            f"<button type='submit'>Bayar {amount} (demo)</button></form>"
            f"<p class=note>Mode demo — tidak ada transaksi sungguhan.</p>"
        )
    else:
        body = "<p class=note>Menunggu pengalihan ke penyedia pembayaran.</p>"

    return Response(
        content=(
            "<!doctype html><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>AgriFlow PRO</title>"
            "<style>body{font-family:system-ui,sans-serif;max-width:26rem;margin:3rem auto;"
            "padding:0 1rem;line-height:1.6}button{background:#15803d;color:#fff;border:0;"
            "padding:.8rem 1.4rem;border-radius:.5rem;font-size:1rem;cursor:pointer;width:100%}"
            ".note{color:#666;font-size:.9rem}.ok{color:#15803d;font-weight:600}</style>"
            f"<h1>AgriFlow PRO</h1><p>Pesanan <b>{order_id}</b><br>"
            f"Jumlah <b>{amount}</b> untuk 30 hari</p>{body}"
        ),
        media_type="text/html",
    )


@app.post("/billing/confirm")
async def billing_confirm(request: Request) -> Response:
    """
    Settle an order and grant PRO — the gateway webhook seam.

    Accepts either form-encoded (the mock page) or JSON (a webhook). A real
    integration MUST verify the provider's signature here before trusting the
    order id; right now anyone who knows an order id can settle it, which is
    acceptable only because mock mode charges nothing.
    """
    subs = _ensure_subs()
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        payload = await request.json()
        order_id = str(payload.get("order_id", ""))
    else:
        form = await request.form()
        order_id = str(form.get("order_id", ""))

    if not order_id:
        raise HTTPException(status_code=400, detail="order_id required")
    if not _ORDER_ID_RE.match(order_id):
        raise HTTPException(status_code=404, detail="unknown order")

    if not billing.billing_mock_enabled():
        raise HTTPException(
            status_code=501,
            detail="Live payment confirmation is not wired yet. "
                   "Implement provider signature verification before enabling.",
        )

    account = subs.confirm_payment(order_id)
    if account is None:
        raise HTTPException(status_code=404, detail="unknown order")

    if "application/json" in ctype:
        return JSONResponse({
            "status": "ok",
            "plan": account.plan,
            "expires_at": account.expires_at.isoformat() if account.expires_at else None,
        })
    return Response(
        content="<!doctype html><meta charset='utf-8'>"
                "<style>body{font-family:system-ui,sans-serif;max-width:26rem;"
                "margin:3rem auto;padding:0 1rem;line-height:1.6}</style>"
                "<h1>Pembayaran berhasil</h1>"
                "<p>Akun WhatsApp Anda sekarang PRO selama 30 hari. "
                "Silakan kembali ke WhatsApp dan lanjutkan bertanya.</p>",
        media_type="text/html",
    )


@app.get("/billing/status")
async def billing_status(
    phone: str = Query(..., description="WhatsApp number, e.g. +628123456789"),
    user: AuthUser = RequireUser,
) -> JSONResponse:
    """
    Plan + remaining quota for one number. Powers the dashboard account panel.

    The number is hashed before lookup and never stored by this call.
    """
    subs = _ensure_subs()
    phone_hash = hash_phone(phone)
    if not phone_hash:
        raise HTTPException(status_code=400, detail="invalid phone number")
    decision = subs.check(phone_hash)
    return JSONResponse({
        "plan": decision.account.plan,
        "is_pro": decision.account.is_pro,
        "expires_at": (
            decision.account.expires_at.isoformat()
            if decision.account.expires_at else None
        ),
        "used_today": decision.used_today,
        "limit": decision.limit,
        "remaining": decision.remaining,
    })


# =============================================================================
# DASHBOARD API — /api/v1/* (consumed by Next.js dashboard)
# =============================================================================

def _ensure_engine() -> EngineData:
    if state.data is None:
        state.data = EngineData(_load_data_backend())
    return state.data


# Cached full engine run.
#
# run_matching() is a pure function of the data loaded at startup, so re-running
# it per request was burning ~1.5 ms of CPU to recompute a byte-identical
# answer — about 60x the cost of everything else in the request and the binding
# constraint on how many concurrent users one worker can serve.
#
# The cache is keyed on the EngineData object itself (not id(), which a garbage
# collector can recycle onto a different object). Reloading data rebinds
# state.data to a new instance, which misses the cache and recomputes.
_matching_cache: Dict[str, Any] = {"data": None, "report": None, "strategy": None}


def _run_engine(
    data: "EngineData",
    *,
    surplus=None,
    deficit=None,
    logistics: Optional[LogisticsContext] = None,
    reference_date: Optional[_dt.datetime] = None,
    import_policy_active: bool = False,
    route_blackouts: Optional[List[RouteBlackout]] = None,
    force_strategy: Optional[str] = None,
):
    """
    One place that wires the v1.1 engine contract: batch anomaly gate on,
    LP allocator by default, same weather and price context as the cache.
    """
    return run_matching(
        surplus_nodes=data.surplus if surplus is None else surplus,
        deficit_nodes=data.deficit if deficit is None else deficit,
        logistics=logistics or LogisticsContext(),
        weather_forecasts=data.weather,
        historical_prices=data.historical,
        anomaly_keys=set(_anomaly_keys()),
        force_strategy=force_strategy or _allocator_strategy(),
        reference_date=reference_date,
        import_policy_active=import_policy_active,
        route_blackouts=route_blackouts,
    )


def _cached_report():
    data = _ensure_engine()
    strategy = _allocator_strategy()
    if _matching_cache["data"] is not data or _matching_cache["strategy"] != strategy:
        _matching_cache["report"] = _run_engine(data)
        _matching_cache["data"] = data
        _matching_cache["strategy"] = strategy
    return _matching_cache["report"]


def _resolve_city(value: Optional[str], data: "EngineData") -> Optional[str]:
    """
    Accept a kabupaten id ("3578") or a name ("Kota Surabaya", "surabaya",
    "Kab. Malang") and return the id, or None when nothing matches. Closes
    audit finding F7 (the forecast endpoint only took IHK codes).
    """
    if value is None:
        return None
    v = value.strip()
    if v in data.kabupaten:
        return v

    def norm(name: str) -> str:
        n = name.lower().strip()
        for prefix in ("kota ", "kab. ", "kab ", "kabupaten "):
            if n.startswith(prefix):
                n = n[len(prefix):]
        return n.strip()

    target = norm(v)
    exact_kota = None
    for k in data.kabupaten.values():
        if k.nama.lower().strip() == v.lower():
            return k.id
        if norm(k.nama) == target:
            # Prefer the kota when the user wrote "Kota X", else the kabupaten.
            if v.lower().startswith("kota"):
                if k.nama.lower().startswith("kota"):
                    return k.id
                exact_kota = exact_kota or k.id
            elif not k.nama.lower().startswith("kota"):
                return k.id
            else:
                exact_kota = exact_kota or k.id
    return exact_kota


def _commodities_payload() -> list:
    data = _ensure_engine()
    return [
        {"code": c.code, "nama": c.nama}
        for c in sorted(data.komoditas.values(), key=lambda c: c.nama)
    ]


@app.get("/api/v1/commodities")
async def api_commodities() -> JSONResponse:
    return JSONResponse(_commodities_payload())


def _kabupaten_payload() -> list:
    data = _ensure_engine()
    return [
        {
            "id": k.id, "nama": k.nama,
            "lat": k.latitude, "lng": k.longitude,
            "tier": k.tier.value, "ipm": k.ipm,
            "population": k.population,
        }
        for k in sorted(data.kabupaten.values(), key=lambda k: k.nama)
    ]


@app.get("/api/v1/kabupaten")
async def api_kabupaten() -> JSONResponse:
    return JSONResponse(_kabupaten_payload())


class ToolLookupError(Exception):
    """Raised by a payload builder for a bad argument, when called as a bot
    tool rather than an HTTP route. HTTP routes still raise HTTPException
    directly, which every payload builder below also does when called
    in-process from the route itself; whatsapp_bot/tools.py catches both,
    since a tool executor has no HTTP status code to return."""


def _surplus_deficit_payload(commodity: str) -> dict:
    """Per-kab surplus/deficit volume for one commodity. Powers the map
    bubbles (api_surplus_deficit) and the get_surplus_deficit bot tool."""
    data = _ensure_engine()
    if commodity not in data.komoditas:
        raise HTTPException(status_code=404, detail=f"unknown commodity: {commodity}")
    commo = data.komoditas[commodity]

    rows = []
    for s in data.surplus:
        if s.commodity.code != commodity:
            continue
        rows.append({
            "kab_id": s.kabupaten.id, "kab_nama": s.kabupaten.nama,
            "lat": s.kabupaten.latitude, "lng": s.kabupaten.longitude,
            "tier": s.kabupaten.tier.value,
            "role": "surplus",
            "volume_tons": s.volume_tons,
            "price_per_kg": s.price_per_kg,
        })
    for d in data.deficit:
        if d.commodity.code != commodity:
            continue
        rows.append({
            "kab_id": d.kabupaten.id, "kab_nama": d.kabupaten.nama,
            "lat": d.kabupaten.latitude, "lng": d.kabupaten.longitude,
            "tier": d.kabupaten.tier.value,
            "role": "deficit",
            "volume_tons": d.volume_tons,
            "price_per_kg": d.price_per_kg,
        })

    total_surplus = sum(r["volume_tons"] for r in rows if r["role"] == "surplus")
    total_deficit = sum(r["volume_tons"] for r in rows if r["role"] == "deficit")
    return {
        "commodity": {"code": commo.code, "nama": commo.nama},
        "rows": rows,
        "totals": {
            "surplus_tons": total_surplus,
            "deficit_tons": total_deficit,
            "balance_tons": total_surplus - total_deficit,
        },
    }


@app.get("/api/v1/surplus-deficit")
async def api_surplus_deficit(
    commodity: str = Query(..., description="Commodity code, e.g. cabai_merah"),
) -> JSONResponse:
    return JSONResponse(_surplus_deficit_payload(commodity))


def _price_lookup_payload(commodity: str, kabupaten: str) -> dict:
    """One row from _surplus_deficit_payload for a single kabupaten: the
    get_price bot tool. "Price" here is whichever side of the balance that
    kabupaten is on (producer price if surplus, consumer price if deficit),
    exactly like the dashboard's own median price cards on the Beranda tab."""
    data = _ensure_engine()
    kab_id = _resolve_city(kabupaten, data) or kabupaten
    payload = _surplus_deficit_payload(commodity)
    row = next((r for r in payload["rows"] if r["kab_id"] == kab_id), None)
    if row is None:
        raise ToolLookupError(
            f"Tidak ada data neraca {commodity} untuk kabupaten/kota {kabupaten!r}. "
            f"Kemungkinan kabupaten tidak dikenali, atau komoditas ini tidak "
            f"terdaftar defisit maupun surplus di sana menurut neraca BPS."
        )
    return {"commodity": payload["commodity"], **row}


def _serialize_match(m) -> Dict[str, Any]:
    return {
        "surplus": {
            "kab_id": m.surplus.kabupaten.id,
            "kab_nama": m.surplus.kabupaten.nama,
            "lat": m.surplus.kabupaten.latitude,
            "lng": m.surplus.kabupaten.longitude,
            "price_per_kg": m.surplus.price_per_kg,
        },
        "deficit": {
            "kab_id": m.deficit.kabupaten.id,
            "kab_nama": m.deficit.kabupaten.nama,
            "lat": m.deficit.kabupaten.latitude,
            "lng": m.deficit.kabupaten.longitude,
            "price_per_kg": m.deficit.price_per_kg,
        },
        "commodity_code": m.surplus.commodity.code,
        "commodity_nama": m.surplus.commodity.nama,
        "matched_volume_tons": m.matched_volume_tons,
        "distance_km": m.distance_km,
        "final_score": m.final_score,
        "confidence": m.confidence.value,
        "flags": list(m.flags),
        # v1.1: explainability. ScoreBreakdown has been computed since v9 but
        # never left the process; the dashboard renders these bars.
        "base_score": round(m.base_score, 2),
        "equity_multiplier": m.equity_multiplier,
        "segment_multiplier": m.segment_multiplier,
        "deficit_ipm": m.deficit.kabupaten.ipm,
        "breakdown": {
            "distance": round(m.breakdown.distance, 4),
            "volume": round(m.breakdown.volume, 4),
            "price": round(m.breakdown.price, 4),
            "perishability": round(m.breakdown.perishability, 4),
            "climate": round(m.breakdown.climate, 4),
        },
        "price_spread_idr_per_kg": round(
            m.deficit.price_per_kg - m.surplus.price_per_kg, 2
        ),
        "gross_arbitrage_idr": round(
            max(0.0, m.deficit.price_per_kg - m.surplus.price_per_kg)
            * m.matched_volume_tons * 1000, 0
        ),
        "notes": m.notes,
        "why": _explain_match(m),
    }


def _explain_match(m) -> List[str]:
    """Short Indonesian sentences a Pemda officer can read on the card."""
    out: List[str] = []
    b = m.breakdown
    out.append(
        f"Skor {m.final_score:.0f} = base {m.base_score:.0f} × equity "
        f"{m.equity_multiplier:.2f} (IPM {m.deficit.kabupaten.nama} {m.deficit.kabupaten.ipm:.1f})"
        + (f" × segmen {m.segment_multiplier:.2f}" if m.segment_multiplier != 1.0 else "")
    )
    out.append(f"Jarak jalan {m.distance_km:.0f} km (skor jarak {b.distance:.2f})")
    out.append(f"Volume menutup {b.volume * 100:.0f}% kebutuhan {m.deficit.kabupaten.nama}")
    spread = m.deficit.price_per_kg - m.surplus.price_per_kg
    out.append(
        f"Selisih harga Rp {spread:,.0f}/kg (skor harga {b.price:.2f})".replace(",", ".")
    )
    out.append(
        f"Sisa masa simpan cukup (skor perishability {b.perishability:.2f}); "
        f"iklim rute {b.climate:.2f}" + (" (tanpa data cuaca, netral)" if abs(b.climate - 0.7) < 1e-9 else "")
    )
    if m.equity_multiplier > 1.0:
        out.append("Kabupaten penerima tertinggal (IPM rendah) mendapat prioritas equity")
    return out


def _matches_payload(
    commodity: Optional[str] = None, kab_id: Optional[str] = None,
    limit: int = 50, *, side: Optional[str] = None,
) -> dict:
    """Scored matches for the map flow lines and side panel (api_matches),
    the find_buyers / find_suppliers bot tools (side="surplus"/"deficit"
    narrows kab_id to one side instead of either), and run_whatif's baseline
    view. `side` has no HTTP equivalent; every route caller leaves it None."""
    report = _cached_report()

    # Copy before sorting. `report.matches` is the shared cached list, and an
    # unfiltered request would otherwise sort it in place under every other
    # concurrent caller.
    matches = list(report.matches)
    if commodity:
        matches = [m for m in matches if m.surplus.commodity.code == commodity]
    if kab_id:
        if side == "surplus":
            matches = [m for m in matches if m.surplus.kabupaten.id == kab_id]
        elif side == "deficit":
            matches = [m for m in matches if m.deficit.kabupaten.id == kab_id]
        else:
            matches = [
                m for m in matches
                if m.surplus.kabupaten.id == kab_id or m.deficit.kabupaten.id == kab_id
            ]
    matches.sort(key=lambda m: m.final_score, reverse=True)
    matches = matches[:limit]
    return {
        "count": len(matches),
        "matches": [_serialize_match(m) for m in matches],
    }


@app.get("/api/v1/matches")
async def api_matches(
    user: AuthUser | None = GatedUser,
    commodity: str | None = Query(None, description="Filter by commodity code"),
    kab_id: str | None = Query(None, description="Filter where this kab is surplus OR deficit side"),
    limit: int = Query(50, ge=1, le=500),
) -> JSONResponse:
    return JSONResponse(_matches_payload(commodity, kab_id, limit))


def _find_buyers_payload(commodity: str, kabupaten_origin: str, volume_tons: Optional[float] = None) -> dict:
    """Who the allocator actually matched this surplus kabupaten's output
    to, i.e. "I have supply in X, who is buying it". Reuses the engine's own
    committed matches rather than a fresh candidate search, so the answer is
    the allocation that is actually running, not a hypothetical one."""
    data = _ensure_engine()
    kab_id = _resolve_city(kabupaten_origin, data) or kabupaten_origin
    payload = _matches_payload(commodity, kab_id, limit=20, side="surplus")
    if not payload["matches"]:
        raise ToolLookupError(
            f"Tidak ada pembeli yang dicocokkan engine untuk {commodity} dari "
            f"{kabupaten_origin!r}. Kemungkinan kabupaten ini bukan sisi surplus "
            f"untuk komoditas itu, atau semua penerima sudah tertutup pemasok lain."
        )
    return {"commodity": commodity, "kabupaten_origin": kab_id,
            "volume_tons_requested": volume_tons, **payload}


# =============================================================================
# FORECAST + ANOMALY API  --  /api/v1/forecast  and  /api/v1/anomalies
#
# Both endpoints serve precomputed JSON files that were generated offline by:
#   python analysis/precompute_anomalies.py
#   python analysis/forecast_timesfm.py
#
# The server NEVER imports timesfm at runtime (HF Space OOM guard).
# =============================================================================

import json as _json
import functools


@functools.lru_cache(maxsize=1)
def _load_forecasts() -> list:
    """Load forecast_all.json once and cache in-process."""
    if not os.path.exists(_FORECASTS_PATH):
        return []
    with open(_FORECASTS_PATH, encoding="utf-8") as fh:
        return _json.load(fh)


@functools.lru_cache(maxsize=1)
def _load_anomalies() -> list:
    """Load anomalies_all.json once and cache in-process.

    The source-aware scan (schema v2+) stores the flat event records under an
    "events" key alongside series_statuses; older scans were a bare list.
    Return the event list either way so callers can treat it as a list.
    """
    if not os.path.exists(_ANOMALIES_PATH):
        return []
    with open(_ANOMALIES_PATH, encoding="utf-8") as fh:
        data = _json.load(fh)
    if isinstance(data, dict):
        return data.get("events", [])
    return data


def _forecast_payload(commodity: str, city: str) -> dict:
    """
    30-day price forecast (point + P10/P90) for one commodity × city pair.

    Data is precomputed offline (seasonal-naive baseline unless TimesFM was
    available at precompute time). The 'method' field in the response tells
    you which model was used. `city` accepts an IHK code or a kabupaten name.

    Response schema:
        commodity_code   str
        city_id          str
        city_name        str
        method           str  ("timesfm_2.0" | "seasonal_naive_baseline")
        generated_at     str  ISO 8601
        horizon_days     int
        history_end_date str  ISO 8601
        forecasts        list of {date, point, p10, p90}
    """
    records = _load_forecasts()
    if not records:
        raise HTTPException(
            status_code=503,
            detail=(
                "Forecast data not yet precomputed.  "
                "Run: python analysis/forecast_timesfm.py"
            ),
        )
    # v1.1 (audit F7): accept a city name as well as the IHK code.
    resolved = _resolve_city(city, _ensure_engine())
    if resolved:
        city = resolved
    match = next(
        (r for r in records if r["commodity_code"] == commodity and r["city_id"] == city),
        None,
    )
    if match is None:
        # List available (commodity, city) pairs so caller can self-correct
        available = sorted({(r["commodity_code"], r["city_id"]) for r in records})
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"No forecast for commodity={commodity!r} city={city!r}",
                "available_pairs": [{"commodity": c, "city": ci} for c, ci in available[:20]],
            },
        )
    return match


@app.get("/api/v1/forecast")
async def api_forecast(
    user: AuthUser | None = GatedUser,
    commodity: str = Query(..., description="Commodity code, e.g. cabai_rawit"),
    city: str = Query(..., description="IHK city_id, e.g. 3578 (Surabaya)"),
) -> JSONResponse:
    return JSONResponse(_forecast_payload(commodity, city))


def _anomalies_payload(
    commodity: Optional[str] = None, city: Optional[str] = None,
    limit: int = 50, since: Optional[str] = None,
) -> dict:
    """
    Detected price anomalies from the Hampel/MAD scanner (precomputed
    offline). All filters are optional; without filters, returns top-N by
    score. `city` accepts an IHK code or a kabupaten name.

    Response schema:
        count     int
        method    str
        anomalies list of {
            date, price, rolling_median, deviation_pct (+spike/-drop),
            type (SPIKE|DROP), score, commodity_code, city_id, city_name,
            persistent (bool)
        }
    """
    records = _load_anomalies()
    if not records:
        raise HTTPException(
            status_code=503,
            detail=(
                "Anomaly data not yet precomputed.  "
                "Run: python analysis/precompute_anomalies.py"
            ),
        )

    filtered = records
    if commodity:
        filtered = [r for r in filtered if r["commodity_code"] == commodity]
    if city:
        city = _resolve_city(city, _ensure_engine()) or city
        filtered = [r for r in filtered if r["city_id"] == city]
    if since:
        filtered = [r for r in filtered if r["date"] >= since]

    # Already sorted by score desc in the precomputed file; slice to limit
    filtered = filtered[:limit]

    return {
        "count":     len(filtered),
        "method":    ANOMALY_METHOD,
        "anomalies": filtered,
    }


@app.get("/api/v1/anomalies")
async def api_anomalies(
    user: AuthUser | None = GatedUser,
    commodity: str | None = Query(None, description="Filter by commodity code"),
    city: str | None = Query(None, description="Filter by IHK city_id"),
    limit: int = Query(50, ge=1, le=500, description="Max records returned (sorted by score desc)"),
    since: str | None = Query(None, description="ISO date lower-bound, e.g. 2024-01-01"),
) -> JSONResponse:
    return JSONResponse(_anomalies_payload(commodity, city, limit, since))


# =============================================================================
# v1.1 — META, SUMMARY, REPORT, EXPLAIN, SIMULATE
# =============================================================================

@_functools.lru_cache(maxsize=1)
def _load_anomaly_meta() -> dict:
    if not os.path.exists(_ANOMALIES_META_PATH):
        return {}
    with open(_ANOMALIES_META_PATH, encoding="utf-8") as fh:
        return _json.load(fh)


def _meta_payload() -> dict:
    """
    "Data per" for every panel, and the get_data_freshness bot tool.
    Everything here is read from the artefacts the server actually serves,
    so neither the dashboard nor the bot can claim freshness the data does
    not have.
    """
    data = _ensure_engine()
    forecasts = _load_forecasts()
    fc_generated = sorted({r.get("generated_at", "") for r in forecasts}) if forecasts else []
    fc_hist_end = sorted({r.get("history_end_date", "") for r in forecasts}) if forecasts else []
    interval_methods = sorted({r.get("interval_method", "same_month_mad") for r in forecasts}) if forecasts else []
    report = _cached_report()
    return {
        "engine_version": ENGINE_VERSION,
        "git_commit": _git_commit(),
        "data_backend": os.environ.get("DATA_BACKEND", "csv"),
        "allocator": report.run_metadata.get("allocator"),
        "anomaly_gate": report.run_metadata.get("anomaly_gate"),
        "anomaly_method": ANOMALY_METHOD,
        "anomaly_gate_window_days": _anomaly_window_days(),
        "anomaly_gate_active_pairs": len(_anomaly_keys()),
        "data_as_of": {
            "price_history_end": _price_history_end(),
            "anomaly_scan_generated_at": _load_anomaly_meta().get("generated_at"),
            "anomaly_last_date": (latest_anomaly_date(_ANOMALIES_PATH) or _dt.date(1970, 1, 1)).isoformat()
                                  if os.path.exists(_ANOMALIES_PATH) else None,
            "forecast_generated_at": fc_generated[-1] if fc_generated else None,
            "forecast_history_end": fc_hist_end[-1] if fc_hist_end else None,
            "forecast_interval_methods": interval_methods,
            "bps_reference_year": BPS_REFERENCE_YEAR,
            "ipm_year": IPM_YEAR,
            "road_distance": ROAD_DISTANCE_SOURCE,
        },
        "coverage": {
            "kabupaten": len(data.kabupaten),
            "commodities": sorted(c.code for c in data.komoditas.values()),
            "forecast_series": len(forecasts),
            "matches": len(report.matches),
        },
        "engine_run": {
            k: report.run_metadata.get(k)
            for k in ("latency_ms", "welfare", "welfare_greedy", "welfare_gain_pct",
                      "matched_tons", "candidate_pairs_evaluated", "active_event")
        },
    }


@app.get("/api/v1/meta")
async def api_meta() -> JSONResponse:
    return JSONResponse(_meta_payload())


def _summary_for(report, data: "EngineData", commodity: Optional[str] = None) -> Dict[str, Any]:
    """KPIs computed from the engine run, never typed in by hand."""
    codes = [commodity] if commodity else sorted({c.code for c in data.komoditas.values()})
    per: Dict[str, Any] = {}
    tot_sup = tot_def = tot_matched = tot_arb = 0.0
    tot_matches = 0
    for code in codes:
        sup = [s for s in data.surplus if s.commodity.code == code]
        dem = [d for d in data.deficit if d.commodity.code == code]
        ms = [m for m in report.matches if m.deficit.commodity.code == code]
        sup_t = sum(s.volume_tons for s in sup)
        def_t = sum(d.volume_tons for d in dem)
        matched = sum(m.matched_volume_tons for m in ms)
        arb = sum(max(0.0, m.deficit.price_per_kg - m.surplus.price_per_kg)
                  * m.matched_volume_tons * 1000 for m in ms)
        low_ipm_def = [d for d in dem if d.kabupaten.ipm < 68]
        low_ipm_def_t = sum(d.volume_tons for d in low_ipm_def)
        low_ipm_matched = sum(
            m.matched_volume_tons for m in ms if m.deficit.kabupaten.ipm < 68
        )
        matched_def_ids = {m.deficit.kabupaten.id for m in ms}
        per[code] = {
            "surplus_tons": round(sup_t, 1),
            "deficit_tons": round(def_t, 1),
            "matched_tons": round(matched, 1),
            "coverage_pct": round(matched / def_t * 100, 1) if def_t else None,
            "n_matches": len(ms),
            "n_surplus_kab": len(sup),
            "n_deficit_kab": len(dem),
            "gross_arbitrage_idr": round(arb, 0),
            "equity_boosted_matches": sum(1 for m in ms if m.equity_multiplier > 1.0),
            "low_ipm_deficit_fulfillment_pct": (
                round(low_ipm_matched / low_ipm_def_t * 100, 1) if low_ipm_def_t else None
            ),
            "unmatched_deficit_kab": sorted(
                d.kabupaten.nama for d in dem if d.kabupaten.id not in matched_def_ids
            ),
        }
        tot_sup += sup_t; tot_def += def_t; tot_matched += matched; tot_arb += arb
        tot_matches += len(ms)
    return {
        "per_commodity": per,
        "totals": {
            "surplus_tons": round(tot_sup, 1),
            "deficit_tons": round(tot_def, 1),
            "matched_tons": round(tot_matched, 1),
            "coverage_pct": round(tot_matched / tot_def * 100, 1) if tot_def else None,
            "n_matches": tot_matches,
            "gross_arbitrage_idr": round(tot_arb, 0),
        },
        "engine": {
            "allocator": report.run_metadata.get("allocator"),
            "welfare": report.run_metadata.get("welfare"),
            "welfare_gain_pct_vs_greedy": report.run_metadata.get("welfare_gain_pct"),
            "latency_ms": report.run_metadata.get("latency_ms"),
            "anomaly_gate": report.run_metadata.get("anomaly_gate"),
        },
    }


def _summary_payload(commodity: Optional[str] = None) -> dict:
    """Real KPIs for the Beranda and Laporan pages, and the get_summary bot
    tool, from the cached engine run."""
    data = _ensure_engine()
    if commodity and commodity not in data.komoditas:
        raise HTTPException(status_code=404, detail=f"unknown commodity: {commodity}")
    return {
        "data_as_of": {
            "price_history_end": _price_history_end(),
            "bps_reference_year": BPS_REFERENCE_YEAR,
        },
        **_summary_for(_cached_report(), data, commodity),
    }


@app.get("/api/v1/summary")
async def api_summary(
    user: AuthUser | None = GatedUser,
    commodity: Optional[str] = Query(None),
) -> JSONResponse:
    return JSONResponse(_summary_payload(commodity))


def _csv_safe_cell(value: Any) -> Any:
    """
    Neutralise spreadsheet formula injection. A cell that starts with =, +, -
    or @ is executed by Excel and LibreOffice when the file is opened; a
    leading apostrophe makes it display as text. Numbers pass through as-is.
    """
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _csv_safe_row(row: List[Any]) -> List[Any]:
    return [_csv_safe_cell(v) for v in row]


_REPORT_COLUMNS = [
    "commodity_code", "commodity_nama", "surplus_kab_id", "surplus_kab", "deficit_kab_id",
    "deficit_kab", "deficit_ipm", "matched_volume_tons", "distance_km", "surplus_price_idr_kg",
    "deficit_price_idr_kg", "price_spread_idr_kg", "gross_arbitrage_idr", "base_score",
    "equity_multiplier", "final_score", "confidence", "flags",
]


@app.get("/api/v1/report.csv")
async def api_report_csv(
    user: AuthUser | None = GatedUser,
    commodity: Optional[str] = Query(None),
) -> Response:
    """Downloadable match list. Replaces the simulated download buttons."""
    data = _ensure_engine()
    report = _cached_report()
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(_REPORT_COLUMNS)
    for m in sorted(report.matches, key=lambda x: -x.final_score):
        if commodity and m.deficit.commodity.code != commodity:
            continue
        spread = m.deficit.price_per_kg - m.surplus.price_per_kg
        w.writerow(_csv_safe_row([
            m.surplus.commodity.code, m.surplus.commodity.nama,
            m.surplus.kabupaten.id, m.surplus.kabupaten.nama,
            m.deficit.kabupaten.id, m.deficit.kabupaten.nama, m.deficit.kabupaten.ipm,
            round(m.matched_volume_tons, 2), round(m.distance_km, 1),
            m.surplus.price_per_kg, m.deficit.price_per_kg, round(spread, 2),
            round(max(0.0, spread) * m.matched_volume_tons * 1000, 0),
            round(m.base_score, 2), m.equity_multiplier, round(m.final_score, 2),
            m.confidence.value, "|".join(m.flags),
        ]))
    stamp = (_price_history_end() or "data").replace("-", "")
    name = f"agriflow_matches_{commodity or 'all'}_{stamp}.csv"
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


def _explain_payload(deficit_kab_id: str, commodity: str, limit: int = 5) -> dict:
    """
    Rank every viable supplier for one deficit with the same score function the
    engine used, and mark which ones the allocator actually chose. This is the
    "why this match, and why not the next one" panel (api_explain), and the
    explain_match and find_suppliers bot tools (find_suppliers is exactly
    this question asked from the buyer's side: "who could supply me").
    """
    data = _ensure_engine()
    deficit_kab_id = _resolve_city(deficit_kab_id, data) or deficit_kab_id
    dem = [d for d in data.deficit
           if d.kabupaten.id == deficit_kab_id and d.commodity.code == commodity]
    if not dem:
        raise HTTPException(status_code=404, detail="no deficit node for that kabupaten and commodity")
    report = _cached_report()
    weights = report.run_metadata.get("weights_used") or _scoring.DEFAULT_WEIGHTS
    keys = set(_anomaly_keys())
    sup = [s for s in data.surplus if s.commodity.code == commodity
           and (s.kabupaten.id, s.commodity.code) not in keys]
    cands = generate_candidates(sup, dem, logistics=LogisticsContext(), top_k_per_surplus=1000)
    chosen = {
        m.surplus.kabupaten.id: m.matched_volume_tons
        for m in report.matches
        if m.deficit.kabupaten.id == deficit_kab_id and m.deficit.commodity.code == commodity
    }
    ranked = []
    for s, d in cands:
        wf = data.weather.get(f"{s.kabupaten.id}_{d.kabupaten.id}")
        breakdown, base, dist = _scoring.compute_score(
            s, d, logistics=LogisticsContext(), weather=wf, weights=weights,
        )
        eq = equity_multiplier_value(d.kabupaten.ipm)
        seg, _f = segment_multiplier_value(s, d)
        ranked.append({
            "surplus_kab_id": s.kabupaten.id,
            "surplus_kab": s.kabupaten.nama,
            "available_tons": s.volume_tons,
            "distance_km": round(dist, 1),
            "base_score": round(base, 2),
            "equity_multiplier": eq,
            "final_score": round(base * eq * seg, 2),
            "breakdown": {
                "distance": round(breakdown.distance, 4), "volume": round(breakdown.volume, 4),
                "price": round(breakdown.price, 4), "perishability": round(breakdown.perishability, 4),
                "climate": round(breakdown.climate, 4),
            },
            "chosen": s.kabupaten.id in chosen,
            "allocated_tons": round(chosen.get(s.kabupaten.id, 0.0), 2),
        })
    ranked.sort(key=lambda r: -r["final_score"])
    d0 = dem[0]
    return {
        "deficit": {"kab_id": d0.kabupaten.id, "kab_nama": d0.kabupaten.nama,
                    "ipm": d0.kabupaten.ipm, "volume_tons": d0.volume_tons,
                    "price_per_kg": d0.price_per_kg, "commodity_code": commodity},
        "weights_used": weights,
        "allocator": report.run_metadata.get("allocator"),
        "n_viable_suppliers": len(ranked),
        "ranking": ranked[:limit],
        "reason_not_chosen": (
            "Allocator LP memaksimalkan welfare total berbobot equity, jadi pemasok "
            "berskor tinggi bisa dialihkan ke defisit lain bila itu menaikkan total; "
            "lihat kolom allocated_tons."
            if report.run_metadata.get("allocator") == "lp_optimal" else
            "Greedy memilih pemasok berskor tertinggi yang masih punya sisa volume, "
            "diurutkan dari defisit ber-IPM terendah."
        ),
    }


@app.get("/api/v1/matches/explain")
async def api_explain(
    user: AuthUser | None = GatedUser,
    deficit_kab_id: str = Query(..., description="Kabupaten id on the receiving side"),
    commodity: str = Query(...),
    limit: int = Query(5, ge=1, le=20),
) -> JSONResponse:
    return JSONResponse(_explain_payload(deficit_kab_id, commodity, limit))


# --- what-if simulator -------------------------------------------------------

SCENARIO_PRESETS: Dict[str, Dict[str, Any]] = {
    "semeru": {
        "label": "Erupsi Semeru: Lumajang tidak terjangkau",
        "unreachable_kab": ["3508"],
    },
    "banjir_sentra_padi": {
        "label": "Banjir La Nina: Ngawi, Madiun, Bojonegoro tidak terjangkau",
        "unreachable_kab": ["3521", "3519", "3522"],
    },
    "banjir_madura": {
        "label": "Banjir Madura: empat kabupaten status humanitarian",
        "humanitarian_kab": ["3526", "3527", "3528", "3529"],
    },
    "ramadan": {"label": "H-14 Idul Fitri: profil bobot Ramadan", "ramadan": True},
    "bbm_20": {"label": "BBM naik 20%: radius viable menyusut", "bbm_pct": 20.0},
    "impor": {"label": "Kebijakan impor aktif: bobot harga turun", "import_policy": True},
    "suramadu_tutup": {
        "label": "Jembatan Suramadu ditutup: rute dari dan ke Madura diblokir",
        "blackout_kab": ["3526", "3527", "3528", "3529"],
    },
}


# Every field bounded: the endpoint re-runs the LP solver per call, so an
# unbounded list or a bbm_pct of 1e308 (infinite fuel cost) is a cheap way to
# stall a worker or crash the solver.
_KabList = List[Annotated[str, Field(min_length=1, max_length=16)]]


class SimulateRequest(BaseModel):
    presets: List[Annotated[str, Field(max_length=32)]] = Field(default_factory=list, max_length=10)
    unreachable_kab: _KabList = Field(default_factory=list, max_length=100)
    humanitarian_kab: _KabList = Field(default_factory=list, max_length=100)
    blackout_kab: _KabList = Field(default_factory=list, max_length=100)
    ramadan: bool = False
    bbm_pct: float = Field(0.0, ge=-90.0, le=1000.0)
    import_policy: bool = False
    commodity: Optional[str] = Field(None, max_length=64)
    reference_date: Optional[str] = Field(None, max_length=40)
    allocator: Optional[str] = Field(None, pattern=r"^(lp|greedy|stable)$")
    limit: int = Field(50, ge=1, le=500)


def _apply_scenario(data: "EngineData", req: SimulateRequest):
    unreachable: Set[str] = set(req.unreachable_kab)
    humanitarian: Set[str] = set(req.humanitarian_kab)
    blackout_kab: Set[str] = set(req.blackout_kab)
    ramadan = req.ramadan
    bbm_pct = req.bbm_pct
    import_policy = req.import_policy
    labels: List[str] = []
    for p in req.presets:
        preset = SCENARIO_PRESETS.get(p)
        if preset is None:
            raise HTTPException(status_code=400, detail=f"unknown preset: {p}; "
                                f"available: {sorted(SCENARIO_PRESETS)}")
        labels.append(preset["label"])
        unreachable |= set(preset.get("unreachable_kab", []))
        humanitarian |= set(preset.get("humanitarian_kab", []))
        blackout_kab |= set(preset.get("blackout_kab", []))
        ramadan = ramadan or preset.get("ramadan", False)
        bbm_pct = max(bbm_pct, preset.get("bbm_pct", 0.0))
        import_policy = import_policy or preset.get("import_policy", False)

    def patched_kab(k):
        if k.id in unreachable:
            return dataclasses.replace(k, emergency_mode=EmergencyMode.UNREACHABLE)
        if k.id in humanitarian:
            return dataclasses.replace(k, emergency_mode=EmergencyMode.HUMANITARIAN)
        return k

    surplus = [dataclasses.replace(s, kabupaten=patched_kab(s.kabupaten)) for s in data.surplus]
    deficit = [dataclasses.replace(d, kabupaten=patched_kab(d.kabupaten)) for d in data.deficit]

    logistics = LogisticsContext(
        bbm_price_idr_per_liter=10000.0 * (1 + bbm_pct / 100.0),
        bbm_price_baseline=10000.0,
        is_ramadan_proximity=ramadan,
    )
    blackouts: List[RouteBlackout] = []
    if blackout_kab:
        far_past, far_future = _dt.datetime(2000, 1, 1), _dt.datetime(2100, 1, 1)
        for kid in blackout_kab:
            blackouts.append(RouteBlackout("*", kid, far_past, far_future, "SCENARIO_BLACKOUT"))
            blackouts.append(RouteBlackout(kid, "*", far_past, far_future, "SCENARIO_BLACKOUT"))
    ref = None
    if req.reference_date:
        try:
            ref = _dt.datetime.fromisoformat(req.reference_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="reference_date must be ISO 8601")
    return surplus, deficit, logistics, blackouts, ref, import_policy, labels, {
        "unreachable_kab": sorted(unreachable), "humanitarian_kab": sorted(humanitarian),
        "blackout_kab": sorted(blackout_kab), "ramadan": ramadan, "bbm_pct": bbm_pct,
        "import_policy": import_policy,
    }


def _match_key(m) -> Tuple[str, str, str]:
    return (m.surplus.kabupaten.id, m.deficit.kabupaten.id, m.deficit.commodity.code)


def _simulate_payload(req: SimulateRequest) -> dict:
    """
    Re-run the engine under a what-if scenario and diff it against the served
    baseline (api_simulate, and the run_whatif bot tool). The 25 scenarios in
    tests/ become something a judge, or a farmer on WhatsApp, can trigger.
    """
    data = _ensure_engine()
    if req.commodity and req.commodity not in data.komoditas:
        raise HTTPException(status_code=404, detail=f"unknown commodity: {req.commodity}")
    surplus, deficit, logistics, blackouts, ref, import_policy, labels, applied = _apply_scenario(data, req)
    baseline = _cached_report()
    scenario = _run_engine(
        data, surplus=surplus, deficit=deficit, logistics=logistics,
        reference_date=ref, import_policy_active=import_policy,
        route_blackouts=blackouts or None, force_strategy=req.allocator,
    )

    def view(report):
        ms = report.matches
        if req.commodity:
            ms = [m for m in ms if m.deficit.commodity.code == req.commodity]
        return ms

    base_ms, scen_ms = view(baseline), view(scenario)
    base_keys = {_match_key(m): m for m in base_ms}
    scen_keys = {_match_key(m): m for m in scen_ms}
    removed = [base_keys[k] for k in base_keys.keys() - scen_keys.keys()]
    added = [scen_keys[k] for k in scen_keys.keys() - base_keys.keys()]

    base_sum = _summary_for(baseline, data, req.commodity)["totals"]
    scen_sum = _summary_for(scenario, data, req.commodity)["totals"]

    return {
        "scenario": {"labels": labels, "applied": applied,
                     "allocator": scenario.run_metadata.get("allocator"),
                     "active_event": scenario.run_metadata.get("active_event"),
                     "weights_used": scenario.run_metadata.get("weights_used")},
        "baseline": base_sum,
        "result": scen_sum,
        "delta": {
            "matched_tons": round(scen_sum["matched_tons"] - base_sum["matched_tons"], 1),
            "coverage_pct": (round(scen_sum["coverage_pct"] - base_sum["coverage_pct"], 1)
                             if scen_sum["coverage_pct"] is not None and base_sum["coverage_pct"] is not None else None),
            "n_matches": scen_sum["n_matches"] - base_sum["n_matches"],
            "welfare": round((scenario.run_metadata.get("welfare") or 0) - (baseline.run_metadata.get("welfare") or 0), 2),
            "latency_ms": scenario.run_metadata.get("latency_ms"),
        },
        "removed_matches": [_serialize_match(m) for m in sorted(removed, key=lambda m: -m.final_score)[:req.limit]],
        "added_matches": [_serialize_match(m) for m in sorted(added, key=lambda m: -m.final_score)[:req.limit]],
        "matches": [_serialize_match(m) for m in sorted(scen_ms, key=lambda m: -m.final_score)[:req.limit]],
        "warnings": scenario.warnings[:30],
        "external_opportunities": scenario.external_opportunities[:10],
    }


@app.post("/api/v1/simulate")
async def api_simulate(req: SimulateRequest, user: AuthUser | None = GatedUser) -> JSONResponse:
    return JSONResponse(_simulate_payload(req))


def _presets_payload() -> dict:
    return {k: v["label"] for k, v in SCENARIO_PRESETS.items()}


@app.get("/api/v1/simulate/presets")
async def api_simulate_presets() -> JSONResponse:
    return JSONResponse(_presets_payload())


# --- price history (for the forecast chart's context window) ----------------

@_functools.lru_cache(maxsize=1)
def _price_series_map():
    """(commodity_code, city_id) -> [(date, price)] from the active source-aware series (Siskaperbapo first, PIHPS fallback)."""
    from collections import defaultdict
    from db.price_ingest import load_source_price_history_csvs, select_active_prices
    try:
        source_records = load_source_price_history_csvs(_PRICE_HISTORY_DIR)
        active_records = select_active_prices(source_records)
        series_map = defaultdict(list)
        for record in active_records:
            key = (record["commodity_code"], str(record["city_id"]))
            series_map[key].append((record["date"], float(record["price_per_kg"])))
        for pts in series_map.values():
            pts.sort(key=lambda x: x[0])
        return dict(series_map)
    except FileNotFoundError:
        return {}


def _price_history_payload(commodity: str, city: str, days: int = 90) -> dict:
    """
    Observed daily prices for one commodity x city, last `days` days
    (api_price_history, and the get_price_history bot tool). Lets the
    dashboard, and the bot, draw history and forecast on one axis instead of
    a bare 30-day line.
    """
    data = _ensure_engine()
    city_id = _resolve_city(city, data) or city
    series = _price_series_map().get((commodity, city_id))
    if not series:
        available = sorted({c for (_c, c) in _price_series_map().keys()})
        raise HTTPException(status_code=404, detail={
            "error": f"No price history for commodity={commodity!r} city={city!r}",
            "available_cities": available,
        })
    tail = series[-days:]
    return {
        "commodity_code": commodity,
        "city_id": city_id,
        "city_name": data.kabupaten[city_id].nama if city_id in data.kabupaten else city_id,
        "source": "SISKAPERBAPO-first + PIHPS (sample_data/price_history)",
        "history_end_date": series[-1][0].isoformat(),
        "n": len(tail),
        "points": [{"date": d.isoformat(), "price": round(float(p), 2)} for d, p in tail],
    }


@app.get("/api/v1/price-history")
async def api_price_history(
    user: AuthUser | None = GatedUser,
    commodity: str = Query(...),
    city: str = Query(..., description="IHK city id or name"),
    days: int = Query(90, ge=7, le=1825),
) -> JSONResponse:
    return JSONResponse(_price_history_payload(commodity, city, days))

# =============================================================================
# BEHAVIOUR TELEMETRY: /api/v1/events (ingest) and /api/v1/insight/demand
#
# The dashboard batches consented interaction events here. Everything personal
# is stripped in whatsapp_bot.telemetry; the per-day token is computed server
# side from the browser session id (or the signed-in user id) and a salt the
# database forgets after two days. WhatsApp will post to the same store with
# channel="whatsapp" once the ManyChat orchestrator lands; those rows never
# reach the sold view demand_signal_export (enforced in SQL).
# =============================================================================
from whatsapp_bot import telemetry as _telemetry  # noqa: E402

_tlog = logging.getLogger("agriflow.telemetry")
telemetry_store = _telemetry.TelemetryStore(
    db_url=settings.supabase_db_url, spool_path=settings.telemetry_spool,
)


@app.post("/api/v1/events", status_code=204)
async def api_events(request: Request, user: AuthUser | None = OptionalUser) -> Response:
    """Ingest a batch of behaviour events (max 20). Returns 204 with no body."""
    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="body must be JSON")
    try:
        events, meta = _telemetry.validate_batch(payload, channel="web")
    except _telemetry.TelemetryError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    subject = getattr(user, "sub", None) or meta["session_id"]
    if user is not None:
        meta["signed_in"] = True
    try:
        n = telemetry_store.record(events, meta, subject_id=str(subject))
        _tlog.info("telemetry.recorded n=%s channel=web signed_in=%s spool=%s",
                   n, meta["signed_in"], not telemetry_store.enabled)
    except Exception as exc:  # telemetry must never break the caller
        _tlog.warning("telemetry.failed err=%s", type(exc).__name__)
    return Response(status_code=204)


@app.get("/api/v1/insight/demand")
async def api_insight_demand(
    commodity: Optional[str] = Query(None, description="Commodity code filter"),
    days: int = Query(30, ge=1, le=365),
    user: AuthUser | None = GatedUser,
) -> JSONResponse:
    """
    Aggregated, k-anonymised demand signal from the web channel only. Reads the
    SQL view demand_signal_export and nothing else, so this endpoint cannot
    leak a WhatsApp-derived row or a cell under 5 unique users.
    """
    if not telemetry_store.enabled:
        raise HTTPException(status_code=503, detail="insight store not configured")
    rows = telemetry_store.demand_signal(commodity, days)
    return JSONResponse({
        "source": "first-party web events (consented) + BPS + engine outputs; cells < 5 unique users suppressed",
        "channel": "web", "days": days, "commodity": commodity, "count": len(rows), "rows": rows,
    })


# =============================================================================
# MANYCHAT: POST /manychat/webhook
#
# ManyChat's Default Reply calls this from an External Request action (see
# docs/SETUP_MANYCHAT_LLM.md section 5). Everything the pipeline itself does
# (auth, phone hashing, session memory, quota, the Gemini-then-OpenAI
# tool-calling answer, the 7.5s deadline) lives in orchestrator.py; this
# route is only the HTTP shell around Orchestrator.handle(), matching the
# rest of this file's pattern of a thin route over a pure function.
# =============================================================================
from . import manychat as _manychat  # noqa: E402
from .orchestrator import Orchestrator  # noqa: E402


def _ensure_orchestrator() -> Orchestrator:
    if state.orchestrator is None:
        _ensure_state()  # populates state.gemini as a side effect
        state.orchestrator = Orchestrator(
            gemini=state.gemini,
            subs=_ensure_subs(),
            deadline_seconds=settings.manychat_deadline_seconds,
        )
    return state.orchestrator


@app.post("/manychat/webhook", dependencies=[Depends(_manychat.require_manychat_key)])
async def manychat_webhook(req: _manychat.ManyChatWebhookRequest) -> JSONResponse:
    orchestrator = _ensure_orchestrator()
    response = await orchestrator.handle(req)
    return JSONResponse(response.model_dump())


# =============================================================================
# CLI helper: python -m whatsapp_bot.server "Harga cabai di Malang"
# =============================================================================

def _cli_main() -> None:
    # Force UTF-8 stdout on Windows so emoji in replies don't crash cp1252 consoles
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
    if len(sys.argv) < 2:
        print("Usage: python -m whatsapp_bot.server \"<your message>\" [--from +628123]")
        sys.exit(1)
    argv = sys.argv[1:]
    sender = None
    if "--from" in argv:
        i = argv.index("--from")
        sender = argv[i + 1] if i + 1 < len(argv) else None
        argv = argv[:i] + argv[i + 2:]
    msg = " ".join(argv)
    print(handle_message(msg, sender=sender))


if __name__ == "__main__":
    _cli_main()
