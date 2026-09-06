"""
Pytest fixtures untuk semua scenario tests.
"""
import sys
import os
from datetime import datetime, timedelta

import pytest

# Add project root ke path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# The API rate limiter is per client IP and every TestClient shares one
# address, so the whole suite would trip it. Off by default here; the tests
# in test_security_hardening.py switch it on explicitly.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from matching_engine.models import (
    Commodity, DemandNode, EmergencyMode, Kabupaten, LogisticsContext,
    SupplyNode, Tier, WeatherForecast,
)


# =============================================================================
# Komoditas fixtures (subset untuk testing — 19 ada di constraints.py)
# =============================================================================

@pytest.fixture
def cabai_merah():
    return Commodity(
        code="cabai_merah", nama="Cabai Merah Besar",
        max_distance_km=200, min_viable_tons=1.0, max_fresh_age_days=5,
    )


@pytest.fixture
def bawang_merah():
    return Commodity(
        code="bawang_merah", nama="Bawang Merah",
        max_distance_km=400, min_viable_tons=2.0, max_fresh_age_days=30,
    )


@pytest.fixture
def beras_premium():
    return Commodity(
        code="beras_premium", nama="Beras Premium",
        max_distance_km=800, min_viable_tons=5.0, max_fresh_age_days=180,
    )


@pytest.fixture
def beras_medium():
    return Commodity(
        code="beras_medium", nama="Beras Medium",
        max_distance_km=800, min_viable_tons=5.0, max_fresh_age_days=180,
    )


# =============================================================================
# Kabupaten fixtures — sample dari Jatim
# =============================================================================

@pytest.fixture
def surabaya():
    """Tier 1, IPM 84.69, no equity boost. Pasar besar."""
    return Kabupaten(
        id="3578", nama="Kota Surabaya",
        latitude=-7.2575, longitude=112.7521,
        ipm=84.69, tier=Tier.HIGH,
    )


@pytest.fixture
def kediri_kab():
    """Tier 2, IPM 74.50. Sentra cabai."""
    return Kabupaten(
        id="3506", nama="Kediri",
        latitude=-7.7960, longitude=112.1700,
        ipm=74.50, tier=Tier.MEDIUM,
    )


@pytest.fixture
def kota_kediri():
    """Tier 1, IPM 81.48."""
    return Kabupaten(
        id="3571", nama="Kota Kediri",
        latitude=-7.8166, longitude=112.0114,
        ipm=81.48, tier=Tier.HIGH,
    )


@pytest.fixture
def sampang():
    """Tier 2, IPM 66.72 — equity boost +30% (range <68, BPS 2024 kalibrasi)."""
    return Kabupaten(
        id="3527", nama="Sampang",
        latitude=-7.1924, longitude=113.2473,
        ipm=66.72, tier=Tier.MEDIUM,
    )


@pytest.fixture
def sampang_severe():
    """Hypothetical: kab dengan IPM jauh di bawah 68 untuk test threshold."""
    return Kabupaten(
        id="9999", nama="Hypothetical-Severe",
        latitude=-7.1924, longitude=113.2473,
        ipm=62.0, tier=Tier.MEDIUM,
    )


@pytest.fixture
def bangkalan():
    """Tier 2, IPM 67.70 — equity boost +30% (range <68)."""
    return Kabupaten(
        id="3526", nama="Bangkalan",
        latitude=-7.0317, longitude=112.7491,
        ipm=67.70, tier=Tier.MEDIUM,
    )


@pytest.fixture
def pamekasan():
    """Tier 2, IPM 70.43 — equity boost +15% (range 68-72)."""
    return Kabupaten(
        id="3528", nama="Pamekasan",
        latitude=-7.1565, longitude=113.4785,
        ipm=70.43, tier=Tier.MEDIUM,
    )


@pytest.fixture
def sumenep():
    """Tier 1 IHK, IPM 68.79 — equity boost +15% (range 68-72)."""
    return Kabupaten(
        id="3529", nama="Sumenep",
        latitude=-7.0067, longitude=113.8525,
        ipm=68.79, tier=Tier.HIGH,
    )


@pytest.fixture
def bondowoso():
    """Tier 2, IPM 69.62 — equity boost +15% (range 68-72)."""
    return Kabupaten(
        id="3511", nama="Bondowoso",
        latitude=-7.9134, longitude=113.8217,
        ipm=69.62, tier=Tier.MEDIUM,
    )


@pytest.fixture
def pacitan():
    """Tier 2, IPM 71.40 — equity boost +15% (range 68-72). Pinggir barat Jatim."""
    return Kabupaten(
        id="3501", nama="Pacitan",
        latitude=-8.1985, longitude=111.1014,
        ipm=71.40, tier=Tier.MEDIUM,
    )


