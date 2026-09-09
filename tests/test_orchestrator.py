"""
whatsapp_bot.orchestrator.Orchestrator, whatsapp_bot.chat_session, and
whatsapp_bot.language: the ManyChat turn pipeline end to end, with fake
collaborators standing in for GeminiClient, SubscriptionService, and
ChatSessionStore, so this file tests the PIPELINE (commands before quota,
quota before the model, consume only on real data, the deadline split)
without touching a live LLM, a live phone-quota store, or a live database.
test_tool_calling.py already covers the model round trip itself in depth.
"""
from __future__ import annotations

import asyncio
import dataclasses
import os
import sys

os.environ.setdefault("MOCK_MODE", "true")

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from whatsapp_bot import orchestrator as orch_mod
from whatsapp_bot.chat_session import ChatSession, ChatSessionStore, MAX_TURNS
from whatsapp_bot.language import detect_language
from whatsapp_bot.manychat import ManyChatWebhookRequest
from whatsapp_bot.orchestrator import Orchestrator
from whatsapp_bot.subscription import Account, AccessDecision, hash_phone
from whatsapp_bot.tools import ToolAnswer


def _with_quota(enabled: bool):
    """Settings is a frozen dataclass (see test_llm_fallback.py's
    _with_settings for the same pattern): rebind orchestrator.py's module-
    level `settings` name to a patched copy rather than mutating a field."""
    return dataclasses.replace(orch_mod.settings, quota_enabled=enabled)


@pytest.fixture()
def quota_off(monkeypatch):
    monkeypatch.setattr(orch_mod, "settings", _with_quota(False))


@pytest.fixture()
def quota_on(monkeypatch):
    monkeypatch.setattr(orch_mod, "settings", _with_quota(True))


# =============================================================================
# language.detect_language
# =============================================================================

class TestDetectLanguage:
    def test_indonesian_sentence(self):
        assert detect_language("Berapa harga cabai di Malang?", "id") == "id"

    def test_javanese_ngoko_sentence(self):
        assert detect_language("Regane lombok ing Malang pira?", "id") == "jv"

    def test_javanese_krama_sentence(self):
        assert detect_language("Reginipun lombok wonten Malang pinten?", "id") == "jv"

    def test_short_ambiguous_message_keeps_prior_language(self):
        assert detect_language("ok", "jv") == "jv"
        assert detect_language("siap", "id") == "id"

    def test_no_cue_words_keeps_prior_language(self):
        assert detect_language("AgriFlow Malang Surabaya", "jv") == "jv"

    def test_bad_prior_lang_falls_back_to_id(self):
        assert detect_language("ok", "xx") == "id"


# =============================================================================
# chat_session.ChatSessionStore (degraded / in-memory mode)
# =============================================================================

class TestChatSessionStoreDegraded:
    def test_disabled_without_db_url(self):
        store = ChatSessionStore(db_url="")
        assert store.enabled is False

    def test_load_missing_session_is_fresh(self):
        store = ChatSessionStore(db_url="")
        s = store.load("abc123", "sub_1")
        assert s.is_new is True
        assert s.turns == []
        assert s.lang == "id"

    def test_save_then_load_round_trips_in_memory(self):
        store = ChatSessionStore(db_url="")
        s = store.load("abc123", "sub_1")
        s.lang = "jv"
        s.add_turn("user", "regane lombok pira")
        s.add_turn("assistant", "Rp 32.500/kg")
        store.save(s)
        reloaded = store.load("abc123")
        assert reloaded.lang == "jv"
        assert len(reloaded.turns) == 2

    def test_turns_capped_at_max_turns(self):
        s = ChatSession(phone_hash="x")
        for i in range(MAX_TURNS + 5):
            s.add_turn("user", f"turn {i}")
        assert len(s.turns) == MAX_TURNS
        assert s.turns[-1]["text"] == f"turn {MAX_TURNS + 4}"

    def test_different_phone_hashes_do_not_share_state(self):
        store = ChatSessionStore(db_url="")
        a = store.load("phone_a"); a.lang = "jv"; store.save(a)
        b = store.load("phone_b")
        assert b.lang == "id"


# =============================================================================
# Orchestrator.handle, with fakes for every collaborator
# =============================================================================

