"""
Behaviour telemetry ingest: validates event batches from the web dashboard
(and, later, the WhatsApp orchestrator) and writes them to intent_event.

Design (spec section 4, k1/research/agriflow-chatbot-architecture/drafts/
spec-manychat-gemini-behaviour-2026-09-08.md):

* Nothing personal is stored. No message text, no phone, no email, no name.
  The `detail` payload is filtered against an allow-list of keys, and the
  database constraint chk_ie_no_text is the second line of defence.
* Users are keyed by a `day_token` = HMAC-SHA256(subject_id, salt_of_today).
  The salt lives in analytics_salt and rotates daily; the database forgets
  salts older than two days, so linking a person across days is not merely
  disallowed, it becomes impossible to compute.
* The token is computed HERE, server side, from the browser session id (or
  the signed-in user id). The client never sends or sees it.
* Without SUPABASE_DB_URL the endpoint still answers 204: events are appended
  to a local JSONL spool (TELEMETRY_SPOOL) so nothing in the UI ever breaks,
  and a warning is logged once. The spool is not durable on ephemeral hosts.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

log = logging.getLogger("agriflow.telemetry")

CHANNELS = frozenset({"web", "whatsapp"})

EVENT_TYPES = frozenset({
    "page_view", "session_start", "session_end", "ui_click",
    "tab_view", "commodity_pick", "kabupaten_pick", "forecast_view", "anomaly_view",
    "explain_view", "simulate_run", "download", "notification_click", "faq_search",
    "bot_query", "bot_clarify", "bot_out_of_coverage",
    "optin", "optout",
})

# Keys allowed inside `detail`. Anything else is dropped, never stored.
DETAIL_KEYS = frozenset({
    "surface", "tab", "from_tab", "target_tab", "path", "label", "tag", "ref",
    "presets", "bbm_pct", "category", "query_len", "result_count", "deficit_kab_id",
    "duration_ms", "n_points", "n_anomalies", "method", "kind", "target", "matched",
    "days", "limit", "source", "decision", "viewport_w", "viewport_h", "lang",
    "n_matches", "coverage_pct", "scenario", "unreachable", "intent_slot",
})
FORBIDDEN_DETAIL_KEYS = frozenset({"text", "message", "phone", "email", "name", "query"})

_CODE_RE = re.compile(r"^[a-z0-9_]{1,40}$")
_KAB_RE = re.compile(r"^\d{4}$")
_VERSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
MAX_BATCH = 20
MAX_STR = 80


class TelemetryError(ValueError):
    """Raised for a malformed batch; the endpoint turns it into HTTP 422."""


# =============================================================================
# Validation
# =============================================================================

def _clean_scalar(v: Any) -> Optional[Any]:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v if abs(v) < 1e12 else None
    if isinstance(v, str):
        s = v.replace("\n", " ").replace("\r", " ").strip()
        return s[:MAX_STR] if s else None
    if isinstance(v, (list, tuple)):
        items = [_clean_scalar(x) for x in v[:20]]
        items = [x for x in items if isinstance(x, (str, int, float, bool))]
        return ",".join(str(x) for x in items) if items else None
    return None


def clean_detail(detail: Any) -> Dict[str, Any]:
    """Keep only allow-listed keys with short scalar values."""
    if not isinstance(detail, dict):
        return {}
    out: Dict[str, Any] = {}
    for k, v in detail.items():
        if not isinstance(k, str) or k in FORBIDDEN_DETAIL_KEYS or k not in DETAIL_KEYS:
            continue
        cv = _clean_scalar(v)
        if cv is not None:
            out[k] = cv
    return out


def validate_event(raw: Any, channel: str) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise TelemetryError("event must be an object")
    et = raw.get("type") or raw.get("event_type")
    if et not in EVENT_TYPES:
        raise TelemetryError(f"unknown event type: {et!r}")
    commodity = raw.get("commodity")
    if commodity is not None and (not isinstance(commodity, str) or not _CODE_RE.match(commodity)):
        commodity = None
    kab = raw.get("kabupaten_id")
    if kab is not None and (not isinstance(kab, str) or not _KAB_RE.match(kab)):
        kab = None
    intent = raw.get("intent")
    if intent is not None and (not isinstance(intent, str) or not _CODE_RE.match(intent)):
        intent = None
    ts = raw.get("ts")
    when: Optional[dt.datetime] = None
    if isinstance(ts, (int, float)) and 1.6e12 < ts < 4e12:  # epoch ms from the browser
        when = dt.datetime.fromtimestamp(ts / 1000.0, tz=dt.timezone.utc)
    return {
        "channel": channel,
        "event_type": et,
        "intent": intent,
        "commodity": commodity,
        "kabupaten_id": kab,
        "detail": clean_detail(raw.get("detail")),
        "ts": when,
    }


def validate_batch(payload: Any, channel: str = "web") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return (events, meta). Raises TelemetryError on a malformed batch."""
    if channel not in CHANNELS:
        raise TelemetryError("bad channel")
    if not isinstance(payload, dict):
        raise TelemetryError("payload must be an object")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise TelemetryError("events must be a non-empty list")
    if len(events) > MAX_BATCH:
        raise TelemetryError(f"at most {MAX_BATCH} events per batch")
    sid = payload.get("session_id")
    try:
        session_id = str(uuid.UUID(str(sid)))
    except (ValueError, TypeError, AttributeError):
        raise TelemetryError("session_id must be a UUID")
    consent = payload.get("consent_version")
    if not isinstance(consent, str) or not _VERSION_RE.match(consent):
        raise TelemetryError("consent_version required")
    app_version = payload.get("app_version")
    if not isinstance(app_version, str) or not _VERSION_RE.match(app_version):
        app_version = None
    signed_in = payload.get("signed_in")
    signed_in = bool(signed_in) if isinstance(signed_in, bool) else None
    meta = {
        "session_id": session_id,
        "consent_version": consent,
        "app_version": app_version,
        "signed_in": signed_in,
    }
    return [validate_event(e, channel) for e in events], meta


