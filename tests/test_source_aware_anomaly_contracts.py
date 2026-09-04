"""Focused contracts for the versioned source-aware anomaly consumers."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from whatsapp_bot import handlers, server
from whatsapp_bot.handlers import handle_anomali
from whatsapp_bot.intent import INTENT_ANOMALI, Intent


def _status(city_id: str, city_name: str, commodity: str, state: str) -> dict:
    observed = 31 if state == "DETECTABLE" else (2 if state == "INSUFFICIENT_HISTORY" else 0)
    return {
        "city_id": city_id, "city_name": city_name, "commodity_code": commodity,
        "series_status": state, "history_start_date": "2026-01-01" if observed else None,
        "latest_observation_date": "2026-01-31" if observed else None,
        "observation_count": observed, "history_coverage_ratio": 1.0 if observed else None,
        "history_confidence": "HIGH" if observed else None,
        "active_history_source_counts": {"SISKAPERBAPO": observed, "PIHPS": 0},
        "latest_observation_source": "SISKAPERBAPO" if observed else None,
        "observation_freshness_days": 1 if observed else None,
        "market_quality": None,
        "market_quality_availability": "UNAVAILABLE_DERIVED_FILE_HAS_FOUR_COLUMNS",
    }


def _artifact(generated_at: str = "2026-02-01T00:00:00Z") -> dict:
    return {
        "schema_version": "source-aware-anomaly/v1",
        "generated_at": generated_at,
        "method": "shesd_v2",
        "active_source_policy": "SISKAPERBAPO_EXACT_KEY_THEN_PIHPS",
        "series_statuses": [
            _status("3578", "Kota Surabaya", "bawang_merah", "DETECTABLE"),
            _status("3573", "Kota Malang", "bawang_merah", "INSUFFICIENT_HISTORY"),
            _status("3506", "Kediri", "bawang_merah", "NO_ACTIVE_HISTORY"),
        ],
        "events": [{
            "date": "2026-01-31", "price": 40000.0, "rolling_median": 30000.0,
            "deviation_pct": 33.3, "type": "SPIKE", "score": 4.2, "persistent": True,
            "city_id": "3578", "city_name": "Kota Surabaya", "commodity_code": "bawang_merah",
            "observation_provenance": {"data_source": "SISKAPERBAPO", "observation_date": "2026-01-31", "price_per_kg": 40000.0},
        }],
    }


@pytest.fixture
def artifact_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "anomalies_all.json"
    path.write_text(json.dumps(_artifact()), encoding="utf-8")
    monkeypatch.setattr(server, "_ANOMALIES_PATH", str(path))
    monkeypatch.setattr(handlers, "_ANOMALIES_PATH", path)
    server.reload_anomaly_artifact()
    return path


def _api(**kwargs: object) -> dict:
    response = asyncio.run(server.api_anomalies(user=None, **kwargs))
    return json.loads(response.body)


def test_pair_envelope_retains_detectable_zero_events(artifact_path: Path):
    body = _api(city="3578", commodity="bawang_merah", limit=50, since="2027-01-01")
    assert body["count"] == 0 and body["anomalies"] == []
    assert body["series"]["series_status"] == "DETECTABLE"
    assert body["artifact_generated_at"] == "2026-02-01T00:00:00Z"
    assert body["active_source_policy"] == "SISKAPERBAPO_EXACT_KEY_THEN_PIHPS"


def test_unavailable_and_unsupported_statuses(artifact_path: Path):
    insufficient = _api(city="3573", commodity="bawang_merah", limit=50, since=None)
    no_history = _api(city="3506", commodity="bawang_merah", limit=50, since=None)
    unsupported = _api(city="3578", commodity="cabai_merah", limit=50, since=None)
    assert insufficient["series"]["series_status"] == "INSUFFICIENT_HISTORY"
    assert no_history["series"]["series_status"] == "NO_ACTIVE_HISTORY"
    assert unsupported["series"]["series_status"] == "OUT_OF_COVERAGE"
    assert unsupported["series"]["commodity_code"] == "cabai_merah"
    assert unsupported["count"] == 0


def test_aggregate_contract_and_explicit_reload(artifact_path: Path):
    aggregate = _api(city=None, commodity=None, limit=50, since=None)
    assert aggregate["series"] is None
    assert {"count", "method", "anomalies", "status_summary"} <= aggregate.keys()
    artifact_path.write_text(json.dumps(_artifact("2026-02-02T00:00:00Z")), encoding="utf-8")
    server.reload_anomaly_artifact()
    assert _api(city="3578", commodity="bawang_merah", limit=50, since=None)["artifact_generated_at"] == "2026-02-02T00:00:00Z"


@pytest.mark.parametrize("contents", ["{not json", json.dumps({"schema_version": "wrong"})])
def test_invalid_or_missing_artifact_returns_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contents: str):
    path = tmp_path / "bad.json"
    path.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(server, "_ANOMALIES_PATH", str(path))
    server.reload_anomaly_artifact()
    with pytest.raises(HTTPException) as exc_info:
        _api(city=None, commodity=None, limit=50, since=None)
    assert exc_info.value.status_code == 503


def test_anomaly_api_does_not_import_or_call_runtime_detector(artifact_path: Path):
    assert "detect_anomalies" not in server.__dict__
    assert _api(city="3578", commodity="bawang_merah", limit=50, since=None)["count"] == 1


def test_whatsapp_status_and_event_provenance(artifact_path: Path):
    intent = Intent(INTENT_ANOMALI, {"commodity": "bawang_merah", "kabupaten_id": "3578", "kabupaten_name": "Kota Surabaya"})
    reply = handle_anomali(intent, None)  # data is intentionally unused by anomaly handling
    assert "DETECTABLE" in reply and "SISKAPERBAPO=31" in reply
    assert "sumber event: SISKAPERBAPO" in reply


def test_whatsapp_unavailable_and_unsupported_are_not_no_anomaly(artifact_path: Path):
    unavailable = handle_anomali(Intent(INTENT_ANOMALI, {"commodity": "bawang_merah", "kabupaten_id": "3506"}), None)
    unsupported = handle_anomali(Intent(INTENT_ANOMALI, {"commodity": "cabai_merah", "kabupaten_id": "3578"}), None)
    assert "NO_ACTIVE_HISTORY" in unavailable and "tidak ada anomali" not in unavailable.lower()
    assert "OUT_OF_COVERAGE" in unsupported and "cabai_merah" in unsupported


@pytest.mark.parametrize("bare_name", ["Kediri", "Malang", "Probolinggo", "Madiun"])
def test_whatsapp_bare_ambiguous_regions_list_kabupaten_and_kota(
    artifact_path: Path, bare_name: str,
):
    reply = handle_anomali(Intent(INTENT_ANOMALI, {"commodity": "bawang_merah", "kabupaten_name": bare_name}), None)
    assert f"Kabupaten {bare_name}" in reply
    assert f"Kota {bare_name}" in reply


def test_whatsapp_exact_id_and_full_name_resolution(artifact_path: Path):
    by_id = handle_anomali(Intent(INTENT_ANOMALI, {"commodity": "bawang_merah", "kabupaten_id": "3506"}), None)
    by_name = handle_anomali(Intent(INTENT_ANOMALI, {"commodity": "bawang_merah", "kabupaten_name": "  kota   surabaya "}), None)
    assert "Kediri" in by_id and "NO_ACTIVE_HISTORY" in by_id
    assert "Kota Surabaya" in by_name and "DETECTABLE" in by_name


def test_missing_artifact_returns_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server, "_ANOMALIES_PATH", str(tmp_path / "missing.json"))
    server.reload_anomaly_artifact()
    with pytest.raises(HTTPException) as exc_info:
        _api(city=None, commodity=None, limit=50, since=None)
    assert exc_info.value.status_code == 503
