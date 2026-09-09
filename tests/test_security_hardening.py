"""
Transport hardening: security headers, body cap, rate limiter, CORS scope,
production posture, and the input bounds on the engine-running endpoints.

Each test is one way the September 2026 audit found the API could be abused
from the outside with no credentials at all.
"""

from __future__ import annotations

import os
import sys
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from whatsapp_bot import security  # noqa: E402


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PHONE_HASH_SALT", "t")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
    from whatsapp_bot import server
    with TestClient(server.app) as c:
        yield c


@pytest.fixture
def limited_client(monkeypatch):
    monkeypatch.setenv("PHONE_HASH_SALT", "t")
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "5")
    monkeypatch.setenv("RATE_LIMIT_HEAVY_PER_MINUTE", "2")
    security.reset_rate_limits()
    from whatsapp_bot import server
    with TestClient(server.app) as c:
        yield c
    security.reset_rate_limits()


# =============================================================================
# A. SECURITY HEADERS
# =============================================================================

class TestA_Headers:

    def test_json_responses_carry_baseline_headers(self, client):
        r = client.get("/api/v1/commodities")
        assert r.status_code == 200
        h = r.headers
        assert h["x-content-type-options"] == "nosniff"
        assert h["x-frame-options"] == "DENY"
        assert h["referrer-policy"] == "no-referrer"
        assert h["cache-control"] == "no-store"
        assert h["content-security-policy"].startswith("default-src 'none'")
        assert "frame-ancestors 'none'" in h["content-security-policy"]

    def test_html_billing_page_gets_form_scoped_csp(self, client):
        r = client.get("/billing/pay/AF-00000000")
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("text/html")
        csp = r.headers["content-security-policy"]
        assert "style-src 'unsafe-inline'" in csp
        assert "form-action 'self'" in csp
        assert "script-src" not in csp  # nothing may run scripts on that page

    def test_hsts_only_behind_https(self, client):
        plain = client.get("/health")
        assert "strict-transport-security" not in plain.headers
        tls = client.get("/health", headers={"X-Forwarded-Proto": "https"})
        assert tls.headers["strict-transport-security"].startswith("max-age=63072000")

    def test_error_responses_are_stamped_too(self, client):
        r = client.get("/api/v1/surplus-deficit", params={"commodity": "nope"})
        assert r.status_code == 404
        assert r.headers["x-content-type-options"] == "nosniff"


# =============================================================================
# B. BODY CAP
# =============================================================================

class TestB_BodyCap:

    def test_oversized_body_is_refused_before_parsing(self, client, monkeypatch):
        monkeypatch.setenv("MAX_BODY_BYTES", "256")
        r = client.post("/chat", json={"message": "x" * 1000})
        assert r.status_code == 413
        assert r.json()["error"] == "payload_too_large"

    def test_normal_body_passes(self, client):
        r = client.post("/chat", json={"message": "Harga cabai di Malang"})
        assert r.status_code == 200

    def test_long_message_is_refused_even_under_body_cap(self, client, monkeypatch):
        monkeypatch.setattr("whatsapp_bot.server.settings",
                            replace(__import__("whatsapp_bot.server", fromlist=["settings"]).settings,
                                    max_message_chars=20))
        r = client.post("/chat", json={"message": "x" * 21})
        assert r.status_code == 413


# =============================================================================
# C. RATE LIMIT
# =============================================================================

