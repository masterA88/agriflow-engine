"""
AgriFlow Data Sources Package
==============================

Connector untuk semua sumber data eksternal yang dipakai matching engine.

Modules:
    pihps_bi          — Harga harian Tier 1 IHK (BI PIHPS)
    bapanas           — Harga mingguan Tier 2 (Bapanas Panel Harga)
    bps               — IPM 2024 + produksi (BPS WebAPI)
    bmkg              — Forecast cuaca (BMKG + Open-Meteo fallback)
    pvmbg             — Erupsi gunung api (PVMBG MAGMA)
    bnpb              — Bencana aktif (BNPB DIBI)
    google_maps       — Routing (Google Routes API + OSRM fallback)
    hijri_calendar    — Detect Ramadan/Idul Fitri (Aladhan + hardcoded)

Setiap connector punya:
    - Real mode (live API)
    - Mock mode (offline, baca sample_data CSV)
    - Fallback handling (graceful degradation)

Usage standar di engine:
    from data_sources import (
        get_pihps_prices, get_bapanas_weekly, get_ipm_jatim,
        get_route_weather, get_unreachable_kabupaten,
    )
"""

from .pihps_bi import PIHPSConnector, get_pihps_prices, TIER1_KOTA_IHK
from .siskaperbapo import SiskaperbapoClient, scrape_range as scrape_siskaperbapo
from .bapanas import BapanasConnector, get_bapanas_weekly
from .bps import BPSConnector, IPM_2024_JATIM, get_ipm_jatim
from .bmkg import WeatherConnector, get_route_weather
from .pvmbg import PVMBGConnector, get_unreachable_kabupaten, GUNUNG_KABUPATEN_MAP
from .bnpb import BNPBConnector, get_disaster_affected_kabupaten
from .google_maps import RouteConnector, get_route
from .hijri_calendar import HijriCalendarConnector, is_ramadan_period

__all__ = [
    # PIHPS
    "PIHPSConnector", "get_pihps_prices", "TIER1_KOTA_IHK",
    # Siskaperbapo
    "SiskaperbapoClient", "scrape_siskaperbapo",
    # Bapanas
    "BapanasConnector", "get_bapanas_weekly",
    # BPS
    "BPSConnector", "IPM_2024_JATIM", "get_ipm_jatim",
    # BMKG
    "WeatherConnector", "get_route_weather",
    # PVMBG
    "PVMBGConnector", "get_unreachable_kabupaten", "GUNUNG_KABUPATEN_MAP",
    # BNPB
    "BNPBConnector", "get_disaster_affected_kabupaten",
    # Routing
    "RouteConnector", "get_route",
    # Hijri
    "HijriCalendarConnector", "is_ramadan_period",
]
