"""
HTTP-route-level tests for POST /manychat/webhook: the shared-secret header
dependency (whatsapp_bot.manychat.require_manychat_key) wired onto the real
FastAPI route, exercised through TestClient rather than by calling the
dependency function directly. test_orchestrator.py already covers the
pipeline behind this route in depth with fake collaborators; this file only
checks what changes at the transport boundary: the header is enforced, an
empty secret fails closed, and a request that passes it reaches a real
(mock-mode) answer with the response shape ManyChat's flow builder expects.
"""
from __future__ import annotations

import dataclasses
import os
import sys

os.environ.setdefault("MOCK_MODE", "true")

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest
from fastapi.testclient import TestClient

from whatsapp_bot import manychat as manychat_mod
from whatsapp_bot import server

TEST_SECRET = "test-manychat-secret-0123456789"

BODY = {
    "subscriber_id": "sub-1",
    "phone": "",
    "first_name": "Budi",
    "last_input_text": "Berapa harga cabai di Malang hari ini?",
}


@pytest.fixture()
def keyed(monkeypatch):
    """A known MANYCHAT_WEBHOOK_SECRET. Settings is frozen (see
    test_orchestrator.py's _with_quota for the same pattern), so the fix is
    to rebind manychat.py's own module-level `settings` name to a patched
    copy rather than mutate a field on the shared instance."""
    monkeypatch.setattr(
        manychat_mod, "settings",
        dataclasses.replace(manychat_mod.settings, manychat_webhook_secret=TEST_SECRET),
    )


@pytest.fixture()
def client():
    with TestClient(server.app) as c:
        yield c


# =============================================================================
# Auth dependency: require_manychat_key, exercised through the real route
# =============================================================================

class TestAuth:
    def test_missing_key_header_is_rejected(self, keyed, client):
        r = client.post("/manychat/webhook", json=BODY)
        assert r.status_code == 401

    def test_wrong_key_is_rejected(self, keyed, client):
        r = client.post(
            "/manychat/webhook", json=BODY,
            headers={"X-AgriFlow-Key": "not-the-secret"},
        )
        assert r.status_code == 401

    def test_unset_secret_refuses_every_request(self, client, monkeypatch):
        # No `keyed` fixture: manychat_webhook_secret stays at its default
        # (""), which must fail closed even when the caller supplies some
        # header value, per require_manychat_key's own docstring.
        monkeypatch.setattr(
            manychat_mod, "settings",
            dataclasses.replace(manychat_mod.settings, manychat_webhook_secret=""),
        )
        r = client.post(
            "/manychat/webhook", json=BODY,
            headers={"X-AgriFlow-Key": "anything"},
        )
        assert r.status_code == 401


# =============================================================================
# Happy path: correct key, mock-mode Gemini, full round trip
# =============================================================================

class TestHappyPath:
    def test_correct_key_returns_a_full_answer(self, keyed, client):
        r = client.post(
            "/manychat/webhook", json=BODY,
            headers={"X-AgriFlow-Key": TEST_SECRET},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["agriflow_status"] == "ok"
        assert isinstance(body["agriflow_reply"], str) and body["agriflow_reply"]
        assert body["agriflow_lang"] == "id"
        assert body["agriflow_intent"] == "chat"  # mock mode calls no tool