class TestC_RateLimit:

    def test_general_tier_trips_after_limit(self, limited_client):
        codes = [limited_client.get("/api/v1/commodities").status_code for _ in range(6)]
        assert codes[:5] == [200] * 5
        assert codes[5] == 429

    def test_429_carries_retry_after_and_headers(self, limited_client):
        for _ in range(5):
            limited_client.get("/api/v1/kabupaten")
        r = limited_client.get("/api/v1/kabupaten")
        assert r.status_code == 429
        assert int(r.headers["retry-after"]) >= 1
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.json()["error"] == "rate_limited"

    def test_heavy_tier_is_stricter(self, limited_client):
        codes = [limited_client.post("/chat", json={"message": "halo"}).status_code
                 for _ in range(3)]
        assert codes == [200, 200, 429]

    def test_tiers_are_independent_buckets(self, limited_client):
        for _ in range(2):
            limited_client.post("/chat", json={"message": "halo"})
        assert limited_client.post("/chat", json={"message": "halo"}).status_code == 429
        # The general bucket for the same client is untouched.
        assert limited_client.get("/api/v1/commodities").status_code == 200

    def test_clients_are_keyed_by_forwarded_ip(self, limited_client):
        a = {"X-Forwarded-For": "203.0.113.1"}
        b = {"X-Forwarded-For": "203.0.113.2"}
        for _ in range(5):
            limited_client.get("/api/v1/commodities", headers=a)
        assert limited_client.get("/api/v1/commodities", headers=a).status_code == 429
        assert limited_client.get("/api/v1/commodities", headers=b).status_code == 200

    def test_forwarded_header_ignored_when_proxy_untrusted(self, limited_client, monkeypatch):
        monkeypatch.setenv("TRUST_PROXY", "false")
        for i in range(5):
            limited_client.get("/api/v1/commodities", headers={"X-Forwarded-For": f"10.0.0.{i}"})
        # Spoofing a fresh XFF per request no longer buys a fresh bucket.
        r = limited_client.get("/api/v1/commodities", headers={"X-Forwarded-For": "10.0.0.99"})
        assert r.status_code == 429

    def test_preflight_is_never_limited(self, limited_client):
        for _ in range(8):
            r = limited_client.options(
                "/api/v1/commodities",
                headers={"Origin": "https://agriflow-engine.vercel.app",
                         "Access-Control-Request-Method": "GET"},
            )
            assert r.status_code == 200


# =============================================================================
# D. CORS SCOPE
# =============================================================================

class TestD_Cors:

    def _preflight(self, client, origin):
        return client.options(
            "/api/v1/matches",
            headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
        )

    def test_production_dashboard_allowed(self, client):
        r = self._preflight(client, "https://agriflow-engine.vercel.app")
        assert r.headers.get("access-control-allow-origin") == "https://agriflow-engine.vercel.app"

    def test_project_preview_allowed(self, client):
        origin = "https://agriflow-engine-git-feature-x-team.vercel.app"
        r = self._preflight(client, origin)
        assert r.headers.get("access-control-allow-origin") == origin

    @pytest.mark.parametrize("origin", [
        "https://evil.vercel.app",
        "https://someone-else.hf.space",
        "https://agriflow-engine.vercel.app.evil.com",
        "http://agriflow-engine.vercel.app",
    ])
    def test_foreign_origins_refused(self, client, origin):
        r = self._preflight(client, origin)
        assert r.headers.get("access-control-allow-origin") is None

    def test_credentials_never_allowed(self, client):
        r = self._preflight(client, "https://agriflow-engine.vercel.app")
        assert r.headers.get("access-control-allow-credentials") is None


# =============================================================================
# E. PRODUCTION POSTURE
# =============================================================================