# =============================================================================
# day_token
# =============================================================================

def day_token(subject_id: str, salt: bytes) -> str:
    return hmac.new(salt, subject_id.encode("utf-8"), hashlib.sha256).hexdigest()


# =============================================================================
# Storage
# =============================================================================

class TelemetryStore:
    """Writes validated events to Postgres, or to a JSONL spool when no DB."""

    def __init__(self, db_url: str = "", spool_path: str = "") -> None:
        self.db_url = (db_url or "").strip()
        self.spool_path = Path(spool_path or os.getenv("TELEMETRY_SPOOL", "data/telemetry_spool.jsonl"))
        self._engine = None
        self._lock = threading.Lock()
        self._salt_cache: Tuple[Optional[dt.date], bytes] = (None, b"")
        self._warned = False
        self._fallback_salt = secrets.token_bytes(32)  # process-local, spool mode only

    # -- connection -----------------------------------------------------------
    @property
    def enabled(self) -> bool:
        return bool(self.db_url)

    def _get_engine(self):
        if self._engine is None:
            from sqlalchemy import create_engine
            url = self.db_url
            if url.startswith("postgres://"):
                url = "postgresql+psycopg2://" + url[len("postgres://"):]
            elif url.startswith("postgresql://"):
                url = "postgresql+psycopg2://" + url[len("postgresql://"):]
            self._engine = create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=3, future=True)
        return self._engine

    # -- salt -----------------------------------------------------------------
    def salt_today(self) -> bytes:
        today = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=7)).date()  # WIB
        with self._lock:
            d, s = self._salt_cache
            if d == today and s:
                return s
        if not self.enabled:
            salt = self._fallback_salt
        else:
            from sqlalchemy import text
            with self._get_engine().begin() as conn:
                salt = conn.execute(text("SELECT analytics_salt_today()")).scalar_one()
            salt = bytes(salt)
        with self._lock:
            self._salt_cache = (today, salt)
        return salt

    # -- write ----------------------------------------------------------------
    def record(self, events: Iterable[Dict[str, Any]], meta: Dict[str, Any], subject_id: str) -> int:
        rows = list(events)
        if not rows:
            return 0
        token = day_token(subject_id, self.salt_today())
        payload = [{
            "channel": e["channel"], "event_type": e["event_type"], "intent": e["intent"],
            "commodity": e["commodity"], "kabupaten_id": e["kabupaten_id"],
            "detail": json.dumps(e["detail"], ensure_ascii=False),
            "day_token": token, "session_id": meta["session_id"], "signed_in": meta["signed_in"],
            "consent_version": meta["consent_version"], "app_version": meta["app_version"],
            "ts": e["ts"],
        } for e in rows]
        if not self.enabled:
            return self._spool(payload)
        from sqlalchemy import text
        sql = text(
            "INSERT INTO intent_event (ts, channel, event_type, intent, commodity, kabupaten_id, "
            "detail, day_token, session_id, signed_in, consent_version, app_version) "
            "VALUES (COALESCE(:ts, now()), :channel, :event_type, :intent, :commodity, :kabupaten_id, "
            "CAST(:detail AS jsonb), :day_token, CAST(:session_id AS uuid), :signed_in, :consent_version, :app_version)"
        )
        with self._get_engine().begin() as conn:
            conn.execute(sql, payload)
        return len(payload)

    def _spool(self, payload: List[Dict[str, Any]]) -> int:
        if not self._warned:
            log.warning("telemetry.spool_mode path=%s (SUPABASE_DB_URL not set; events are not durable)", self.spool_path)
            self._warned = True
        try:
            self.spool_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, self.spool_path.open("a", encoding="utf-8") as fh:
                for p in payload:
                    p = dict(p)
                    p["ts"] = (p["ts"] or dt.datetime.now(dt.timezone.utc)).isoformat()
                    fh.write(json.dumps(p, ensure_ascii=False) + "\n")
        except OSError as exc:  # never let telemetry break the app
            log.warning("telemetry.spool_failed err=%s", exc)
            return 0
        return len(payload)

    # -- read (internal insight) ----------------------------------------------
    def demand_signal(self, commodity: Optional[str], days: int) -> List[Dict[str, Any]]:
        """Rows from demand_signal_export, the only sellable surface."""
        if not self.enabled:
            return []
        from sqlalchemy import text
        q = (
            "SELECT day, event_type, intent, commodity, kabupaten_id, event_count, unique_users "
            "FROM demand_signal_export WHERE day >= (now() AT TIME ZONE 'Asia/Jakarta')::date - :days "
            + ("AND commodity = :commodity " if commodity else "")
            + "ORDER BY day DESC, unique_users DESC LIMIT 2000"
        )
        params: Dict[str, Any] = {"days": max(1, min(days, 365))}
        if commodity:
            params["commodity"] = commodity
        with self._get_engine().connect() as conn:
            res = conn.execute(text(q), params)
            return [{"day": r.day.isoformat(), "event_type": r.event_type, "intent": r.intent,
                     "commodity": r.commodity, "kabupaten_id": r.kabupaten_id,
                     "event_count": r.event_count, "unique_users": r.unique_users} for r in res]