class _FakeGemini:
    def __init__(self, answer: ToolAnswer):
        self._answer = answer
        self.calls = 0

    def answer_with_tools(self, system, message):
        self.calls += 1
        return self._answer


class _SlowFakeGemini:
    """Simulates a call that outlives the deadline."""
    def __init__(self, delay: float, answer: ToolAnswer):
        self.delay = delay
        self._answer = answer
        self.calls = 0

    def answer_with_tools(self, system, message):
        import time
        self.calls += 1
        time.sleep(self.delay)
        return self._answer


class _FakeSubs:
    """Real Account / AccessDecision objects (both plain frozen dataclasses
    from subscription.py), not hand-rolled shapes, so this fake stays
    faithful to whatever billing.py actually reads off them without a
    second copy of that contract to keep in sync by hand."""

    def __init__(self, allowed=True):
        self.allowed = allowed
        self.checked = []
        self.consumed = []
        self.upgrades = []

    def account(self, phone_hash):
        return Account(phone_hash=phone_hash)

    def check(self, phone_hash):
        self.checked.append(phone_hash)
        return AccessDecision(allowed=self.allowed, account=self.account(phone_hash), used_today=2, limit=2)

    def consume(self, phone_hash):
        self.consumed.append(phone_hash)

    def start_upgrade(self, phone_hash):
        self.upgrades.append(phone_hash)
        from whatsapp_bot.subscription import Order, new_order_id, now_wib
        return Order(order_id=new_order_id(), phone_hash=phone_hash, plan="PRO",
                     amount_idr=25000, status="PENDING", created_at=now_wib())


PHONE = "+6281234567890"


def make_req(text: str, subscriber="sub_1", phone=PHONE) -> ManyChatWebhookRequest:
    return ManyChatWebhookRequest(subscriber_id=subscriber, phone=phone, first_name="Tester", last_input_text=text)


def run(coro):
    return asyncio.run(coro)


async def _handle_then_wait(orch, req, wait_seconds):
    """asyncio.run() cancels any task still pending on its loop the moment
    the given coroutine returns, so a background task started inside
    orch.handle() (the deferred-push path) would never get to finish if the
    test awaited it via a second, separate asyncio.run() call. Doing both
    steps inside one coroutine keeps them on the same loop, so the deferred
    task is still alive, and still scheduled, during the sleep below."""
    resp = await orch.handle(req)
    await asyncio.sleep(wait_seconds)
    return resp


class TestOrchestratorHappyPath:
    def test_answers_and_saves_two_turns(self, quota_off):
        gemini = _FakeGemini(ToolAnswer(text="Rp 32.500/kg", tool_calls=[{"name": "get_price", "args": {}, "ok": True}]))
        sessions = ChatSessionStore(db_url="")
        orch = Orchestrator(gemini=gemini, subs=_FakeSubs(), sessions=sessions, deadline_seconds=5.0)

        resp = run(orch.handle(make_req("harga cabai di malang")))

        assert resp.agriflow_status == "ok"
        assert resp.agriflow_reply == "Rp 32.500/kg"
        assert resp.agriflow_intent == "get_price"
        saved = sessions.load(hash_phone(PHONE))
        assert len(saved.turns) == 2
        assert saved.turns[0]["role"] == "user"
        assert saved.turns[1]["role"] == "assistant"

    def test_language_detected_and_carried_in_response(self, quota_off):
        gemini = _FakeGemini(ToolAnswer(text="Rp 32.500/kg"))
        orch = Orchestrator(gemini=gemini, subs=_FakeSubs(), sessions=ChatSessionStore(db_url=""), deadline_seconds=5.0)
        resp = run(orch.handle(make_req("Regane lombok pira?")))
        assert resp.agriflow_lang == "jv"

    def test_no_tool_call_answer_still_returns_ok(self, quota_off):
        gemini = _FakeGemini(ToolAnswer(text="Halo! Ada yang bisa saya bantu?", tool_calls=[]))
        orch = Orchestrator(gemini=gemini, subs=_FakeSubs(), sessions=ChatSessionStore(db_url=""), deadline_seconds=5.0)
        resp = run(orch.handle(make_req("halo")))
        assert resp.agriflow_status == "ok"
        assert resp.agriflow_intent == "chat"