@pytest.fixture
def banyuwangi():
    """Tier 1 IHK, IPM 73.45 — equity boost +5% (range 72-78). Pinggir timur Jatim."""
    return Kabupaten(
        id="3510", nama="Banyuwangi",
        latitude=-8.2192, longitude=114.3691,
        ipm=73.45, tier=Tier.HIGH,
    )


@pytest.fixture
def sidoarjo():
    """Tier 2, IPM 80.13 — no equity boost. Pasar besar."""
    return Kabupaten(
        id="3515", nama="Sidoarjo",
        latitude=-7.4549, longitude=112.7178,
        ipm=80.13, tier=Tier.MEDIUM,
    )


@pytest.fixture
def gresik():
    """Tier 2, IPM 77.61 — no equity boost."""
    return Kabupaten(
        id="3525", nama="Gresik",
        latitude=-7.1568, longitude=112.6510,
        ipm=77.61, tier=Tier.MEDIUM,
    )


@pytest.fixture
def blitar_kab():
    """Tier 2, IPM 73.85 — equity boost +5%."""
    return Kabupaten(
        id="3505", nama="Blitar",
        latitude=-8.0950, longitude=112.1658,
        ipm=73.85, tier=Tier.MEDIUM,
    )


@pytest.fixture
def tulungagung():
    """Tier 2, IPM 75.30 — no equity boost."""
    return Kabupaten(
        id="3504", nama="Tulungagung",
        latitude=-8.0658, longitude=111.9028,
        ipm=75.30, tier=Tier.MEDIUM,
    )


@pytest.fixture
def trenggalek():
    """Tier 2, IPM 73.85 — equity boost +5%."""
    return Kabupaten(
        id="3503", nama="Trenggalek",
        latitude=-8.0497, longitude=111.7100,
        ipm=73.85, tier=Tier.MEDIUM,
    )


@pytest.fixture
def probolinggo_kab():
    """Tier 2, IPM 69.40 — equity boost +15%."""
    return Kabupaten(
        id="3513", nama="Probolinggo",
        latitude=-7.8742, longitude=113.4675,
        ipm=69.40, tier=Tier.MEDIUM,
    )


@pytest.fixture
def lumajang():
    """Tier 2, IPM 70.10 — equity boost +5%."""
    return Kabupaten(
        id="3508", nama="Lumajang",
        latitude=-8.1336, longitude=113.2245,
        ipm=70.10, tier=Tier.MEDIUM,
    )


# =============================================================================
# Logistics & weather fixtures
# =============================================================================

@pytest.fixture
def logistics_normal():
    return LogisticsContext(
        bbm_price_idr_per_liter=10000,
        bbm_price_baseline=10000,
    )


@pytest.fixture
def logistics_bbm_naik_20pct():
    """Skenario E5: BBM naik 20%."""
    return LogisticsContext(
        bbm_price_idr_per_liter=12000,
        bbm_price_baseline=10000,
    )


@pytest.fixture
def logistics_ramadan():
    """Skenario C1: pre-Ramadan H-14."""
    return LogisticsContext(is_ramadan_proximity=True)


@pytest.fixture
def weather_clear():
    """Cuaca cerah default — climate score = 1.0."""
    return {}  # no forecast = default 0.7 fallback or specific routes


@pytest.fixture
def weather_banjir():
    """Skenario D1: hujan deras 75mm di rute Kediri-Surabaya."""
    return {
        "3506_3578": WeatherForecast(
            origin_kab_id="3506", dest_kab_id="3578",
            max_rain_mm=75.0, transit_window_days=1,
        ),
        "3571_3578": WeatherForecast(
            origin_kab_id="3571", dest_kab_id="3578",
            max_rain_mm=75.0, transit_window_days=1,
        ),
    }


# =============================================================================
# Helper untuk membuat SupplyNode/DemandNode dengan defaults sane
# =============================================================================

@pytest.fixture
def make_supply():
    """Factory fixture untuk membuat SupplyNode."""
    def _make(kab, commodity, volume=50.0, price=40000, age=2):
        return SupplyNode(
            kabupaten=kab, commodity=commodity,
            volume_tons=volume, price_per_kg=price,
            harvest_age_days=age,
        )
    return _make


@pytest.fixture
def make_demand():
    """Factory fixture untuk membuat DemandNode."""
    def _make(kab, commodity, volume=50.0, price=60000):
        return DemandNode(
            kabupaten=kab, commodity=commodity,
            volume_tons=volume, price_per_kg=price,
        )
    return _make


@pytest.fixture
def make_stale_supply():
    """Factory untuk SupplyNode dengan timestamp lama (skenario C3)."""
    def _make(kab, commodity, hours_old=48, volume=50.0, price=40000, age=2):
        return SupplyNode(
            kabupaten=kab, commodity=commodity,
            volume_tons=volume, price_per_kg=price,
            harvest_age_days=age,
            timestamp=datetime.now() - timedelta(hours=hours_old),
        )
    return _make
