"""
The ManyChat turn pipeline: one incoming WhatsApp message in, one
ManyChatWebhookResponse out, with everything server.py's existing
handle_message() already does for Twilio (billing commands, quota, phone
hashing) reused as-is, plus what handle_message() cannot do: answer an
arbitrary question about AgriFlow's data via the function-calling tools in
tools.py instead of six hand-classified intents.

Pipeline (spec 2.2, this module's numbering matches it):
    1-2  auth + phone_hash            done by the caller (manychat.py, server.py route)
    3    session                      chat_session.py, load()
    4    language                     language.py
    5    commands                     billing.parse_command / handle_command, unmetered
    6-11 quota, answer, consume       SubscriptionService (shared with Twilio), gemini_client cascade
    10   deadline                     asyncio.wait, this module
    12   persist                      chat_session.py, save(); intent_event via telemetry.py
    13   reply                        ManyChatWebhookResponse

Two paths out of the deadline step: inside the window, the full answer comes
back as agriflow_status="ok". Past it, this returns a short holding line as
agriflow_status="pending" immediately, while the same answer keeps computing
in the background and is pushed through ManyChat's Public API the moment it
finishes (manychat.send_content). Either way the user gets exactly one
answer; "pending" only changes how it arrives, never whether it arrives.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .chat_session import ChatSession, ChatSessionStore
from .config import settings
from .gemini_client import GeminiClient
from .language import detect_language
from .manychat import (
    HOLDING_MESSAGE_ID, HOLDING_MESSAGE_JV, ManyChatPushError,
    ManyChatWebhookRequest, ManyChatWebhookResponse, send_content,
)
from .subscription import hash_phone, SubscriptionService
from . import billing
from . import telemetry as _telemetry

log = logging.getLogger("agriflow.orchestrator")

DEFAULT_DEADLINE_SECONDS = 7.5

SYSTEM_PROMPT_ID = """\
Anda adalah asisten AgriFlow, platform ketahanan pangan Jawa Timur, yang menjawab lewat WhatsApp.
Jawab dalam Bahasa Indonesia, singkat dan jelas (maksimal 4 kalimat kecuali diminta lebih rinci).
Setiap angka (harga, prakiraan, surplus/defisit, hasil simulasi) HARUS berasal dari pemanggilan alat
yang tersedia; jangan pernah mengarang angka. Bila pertanyaan menyebut nama kabupaten/kota atau nama
komoditas dalam bahasa sehari-hari, panggil alat dengan nama itu apa adanya, alat akan mencocokkannya.
Bila alat mengembalikan error, sampaikan dengan jujur dan singkat, jangan menebak jawabannya.
Akhiri jawaban yang memuat angka dengan menyebut singkat tanggal datanya bila relevan.
"""

SYSTEM_PROMPT_JV = """\
Sampeyan asisten AgriFlow, platform katahanan pangan Jawa Timur, sing mangsuli liwat WhatsApp.
Wangsulan nganggo Basa Jawa (ngoko utawa krama miturut basane sing takon), cekak lan cetha
(maksimal 4 ukara kajaba dijaluk luwih rinci). Saben angka (rega, prakiraan, surplus/defisit, asil
simulasi) KUDU asale saka alat sing kasedhiya; aja tau ngarang angka. Yen pitakonan nyebut jeneng
kabupaten/kota utawa jeneng komoditas nganggo basa saben dinane, undang alat kanthi jeneng kuwi apa
anane, alat bakal nyocogake. Yen alat bali error, kandhakna kanthi jujur lan cekak, aja ngira-ira
wangsulane.
"""


def _system_prompt(lang: str, session: ChatSession) -> str:
    base = SYSTEM_PROMPT_JV if lang == "jv" else SYSTEM_PROMPT_ID
    if session.rolling_summary:
        base += f"\n\nRingkasan percakapan sebelumnya: {session.rolling_summary}"
    if session.turns:
        recent = session.turns[-4:]
        lines = "\n".join(f"{t['role']}: {t['text']}" for t in recent)
        base += f"\n\nBeberapa giliran terakhir:\n{lines}"
    return base


class Orchestrator:
    """Holds the collaborators the pipeline needs so tests can substitute
    fakes for all of them without monkeypatching module globals. server.py
    constructs the real one once at startup, mirroring how it already holds
    one GeminiClient and one SubscriptionService in `state`."""

    def __init__(
        self,
        gemini: Optional[GeminiClient] = None,
        subs: Optional[SubscriptionService] = None,
        sessions: Optional[ChatSessionStore] = None,
        deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    ):
        self.gemini = gemini or GeminiClient()
        self.subs = subs or SubscriptionService()
        self.sessions = sessions or ChatSessionStore(db_url=settings.supabase_db_url)
        self.deadline_seconds = deadline_seconds

    async def handle(self, req: ManyChatWebhookRequest) -> ManyChatWebhookResponse:
        phone_hash = hash_phone(req.phone) if req.phone.strip() else hash_phone(req.subscriber_id)
        session = self.sessions.load(phone_hash, req.subscriber_id)
        text = req.last_input_text.strip()

        # 5. Commands: free, unmetered, and skipped entirely with the paywall
        #    off, exactly like handle_message()'s own reasoning in server.py.
        if settings.quota_enabled and phone_hash:
            command = billing.parse_command(text)
            if command is not None:
                reply = billing.handle_command(command, phone_hash, self.subs)
                self._remember(session, text, reply)
                self._log_intent_event(phone_hash, "bot_query", ok=True)
                return ManyChatWebhookResponse(agriflow_reply=reply, agriflow_lang=session.lang, agriflow_intent="command")

        # 4. Language for this turn (after commands: "STATUS" is not evidence
        #    of either language, and must not flip the session's lang).
        lang = detect_language(text, session.lang)
        session.lang = lang

        # 6. Quota.
        metered = settings.quota_enabled and bool(phone_hash)
        if metered:
            decision = self.subs.check(phone_hash)
            if not decision.allowed:
                order = self.subs.start_upgrade(phone_hash)
                reply = billing.quota_exceeded(decision, order)
                self._remember(session, text, reply)
                self._log_intent_event(phone_hash, "bot_query", ok=False)
                return ManyChatWebhookResponse(agriflow_reply=reply, agriflow_lang=lang, agriflow_intent="quota_exceeded")

        system = _system_prompt(lang, session)

        # 7-9-10. Route, execute, compose, all inside answer_with_tools; the
        # deadline wraps the whole thing in a thread so a slow provider call
        # cannot block the event loop other requests are being served on.
        task = asyncio.create_task(asyncio.to_thread(self.gemini.answer_with_tools, system, text))
        done, _pending = await asyncio.wait({task}, timeout=self.deadline_seconds)

        if task in done:
            answer = task.result()
            self._finish_turn(session, phone_hash, text, answer, metered)
            return ManyChatWebhookResponse(
                agriflow_reply=answer.text, agriflow_lang=lang,
                agriflow_intent=",".join(c["name"] for c in answer.tool_calls) or "chat",
            )

        # Deadline missed. Reply now with a holding line; the same task keeps
        # running and pushes the real answer through the Public API the
        # moment it finishes. subscriber_id, not phone_hash, is what the
        # push needs, since that is ManyChat's own addressing.
        subscriber_id = req.subscriber_id
        holding = HOLDING_MESSAGE_JV if lang == "jv" else HOLDING_MESSAGE_ID
        asyncio.ensure_future(self._finish_after_deadline(task, session, phone_hash, subscriber_id, text, metered))
        return ManyChatWebhookResponse(agriflow_reply=holding, agriflow_status="pending", agriflow_lang=lang)

    async def _finish_after_deadline(self, task, session, phone_hash, subscriber_id, text, metered) -> None:
        try:
            answer = await task
        except Exception as exc:  # answer_with_tools itself should never raise (it degrades to mock),
            log.warning("orchestrator.deferred_task_failed err=%s", type(exc).__name__)  # but this is the last line of defence.
            return
        self._finish_turn(session, phone_hash, text, answer, metered)
        try:
            await asyncio.to_thread(send_content, subscriber_id, answer.text)
        except ManyChatPushError as exc:
            log.warning("manychat.push_failed subscriber=%s err=%s", subscriber_id, exc)

    def _finish_turn(self, session, phone_hash, user_text, answer, metered) -> None:
        # 11. Consume only if a tool actually returned data, mirroring
        #     handle_message()'s "bill only what we actually answered".
        if metered and any(c.get("ok") for c in answer.tool_calls):
            self.subs.consume(phone_hash)
        self._remember(session, user_text, answer.text)
        self._log_intent_event(
            phone_hash, "bot_query" if not answer.tool_calls else "bot_query",
            ok=(not answer.tool_calls) or any(c.get("ok") for c in answer.tool_calls),
            tool_names=[c["name"] for c in answer.tool_calls],
        )

    def _remember(self, session: ChatSession, user_text: str, reply_text: str) -> None:
        session.add_turn("user", user_text)
        session.add_turn("assistant", reply_text)
        self.sessions.save(session)

    def _log_intent_event(self, phone_hash: str, event_type: str, *, ok: bool, tool_names: Optional[list] = None) -> None:
        """Best-effort, channel="whatsapp": this row can never reach
        demand_signal_export (the view filters to channel='web' in SQL), so
        logging it freely here does not risk the Meta Business Solution
        Terms boundary the telemetry system was built around."""
        try:
            from . import server as _srv
            store: _telemetry.TelemetryStore = getattr(_srv, "telemetry_store", None)
            if store is None or not store.enabled:
                return
            raw_detail = {"decision": "ok" if ok else "no_data", "target": ",".join(tool_names or [])[:80]}
            events = [{
                "channel": "whatsapp", "event_type": event_type, "intent": None,
                "commodity": None, "kabupaten_id": None,
                # Defence in depth: record() is called directly here, bypassing
                # the HTTP-facing validate_batch() in telemetry.py, so this
                # allow-list filter (the same one that path uses) is applied
                # by hand instead of trusted to stay correct by construction.
                "detail": _telemetry.clean_detail(raw_detail),
                "ts": None,
            }]
            meta = {"session_id": None, "consent_version": "none", "app_version": "whatsapp-bot-1.0", "signed_in": False}
            store.record(events, meta, subject_id=phone_hash)
        except Exception as exc:  # telemetry must never break a reply already computed
            log.warning("orchestrator.telemetry_failed err=%s", type(exc).__name__)
