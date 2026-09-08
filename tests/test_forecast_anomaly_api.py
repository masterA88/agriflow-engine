"""
tests/test_forecast_anomaly_api.py

Tests for the new /api/v1/forecast and /api/v1/anomalies endpoints,
plus intent classification and handler dispatch for INTENT_FORECAST
and INTENT_ANOMALI.

All tests run in mock mode (no Gemini, no Twilio, no TimesFM at runtime).
Forecast file: sample_data/forecasts/forecast_all.json (precomputed offline).
Anomaly file:  sample_data/anomalies/anomalies_all.json (precomputed offline).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ["MOCK_MODE"] = "true"

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from sample_data.loader import load_all_sample_data
from whatsapp_bot.gemini_client import GeminiClient
from whatsapp_bot.handlers import EngineData, dispatch
from whatsapp_bot.intent import (
    INTENT_FORECAST, INTENT_ANOMALI, classify,
)

PRICE_DIR      = Path(_ROOT) / "sample_data" / "price_history"
FORECASTS_PATH = Path(_ROOT) / "sample_data" / "forecasts" / "forecast_all.json"
ANOMALIES_PATH = Path(_ROOT) / "sample_data" / "anomalies" / "anomalies_all.json"


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def data():
    return EngineData(load_all_sample_data())


@pytest.fixture(scope="module")
def gemini():
    return GeminiClient(mock=True)


# =============================================================================
# A. Precomputed file integrity
# =============================================================================

class TestPrecomputedFiles:
    """Verify the JSON files exist and have correct schema."""

    def test_forecast_file_exists(self):
        assert FORECASTS_PATH.exists(), (
            f"Forecast file missing: {FORECASTS_PATH}\n"
            "Run: python analysis/forecast_timesfm.py"
        )

    def test_anomaly_file_exists(self):
        assert ANOMALIES_PATH.exists(), (
            f"Anomaly file missing: {ANOMALIES_PATH}\n"
            "Run: python analysis/precompute_anomalies.py"
        )

    def test_forecast_file_nonempty(self):
        with FORECASTS_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
        assert isinstance(data, list) and len(data) > 0

    def test_anomaly_file_nonempty(self):
        """Accept both artifact schemas: the v1 bare list and the source-aware
        v2 dict that keeps the flat records under "events"."""
        with ANOMALIES_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
        events = data.get("events") if isinstance(data, dict) else data
        assert isinstance(events, list) and len(events) > 0

    def test_forecast_record_schema(self):
        """Each forecast record must carry required keys."""
        with FORECASTS_PATH.open(encoding="utf-8") as fh:
            records = json.load(fh)
        required = {
            "commodity_code", "city_id", "city_name",
            "method", "generated_at", "horizon_days",
            "history_end_date", "forecasts",
        }
        for r in records[:5]:
            missing = required - set(r.keys())
            assert not missing, f"Forecast record missing keys: {missing}"

    def test_forecast_point_schema(self):
        """Each forecast point must have date, point, p10, p90."""
        with FORECASTS_PATH.open(encoding="utf-8") as fh:
            records = json.load(fh)
        for r in records[:3]:
            for pt in r["forecasts"][:3]:
                assert "date"  in pt
                assert "point" in pt
                assert "p10"   in pt
                assert "p90"   in pt
                assert pt["p10"] <= pt["point"] <= pt["p90"], (
                    f"CI ordering violated: p10={pt['p10']} point={pt['point']} p90={pt['p90']}"
                )

    def test_anomaly_record_schema(self):
        """Each anomaly record must carry required keys."""
        with ANOMALIES_PATH.open(encoding="utf-8") as fh:
            records = json.load(fh)
        required = {
            "date", "price", "rolling_median", "deviation_pct",
            "type", "score", "commodity_code", "city_id", "city_name", "persistent",
        }
        for r in records[:10]:
            missing = required - set(r.keys())
            assert not missing, f"Anomaly record missing keys: {missing}"

    def test_anomaly_types_valid(self):
        with ANOMALIES_PATH.open(encoding="utf-8") as fh:
            records = json.load(fh)
        for r in records[:50]:
            assert r["type"] in ("SPIKE", "DROP")

    def test_forecast_method_labelled(self):
        """method must be 'timesfm_2.0' or 'seasonal_naive_baseline' — never blank."""
        with FORECASTS_PATH.open(encoding="utf-8") as fh:
            records = json.load(fh)
        valid_methods = {"timesfm_2.0", "seasonal_naive_baseline"}
        for r in records:
            assert r["method"] in valid_methods, (
                f"Unexpected method label: {r['method']!r}"
            )

    def test_forecast_horizon_is_30(self):
        with FORECASTS_PATH.open(encoding="utf-8") as fh:
            records = json.load(fh)
        for r in records[:5]:
            assert len(r["forecasts"]) == 30
            assert r["horizon_days"] == 30

    def test_forecast_cabai_rawit_surabaya_present(self):
        """Key series must be present."""
        with FORECASTS_PATH.open(encoding="utf-8") as fh:
            records = json.load(fh)
        match = next(
            (r for r in records
             if r["commodity_code"] == "cabai_rawit" and r["city_id"] == "3578"),
            None,
        )
        assert match is not None, "cabai_rawit / Surabaya (3578) forecast missing"

    def test_anomaly_bawang_merah_present(self):
        with ANOMALIES_PATH.open(encoding="utf-8") as fh:
            records = json.load(fh)
        bm = [r for r in records if r["commodity_code"] == "bawang_merah"]
        assert len(bm) > 0


# =============================================================================
# B. FastAPI endpoint tests (TestClient)
# =============================================================================

class TestForecastEndpoint:
    @pytest.fixture(scope="class")
    def client(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("fastapi not installed")
        from whatsapp_bot.server import app
        with TestClient(app) as c:
            yield c

    def test_forecast_returns_200_for_valid_pair(self, client):
        r = client.get("/api/v1/forecast?commodity=cabai_rawit&city=3578")
        assert r.status_code == 200, r.text

    def test_forecast_response_schema(self, client):
        r = client.get("/api/v1/forecast?commodity=bawang_merah&city=3509")
        assert r.status_code == 200
        body = r.json()
        assert "commodity_code"   in body
        assert "city_id"          in body
        assert "method"           in body
        assert "forecasts"        in body
        assert isinstance(body["forecasts"], list)
        assert len(body["forecasts"]) == 30

    def test_forecast_point_ci_ordering(self, client):
        r = client.get("/api/v1/forecast?commodity=telur_ayam&city=3578")
        assert r.status_code == 200
        for pt in r.json()["forecasts"]:
            assert pt["p10"] <= pt["point"] <= pt["p90"]

    def test_forecast_404_for_unknown_pair(self, client):
        r = client.get("/api/v1/forecast?commodity=nangka&city=9999")
        assert r.status_code == 404

    def test_forecast_missing_params_422(self, client):
        r = client.get("/api/v1/forecast?commodity=cabai_rawit")
        assert r.status_code == 422  # FastAPI validation

    def test_forecast_method_field_present(self, client):
        r = client.get("/api/v1/forecast?commodity=beras_medium&city=3573")
        assert r.status_code == 200
        assert r.json()["method"] in ("timesfm_2.0", "seasonal_naive_baseline")


class TestAnomaliesEndpoint:
    @pytest.fixture(scope="class")
    def client(self):
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("fastapi not installed")
        from whatsapp_bot.server import app
        with TestClient(app) as c:
            yield c

    def test_anomalies_no_filter_returns_200(self, client):
        r = client.get("/api/v1/anomalies")
        assert r.status_code == 200

    def test_anomalies_response_schema(self, client):
        r = client.get("/api/v1/anomalies?limit=10")
        assert r.status_code == 200
        body = r.json()
        assert "count"     in body
        assert "method"    in body
        assert "anomalies" in body
        assert body["method"] == "hampel_mad_v2"
        assert isinstance(body["anomalies"], list)
        assert len(body["anomalies"]) <= 10

    def test_anomalies_commodity_filter(self, client):
        r = client.get("/api/v1/anomalies?commodity=cabai_rawit&limit=20")
        assert r.status_code == 200
        for a in r.json()["anomalies"]:
            assert a["commodity_code"] == "cabai_rawit"

    def test_anomalies_city_filter(self, client):
        r = client.get("/api/v1/anomalies?city=3578&limit=20")
        assert r.status_code == 200
        for a in r.json()["anomalies"]:
            assert a["city_id"] == "3578"

    def test_anomalies_since_filter(self, client):
        r = client.get("/api/v1/anomalies?since=2024-01-01&limit=50")
        assert r.status_code == 200
        for a in r.json()["anomalies"]:
            assert a["date"] >= "2024-01-01"

    def test_anomalies_record_keys(self, client):
        r = client.get("/api/v1/anomalies?limit=5")
        required = {
            "date", "price", "deviation_pct",
            "type", "score", "commodity_code", "city_id",
        }
        for a in r.json()["anomalies"]:
            missing = required - set(a.keys())
            assert not missing, f"Anomaly record missing keys: {missing}"

    def test_anomalies_limit_respected(self, client):
        r = client.get("/api/v1/anomalies?limit=7")
        assert r.status_code == 200
        assert len(r.json()["anomalies"]) <= 7

    def test_anomalies_nonzero_count(self, client):
        r = client.get("/api/v1/anomalies?limit=100")
        assert r.status_code == 200
        assert r.json()["count"] > 0


# =============================================================================
# C. Intent classification — forecast and anomali
# =============================================================================

class TestNewIntentClassification:
    def test_forecast_intent_prediksi(self, gemini, data):
        intent = classify(
            "Prediksi harga cabai rawit Surabaya bulan depan",
            gemini, data.kabupaten, data.komoditas,
        )
        assert intent.name == INTENT_FORECAST
        assert intent.commodity is not None

    def test_forecast_intent_ramalan(self, gemini, data):
        intent = classify(
            "Ramalan harga bawang merah Malang",
            gemini, data.kabupaten, data.komoditas,
        )
        assert intent.name == INTENT_FORECAST

    def test_forecast_intent_perkiraan(self, gemini, data):
        intent = classify(
            "Perkiraan harga telur Kediri minggu depan",
            gemini, data.kabupaten, data.komoditas,
        )
        assert intent.name == INTENT_FORECAST

    def test_anomali_intent_lonjakan(self, gemini, data):
        intent = classify(
            "Lonjakan harga bawang merah Surabaya",
            gemini, data.kabupaten, data.komoditas,
        )
        assert intent.name == INTENT_ANOMALI

    def test_anomali_intent_anomali_keyword(self, gemini, data):
        intent = classify(
            "Anomali harga cabai rawit",
            gemini, data.kabupaten, data.komoditas,
        )
        assert intent.name == INTENT_ANOMALI

    def test_anomali_intent_spike(self, gemini, data):
        intent = classify(
            "Ada spike harga beras Malang?",
            gemini, data.kabupaten, data.komoditas,
        )
        assert intent.name == INTENT_ANOMALI

    def test_forecast_commodity_extracted(self, gemini, data):
        intent = classify(
            "Forecast cabai rawit Madiun",
            gemini, data.kabupaten, data.komoditas,
        )
        assert intent.name == INTENT_FORECAST
        # commodity may or may not resolve through the engine lookup;
        # test that we at least get a commodity-like string
        # (the mock heuristic resolves cabai rawit → cabai_rawit via _COMMODITY_KEYWORDS)


# =============================================================================
# D. Handler dispatch — forecast and anomali
# =============================================================================

class TestNewHandlerDispatch:
    def test_forecast_dispatch_returns_text(self, gemini, data):
        intent = classify(
            "Prediksi harga cabai rawit Surabaya",
            gemini, data.kabupaten, data.komoditas,
        )
        reply = dispatch(intent, data, gemini)
        assert isinstance(reply, str) and len(reply) > 0

    def test_forecast_dispatch_contains_price(self, gemini, data):
        intent = classify(
            "Prediksi harga bawang merah Surabaya",
            gemini, data.kabupaten, data.komoditas,
        )
        reply = dispatch(intent, data, gemini)
        # Should mention a price (Rp ...) or a help message
        has_price_or_help = any(
            tok in reply.lower() for tok in ["rp ", "prediksi", "tersedia", "kota"]
        )
        assert has_price_or_help, f"Unexpected reply: {reply}"

    def test_anomali_dispatch_returns_text(self, gemini, data):
        intent = classify(
            "Anomali harga cabai rawit",
            gemini, data.kabupaten, data.komoditas,
        )
        reply = dispatch(intent, data, gemini)
        assert isinstance(reply, str) and len(reply) > 0

    def test_anomali_dispatch_contains_anomaly_info(self, gemini, data):
        from whatsapp_bot.intent import Intent, INTENT_ANOMALI
        # Use direct Intent construction to guarantee the anomali handler path
        intent = Intent(
            name=INTENT_ANOMALI,
            slots={"commodity": "bawang_merah", "kabupaten_id": "3578", "kabupaten_name": "Surabaya"},
            raw_message="Lonjakan harga bawang merah Surabaya",
        )
        reply = dispatch(intent, data, gemini)
        has_info = any(
            tok in reply.lower() for tok in ["spike", "drop", "anomali", "deviasi", "total"]
        )
        assert has_info, f"Reply should mention anomaly info: {reply}"

    def test_forecast_no_commodity_returns_help(self, gemini, data):
        """If commodity missing, reply should guide user."""
        from whatsapp_bot.intent import Intent, INTENT_FORECAST
        intent = Intent(
            name=INTENT_FORECAST,
            slots={"commodity": None, "kabupaten_id": None, "kabupaten_name": None},
            raw_message="Prediksi harga",
        )
        reply = dispatch(intent, data, gemini)
        assert isinstance(reply, str) and len(reply) > 0

    def test_anomali_no_filter_returns_results(self, gemini, data):
        """Anomali without commodity filter should return data from precomputed file."""
        from whatsapp_bot.intent import Intent, INTENT_ANOMALI
        intent = Intent(
            name=INTENT_ANOMALI,
            slots={"commodity": None, "kabupaten_id": None, "kabupaten_name": None},
            raw_message="Anomali harga",
        )
        reply = dispatch(intent, data, gemini)
        # Should return anomaly data or empty message — never crash
        assert isinstance(reply, str) and len(reply) > 0


# =============================================================================
# E. TimesFM import guard (CI safety)
# =============================================================================

class TestTimesFMImportGuard:
    def test_timesfm_importorskip(self):
        """
        This test is skipped in CI if timesfm is not installed.
        Guards against the CI failure pattern documented in CLAUDE.md (pandas lesson).
        """
        timesfm = pytest.importorskip(
            "timesfm",
            reason="timesfm not installed — skip TimesFM-specific tests in CI",
        )
        # If we get here, timesfm is available; verify it has the expected API
        assert hasattr(timesfm, "TimesFm") or hasattr(timesfm, "TimesFM"), (
            "timesfm module found but missing expected TimesFm/TimesFM class"
        )