class TestOrchestratorQuota:
    def test_metered_and_allowed_consumes_only_on_successful_tool_call(self, quota_on):
        gemini = _FakeGemini(ToolAnswer(text="Rp 32.500/kg", tool_calls=[{"name": "get_price", "args": {}, "ok": True}]))
        subs = _FakeSubs(allowed=True)
        orch = Orchestrator(gemini=gemini, subs=subs, sessions=ChatSessionStore(db_url=""), deadline_seconds=5.0)
        resp = run(orch.handle(make_req("harga cabai di malang")))
        assert resp.agriflow_status == "ok"
        assert len(subs.consumed) == 1

    def test_metered_but_tool_failed_does_not_consume(self, quota_on):
        gemini = _FakeGemini(ToolAnswer(text="Maaf, tidak ditemukan.", tool_calls=[{"name": "get_price", "args": {}, "ok": False}]))
        subs = _FakeSubs(allowed=True)
        orch = Orchestrator(gemini=gemini, subs=subs, sessions=ChatSessionStore(db_url=""), deadline_seconds=5.0)
        run(orch.handle(make_req("harga entah apa")))
        assert subs.consumed == []

    def test_quota_exceeded_never_calls_the_model(self, quota_on):
        gemini = _FakeGemini(ToolAnswer(text="should not be reached"))
        subs = _FakeSubs(allowed=False)
        orch = Orchestrator(gemini=gemini, subs=subs, sessions=ChatSessionStore(db_url=""), deadline_seconds=5.0)
        resp = run(orch.handle(make_req("harga cabai di malang")))
        assert resp.agriflow_intent == "quota_exceeded"
        assert gemini.calls == 0
        assert len(subs.upgrades) == 1

    def test_status_command_is_free_and_never_calls_the_model(self, quota_on):
        """STATUS must work even over quota. billing.handle_command() calls
        subs.check() itself, to report the remaining count in the reply text,
        so a check() call is expected here; what must NOT happen is
        orchestrator.py's own quota-gate branch running (no consume, no
        upgrade order, and above all the model never touched)."""
        gemini = _FakeGemini(ToolAnswer(text="should not be reached"))
        subs = _FakeSubs(allowed=False)  # even over quota, STATUS must still work
        orch = Orchestrator(gemini=gemini, subs=subs, sessions=ChatSessionStore(db_url=""), deadline_seconds=5.0)
        resp = run(orch.handle(make_req("status")))
        assert gemini.calls == 0
        assert subs.consumed == []
        assert subs.upgrades == []
        assert resp.agriflow_intent == "command"
        assert "Status akun" in resp.agriflow_reply


class TestOrchestratorDeadline:
    def test_slow_answer_returns_pending_immediately(self, quota_off, monkeypatch):
        pushed = []
        monkeypatch.setattr(orch_mod, "send_content", lambda subscriber_id, text: pushed.append((subscriber_id, text)))
        gemini = _SlowFakeGemini(delay=0.3, answer=ToolAnswer(text="jawaban lengkap setelah lama"))
        orch = Orchestrator(gemini=gemini, subs=_FakeSubs(), sessions=ChatSessionStore(db_url=""), deadline_seconds=0.05)

        resp = run(_handle_then_wait(orch, make_req("pertanyaan berat"), wait_seconds=0.6))
        assert resp.agriflow_status == "pending"
        assert "Sebentar" in resp.agriflow_reply
        assert pushed and pushed[0][1] == "jawaban lengkap setelah lama"

    def test_deadline_pending_uses_javanese_holding_message(self, quota_off, monkeypatch):
        monkeypatch.setattr(orch_mod, "send_content", lambda *a, **k: None)
        gemini = _SlowFakeGemini(delay=0.3, answer=ToolAnswer(text="wangsulan"))
        orch = Orchestrator(gemini=gemini, subs=_FakeSubs(), sessions=ChatSessionStore(db_url=""), deadline_seconds=0.05)
        req = make_req("Regane lombok pira nek Semeru njeblug?")
        resp = run(_handle_then_wait(orch, req, wait_seconds=0.6))
        assert resp.agriflow_status == "pending"
        assert resp.agriflow_lang == "jv"
        assert "Sekedhap" in resp.agriflow_reply
