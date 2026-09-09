"""
Conversation memory for the ManyChat bot: the chat_session table created in
db/migrations/2026-09-08_behaviour_analytics.sql, keyed by phone_hash so it
joins the existing subscription/quota tables without change.

Mirrors whatsapp_bot/telemetry.py's connection pattern deliberately: same
SQLAlchemy engine construction, same "SUPABASE_DB_URL unset means degrade,
never crash" contract. Here, degrading means every turn is treated as a
fresh session (no memory across messages), which is an honest fallback for
a bot that still answers correctly, just without "what we were just talking
about" continuity, rather than a bot that breaks.

Only the last 10 turns are kept (spec: db/migrations comment "last 10, 24h
clock"). There is no LLM-based summary fold in this version: `rolling_summary`
exists in the schema and is threaded through here so a future pass can add
one, but today it stays whatever was last written to it, most often empty.
Ten raw turns is enough conversational context for "what commodity/city were
we just discussing", which is the continuity this bot actually needs; a
compressed history of turns 11+ is a refinement, not a requirement, for
answering the next question correctly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

log = logging.getLogger("agriflow.chat_session")

MAX_TURNS = 10


@dataclass
class ChatSession:
    phone_hash: str
    manychat_subscriber_id: str = ""
    lang: str = "id"
    turns: List[Dict[str, str]] = field(default_factory=list)
    rolling_summary: str = ""
    slots: Dict[str, Any] = field(default_factory=dict)
    quota_snapshot: Dict[str, Any] = field(default_factory=dict)
    consent_version: str = "none"
    is_new: bool = True

    def add_turn(self, role: str, text: str) -> None:
        """Append one exchange and enforce the 10-turn cap. `text` here is
        conversation history for the model's own context window, not
        anything logged elsewhere: intent_event never receives this."""
        self.turns.append({
            "role": role, "text": text,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        if len(self.turns) > MAX_TURNS:
            self.turns = self.turns[-MAX_TURNS:]


class ChatSessionStore:
    """Loads and saves ChatSession rows. Degrades to an in-memory, per-process
    dict when SUPABASE_DB_URL is unset, so local development and a
    not-yet-configured HF Space both still work; that cache is lost on
    restart, same as it would be with no store at all."""

    def __init__(self, db_url: str = "") -> None:
        self.db_url = (db_url or "").strip()
        self._engine = None
        self._memory: Dict[str, ChatSession] = {}

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

    def load(self, phone_hash: str, manychat_subscriber_id: str = "") -> ChatSession:
        if not self.enabled:
            cached = self._memory.get(phone_hash)
            return cached if cached else ChatSession(phone_hash=phone_hash, manychat_subscriber_id=manychat_subscriber_id)
        from sqlalchemy import text
        try:
            with self._get_engine().connect() as conn:
                row = conn.execute(
                    text("SELECT lang, turns, rolling_summary, slots, quota_snapshot, consent_version "
                         "FROM chat_session WHERE phone_hash = :ph"),
                    {"ph": phone_hash},
                ).mappings().first()
        except Exception as exc:  # a DB hiccup must degrade the turn, not fail it
            log.warning("chat_session.load_failed err=%s", type(exc).__name__)
            return ChatSession(phone_hash=phone_hash, manychat_subscriber_id=manychat_subscriber_id)
        if row is None:
            return ChatSession(phone_hash=phone_hash, manychat_subscriber_id=manychat_subscriber_id)
        return ChatSession(
            phone_hash=phone_hash,
            manychat_subscriber_id=manychat_subscriber_id,
            lang=row["lang"] or "id",
            turns=list(row["turns"] or []),
            rolling_summary=row["rolling_summary"] or "",
            slots=dict(row["slots"] or {}),
            quota_snapshot=dict(row["quota_snapshot"] or {}),
            consent_version=row["consent_version"] or "none",
            is_new=False,
        )

    def save(self, session: ChatSession) -> None:
        if not self.enabled:
            self._memory[session.phone_hash] = session
            return
        from sqlalchemy import text
        sql = text("""
            INSERT INTO chat_session
                (phone_hash, manychat_subscriber_id, lang, turns, rolling_summary,
                 slots, quota_snapshot, consent_version, last_seen_at, updated_at,
                 turns_updated_at, slots_updated_at)
            VALUES
                (:phone_hash, :manychat_subscriber_id, :lang, CAST(:turns AS jsonb), :rolling_summary,
                 CAST(:slots AS jsonb), CAST(:quota_snapshot AS jsonb), :consent_version, now(), now(),
                 now(), now())
            ON CONFLICT (phone_hash) DO UPDATE SET
                manychat_subscriber_id = EXCLUDED.manychat_subscriber_id,
                lang = EXCLUDED.lang,
                turns = EXCLUDED.turns,
                rolling_summary = EXCLUDED.rolling_summary,
                slots = EXCLUDED.slots,
                quota_snapshot = EXCLUDED.quota_snapshot,
                consent_version = EXCLUDED.consent_version,
                last_seen_at = now(),
                updated_at = now(),
                turns_updated_at = now(),
                slots_updated_at = now()
        """)
        import json
        try:
            with self._get_engine().begin() as conn:
                conn.execute(sql, {
                    "phone_hash": session.phone_hash,
                    "manychat_subscriber_id": session.manychat_subscriber_id,
                    "lang": session.lang,
                    "turns": json.dumps(session.turns, ensure_ascii=False),
                    "rolling_summary": session.rolling_summary,
                    "slots": json.dumps(session.slots, ensure_ascii=False),
                    "quota_snapshot": json.dumps(session.quota_snapshot, ensure_ascii=False),
                    "consent_version": session.consent_version,
                })
        except Exception as exc:  # never let a memory write break the reply already sent
            log.warning("chat_session.save_failed err=%s", type(exc).__name__)
