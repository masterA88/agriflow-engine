"""
Configuration — env vars + defaults.

Loads .env from whatsapp_bot/.env or project root .env if present.
Falls back to MOCK_MODE=true so a fresh clone is runnable without any
Twilio or Gemini credentials.
"""

from __future__ import annotations
import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    # Try whatsapp_bot/.env first, then project-root .env
    _here = os.path.dirname(os.path.abspath(__file__))
    for candidate in (
        os.path.join(_here, ".env"),
        os.path.join(_here, "..", ".env"),
    ):
        if os.path.exists(candidate):
            load_dotenv(candidate)
            break
except ImportError:
    # python-dotenv not installed — env must be set externally
    pass


def _bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Mock mode short-circuits Gemini + Twilio signature validation so the
    # bot is runnable end-to-end without external accounts. Default True
    # so fresh clones work; flip to false for production.
    mock_mode: bool = _bool(os.getenv("MOCK_MODE"), default=True)

    # Twilio
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_whatsapp_from: str = os.getenv(
        "TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"  # Twilio sandbox default
    )
    # Disable signature validation entirely (use only for local curl testing).
    twilio_validate_signature: bool = _bool(
        os.getenv("TWILIO_VALIDATE_SIGNATURE"), default=False
    )

    # Gemini — primary LLM (see whatsapp_bot/gemini_client.py)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    # gemini-1.5-flash is retired; 2.5 Flash-Lite is the cheapest current tier and
    # itself retires 16 Oct 2026 (budget on its successor for a Q4 pilot).
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

    # OpenAI — second-tier fallback, tried only when Gemini errors, times out,
    # or returns something unparsable (see whatsapp_bot/openai_client.py and
    # the cascade wired in GeminiClient). Empty key disables this tier
    # entirely: behaviour is then identical to Gemini-only, as it was before
    # this fallback existed. gpt-5.6-luna is OpenAI's cheap/fast tier as of
    # 2026-09, the rough analogue of gemini-2.5-flash-lite — re-verify before
    # trusting this name months from now; see docs/SETUP_MANYCHAT_LLM.md.
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

    # Server
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")

    # Free tier / billing
    # Master switch for the WhatsApp paywall. Default OFF: the quota machinery
    # ships complete and tested, but WhatsApp stays unlimited until the business
    # decision to meter it is actually made. Flip to true to enable.
    quota_enabled: bool = _bool(os.getenv("QUOTA_ENABLED"), default=False)
    # Metered queries a FREE WhatsApp sender gets per day (resets 00:00 WIB).
    free_daily_quota: int = int(os.getenv("FREE_DAILY_QUOTA", "2"))
    pro_price_idr: int = int(os.getenv("PRO_PRICE_IDR", "25000"))
    # Salt for the phone-number digest. MUST be set in production — see the
    # note in subscription.hash_phone about the reversibility of an unsalted
    # hash over the Indonesian mobile keyspace.
    phone_hash_salt: str = os.getenv("PHONE_HASH_SALT", "")
    # json (offline-safe, default) | postgres
    quota_backend: str = os.getenv("QUOTA_BACKEND", "json")
    # Mock billing settles orders with no gateway. Default True so a fresh
    # clone demos end-to-end; set false once a real provider is wired.
    billing_mock: bool = _bool(os.getenv("BILLING_MOCK"), default=True)
    # /chat is unmetered when no sender is supplied, so it bypasses the
    # paywall. Disable it in deployments where that matters.
    debug_chat_enabled: bool = _bool(os.getenv("DEBUG_CHAT_ENABLED"), default=True)

    # Deployment posture. "production" flips the demo defaults into hard
    # requirements at startup (see security.check_production_posture), trims
    # /health to a liveness answer, ignores the caller-supplied sender on
    # /chat, and hides the OpenAPI docs unless API_DOCS_ENABLED says otherwise.
    app_env: str = os.getenv("APP_ENV", "development").strip().lower() or "development"
    # Swagger UI + openapi.json. Default: on in development, off in production.
    api_docs_enabled: bool = _bool(
        os.getenv("API_DOCS_ENABLED"),
        default=(os.getenv("APP_ENV", "development").strip().lower() != "production"),
    )
    # Longest message /chat and /whatsapp will process. WhatsApp itself caps
    # a message at 4096 characters; the intent parser needs far less.
    max_message_chars: int = int(os.getenv("MAX_MESSAGE_CHARS", "1000"))

    # Behaviour telemetry (intent_event). Empty URL = spool to a local JSONL
    # file and warn once; the UI never breaks, but events are not durable.
    supabase_db_url: str = os.getenv("SUPABASE_DB_URL", "")
    telemetry_spool: str = os.getenv("TELEMETRY_SPOOL", "data/telemetry_spool.jsonl")
    consent_version: str = os.getenv("CONSENT_VERSION", "2026-09-v1")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


settings = Settings()
