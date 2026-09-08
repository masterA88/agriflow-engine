"""
Behaviour telemetry: validation, day_token, spool fallback, and the
POST /api/v1/events contract. No database is needed; the store runs in
spool mode when SUPABASE_DB_URL is empty.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whatsapp_bot import telemetry  # noqa: E402

SID = str(uuid.uuid4())


def batch(**over):
    p = {
        "events": [{"type": "tab_view", "detail": {"tab": "peta"}}],
        "session_id": SID,
        "consent_version": "2026-09-v1",
        "app_version": "dashboard-1.2",
        "signed_in": False,
    }
    p.update(over)
    return p


class TestValidation:
    def test_valid_batch(self):
        events, meta = telemetry.validate_batch(batch())
        assert len(events) == 1
        assert events[0]["event_type"] == "tab_view"
        assert events[0]["detail"] == {"tab": "peta"}
        assert meta["session_id"] == SID
        assert meta["signed_in"] is False

    def test_unknown_event_type_rejected(self):
        with pytest.raises(telemetry.TelemetryError):
            telemetry.validate_batch(batch(events=[{"type": "keystroke"}]))

    def test_free_text_keys_are_dropped(self):
        ev = {"type": "faq_search", "detail": {"query": "harga cabai", "text": "x", "query_len": 11, "result_count": 3}}
        events, _ = telemetry.validate_batch(batch(events=[ev]))
        assert events[0]["detail"] == {"query_len": 11, "result_count": 3}

    def test_unknown_detail_keys_are_dropped(self):
        ev = {"type": "ui_click", "detail": {"label": "Muat ulang", "secret": "nope", "path": "/dashboard"}}
        events, _ = telemetry.validate_batch(batch(events=[ev]))
        assert set(events[0]["detail"]) == {"label", "path"}

    def test_long_strings_truncated_and_newlines_removed(self):
        ev = {"type": "ui_click", "detail": {"label": "a\nb" + "x" * 200}}
        events, _ = telemetry.validate_batch(batch(events=[ev]))
        assert "\n" not in events[0]["detail"]["label"]
        assert len(events[0]["detail"]["label"]) <= telemetry.MAX_STR

    def test_bad_commodity_and_kab_are_nulled_not_rejected(self):
        ev = {"type": "kabupaten_pick", "commodity": "Cabai Rawit!", "kabupaten_id": "35xx"}
        events, _ = telemetry.validate_batch(batch(events=[ev]))
        assert events[0]["commodity"] is None and events[0]["kabupaten_id"] is None

    def test_good_commodity_and_kab_kept(self):
        ev = {"type": "kabupaten_pick", "commodity": "cabai_rawit", "kabupaten_id": "3578"}
        events, _ = telemetry.validate_batch(batch(events=[ev]))
        assert events[0]["commodity"] == "cabai_rawit" and events[0]["kabupaten_id"] == "3578"

    def test_batch_limits(self):
        with pytest.raises(telemetry.TelemetryError):
            telemetry.validate_batch(batch(events=[]))
        with pytest.raises(telemetry.TelemetryError):
            telemetry.validate_batch(batch(events=[{"type": "page_view"}] * (telemetry.MAX_BATCH + 1)))

    def test_session_id_must_be_uuid(self):
        with pytest.raises(telemetry.TelemetryError):
            telemetry.validate_batch(batch(session_id="abc"))

    def test_consent_version_required(self):
        with pytest.raises(telemetry.TelemetryError):
            telemetry.validate_batch(batch(consent_version=""))

    def test_client_timestamp_parsed(self):
        ev = {"type": "page_view", "ts": 1_757_300_000_000}
        events, _ = telemetry.validate_batch(batch(events=[ev]))
        assert isinstance(events[0]["ts"], dt.datetime)


class TestDayToken:
    def test_deterministic_within_salt_and_different_across_salts(self):
        a = telemetry.day_token("sid-1", b"salt-a")
        assert a == telemetry.day_token("sid-1", b"salt-a")
        assert a != telemetry.day_token("sid-1", b"salt-b")
        assert a != telemetry.day_token("sid-2", b"salt-a")
        assert len(a) == 64

    def test_token_does_not_contain_subject(self):
        t = telemetry.day_token("+628123456789", b"s")
        assert "628123" not in t


class TestSpoolStore:
    def test_spool_mode_writes_jsonl_without_db(self, tmp_path):
        store = telemetry.TelemetryStore(db_url="", spool_path=str(tmp_path / "spool.jsonl"))
        events, meta = telemetry.validate_batch(batch())
        n = store.record(events, meta, subject_id=SID)
        assert n == 1
        rows = [json.loads(l) for l in (tmp_path / "spool.jsonl").read_text(encoding="utf-8").splitlines()]
        assert rows[0]["event_type"] == "tab_view"
        assert rows[0]["session_id"] == SID
        assert len(rows[0]["day_token"]) == 64
        assert store.demand_signal(None, 30) == []


class TestEndpoint:
    @pytest.fixture()
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TELEMETRY_SPOOL", str(tmp_path / "spool.jsonl"))
        from fastapi.testclient import TestClient
        from whatsapp_bot import server
        server.telemetry_store = telemetry.TelemetryStore(db_url="", spool_path=str(tmp_path / "spool.jsonl"))
        return TestClient(server.app)

    def test_events_returns_204(self, client, tmp_path):
        r = client.post("/api/v1/events", json=batch())
        assert r.status_code == 204, r.text
        assert (tmp_path / "spool.jsonl").exists()

    def test_events_rejects_bad_batch(self, client):
        r = client.post("/api/v1/events", json=batch(events=[{"type": "nope"}]))
        assert r.status_code == 422

    def test_insight_without_db_is_503(self, client):
        r = client.get("/api/v1/insight/demand?days=30")
        assert r.status_code == 503