class TestE_Posture:

    def test_development_defaults_only_warn(self):
        from whatsapp_bot.config import settings
        findings = security.posture_findings(settings)
        assert findings  # the demo defaults are, by design, not production-safe
        assert security.check_production_posture(settings) == findings

    def test_production_refuses_demo_defaults(self, monkeypatch):
        from whatsapp_bot.config import settings
        monkeypatch.setenv("APP_ENV", "production")
        # Pin the demo defaults explicitly: `settings` is frozen at first
        # import, and another test may have exported a salt before that.
        demo = replace(settings, mock_mode=True, phone_hash_salt="",
                       twilio_validate_signature=False, billing_mock=True)
        with pytest.raises(security.InsecureProductionConfig) as exc:
            security.check_production_posture(demo)
        msg = str(exc.value)
        for flag in ("MOCK_MODE", "PHONE_HASH_SALT", "TWILIO_VALIDATE_SIGNATURE", "BILLING_MOCK"):
            assert flag in msg

    def test_production_boots_when_hardened(self, monkeypatch):
        from whatsapp_bot.config import settings
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("API_DOCS_ENABLED", raising=False)
        hardened = replace(
            settings, mock_mode=False, twilio_validate_signature=True,
            billing_mock=False, phone_hash_salt="s" * 64, debug_chat_enabled=True,
            app_env="production", manychat_webhook_secret="s" * 32,
        )
        assert security.check_production_posture(hardened) == []

    def test_strict_off_downgrades_to_warning(self, monkeypatch):
        from whatsapp_bot.config import settings
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("SECURITY_POSTURE_STRICT", "false")
        assert security.check_production_posture(settings)  # returns, does not raise

    def test_health_is_minimal_in_production(self, monkeypatch):
        monkeypatch.setenv("PHONE_HASH_SALT", "t")
        monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
        from whatsapp_bot import server
        monkeypatch.setattr(server, "settings", replace(server.settings, app_env="production"))
        with TestClient(server.app) as c:
            body = c.get("/health").json()
        assert set(body) == {"status", "version", "data_loaded"}

    def test_chat_ignores_sender_in_production(self, monkeypatch):
        monkeypatch.setenv("PHONE_HASH_SALT", "t")
        monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
        from whatsapp_bot import server
        monkeypatch.setattr(server, "settings", replace(
            server.settings, app_env="production", quota_enabled=True))
        seen = {}

        def fake_handle(message, sender=None):
            seen["sender"] = sender
            return "ok"

        monkeypatch.setattr(server, "handle_message", fake_handle)
        with TestClient(server.app) as c:
            c.post("/chat", json={"message": "STATUS", "from": "whatsapp:+628123"})
        assert seen["sender"] is None

    def test_docs_hidden_when_disabled(self, monkeypatch):
        # The FastAPI app is built at import time, so build a fresh one.
        from fastapi import FastAPI
        from whatsapp_bot.config import settings
        assert settings.api_docs_enabled is True  # development default
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        with TestClient(app) as c:
            assert c.get("/docs").status_code == 404
            assert c.get("/openapi.json").status_code == 404


# =============================================================================
# F. INPUT BOUNDS AND OUTPUT HYGIENE
# =============================================================================

class TestF_Inputs:

    def test_simulate_rejects_absurd_fuel_shock(self, client):
        r = client.post("/api/v1/simulate", json={"bbm_pct": 1e308})
        assert r.status_code == 422

    def test_simulate_rejects_oversized_lists(self, client):
        r = client.post("/api/v1/simulate", json={"unreachable_kab": ["3508"] * 101})
        assert r.status_code == 422

    def test_simulate_rejects_unknown_allocator(self, client):
        r = client.post("/api/v1/simulate", json={"allocator": "drop table"})
        assert r.status_code == 422

    def test_simulate_rejects_bad_limit(self, client):
        assert client.post("/api/v1/simulate", json={"limit": 0}).status_code == 422
        assert client.post("/api/v1/simulate", json={"limit": 10_000}).status_code == 422

    def test_simulate_still_works_inside_bounds(self, client):
        r = client.post("/api/v1/simulate", json={"presets": ["semeru"], "limit": 5})
        assert r.status_code == 200

    @pytest.mark.parametrize("bad", ["../etc/passwd", "AF-1234", "<script>", "AF-ZZZZZZZZ"])
    def test_billing_pay_rejects_malformed_ids(self, client, bad):
        r = client.get(f"/billing/pay/{bad}")
        assert r.status_code == 404
        assert bad not in r.text

    def test_billing_confirm_does_not_echo_unknown_id(self, client):
        r = client.post("/billing/confirm", json={"order_id": "AF-DEADBEEF"})
        assert r.status_code == 404
        assert "DEADBEEF" not in r.text

    def test_csv_cells_cannot_start_a_formula(self):
        from whatsapp_bot.server import _csv_safe_cell
        assert _csv_safe_cell("=HYPERLINK(...)") == "'=HYPERLINK(...)"
        assert _csv_safe_cell("+1") == "'+1"
        assert _csv_safe_cell("-1") == "'-1"
        assert _csv_safe_cell("@cmd") == "'@cmd"
        assert _csv_safe_cell("Kota Malang") == "Kota Malang"
        assert _csv_safe_cell(-1.5) == -1.5  # numbers untouched

    def test_report_csv_still_downloads(self, client):
        r = client.get("/api/v1/report.csv")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        assert r.headers["cache-control"] == "no-store"
