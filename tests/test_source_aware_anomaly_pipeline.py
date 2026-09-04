"""Focused contracts for the source-aware offline anomaly artifact."""
from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis import precompute_anomalies as precompute
from analysis.price_anomaly import (
    ACTIVE_SOURCE_POLICY,
    ANOMALY_ARTIFACT_SCHEMA_VERSION,
    SUPPORTED_ANOMALY_COMMODITIES,
    build_source_aware_anomaly_result,
    load_anomaly_region_registry,
)
from db.price_ingest import load_source_price_history_csvs, select_active_prices

FIXED_TIME = dt.datetime(2026, 1, 31, 12, 0, tzinfo=dt.timezone.utc)


def _write_csv(path: Path, rows: list[tuple[str, str, str, float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("date", "city_id", "commodity_code", "price_per_kg"))
        writer.writerows(rows)


def _records(city_id: str, commodity: str, count: int, source: str = "SISKAPERBAPO") -> list[dict]:
    start = dt.date(2026, 1, 1)
    return [
        {
            "date": start + dt.timedelta(days=index),
            "city_id": city_id,
            "commodity_code": commodity,
            "price_per_kg": 10_000.0,
            "data_source": source,
        }
        for index in range(count)
    ]


def _status(statuses: list[dict], city_id: str, commodity: str) -> dict:
    return next(
        item for item in statuses
        if item["city_id"] == city_id and item["commodity_code"] == commodity
    )


def test_public_loader_selects_exact_key_sources_without_cross_source_mean(tmp_path: Path) -> None:
    """The public seam retains source provenance and never blends the two sources."""
    _write_csv(tmp_path / "bawang_merah_cleaned.csv", [
        ("2026-01-01", "3501", "bawang_merah", 100.0),
        ("2026-01-02", "3501", "bawang_merah", 110.0),
    ])
    _write_csv(tmp_path / "bawang_merah_jatim.csv", [
        ("2026-01-01", "3501", "bawang_merah", 300.0),
        ("2026-01-03", "3501", "bawang_merah", 999_999.0),
    ])
    raw_evidence = tmp_path / "siskaperbapo_raw.csv"
    exclusion_audit = tmp_path / "siskaperbapo_excluded_records.csv"
    raw_evidence.write_bytes(b"immutable-market-observation,999999\\n")
    exclusion_audit.write_bytes(b"date,reason\\n")
    before = {path: path.read_bytes() for path in (raw_evidence, exclusion_audit)}

    source_records = load_source_price_history_csvs(tmp_path)
    selected = select_active_prices(source_records)

    assert [(row["date"].isoformat(), row["price_per_kg"], row["data_source"]) for row in selected] == [
        ("2026-01-01", 300.0, "SISKAPERBAPO"),
        ("2026-01-02", 110.0, "PIHPS"),
        ("2026-01-03", 999_999.0, "SISKAPERBAPO"),
    ]
    assert all(row["price_per_kg"] != 200.0 for row in selected)
    assert {path: path.read_bytes() for path in before} == before


def test_source_aware_statuses_are_complete_and_gate_detector_history() -> None:
    records = (
        _records("3501", "bawang_merah", 30)
        + _records("3502", "bawang_putih", 29, "PIHPS")
    )
    statuses, events = build_source_aware_anomaly_result(records, FIXED_TIME)

    assert len(statuses) == 38 * 7 == 266
    assert len({(item["city_id"], item["commodity_code"]) for item in statuses}) == 266
    assert [item["commodity_code"] for item in statuses[:7]] == list(SUPPORTED_ANOMALY_COMMODITIES)
    assert _status(statuses, "3501", "bawang_merah")["series_status"] == "DETECTABLE"
    assert _status(statuses, "3502", "bawang_putih")["series_status"] == "INSUFFICIENT_HISTORY"
    assert _status(statuses, "3503", "cabai_rawit")["series_status"] == "NO_ACTIVE_HISTORY"
    assert not [event for event in events if event["city_id"] == "3502"]


def test_status_metadata_has_honest_coverage_freshness_and_source_counts() -> None:
    records = _records("3501", "bawang_merah", 30)
    records[-1]["data_source"] = "PIHPS"
    statuses, _ = build_source_aware_anomaly_result(records, FIXED_TIME)
    status = _status(statuses, "3501", "bawang_merah")
    no_history = _status(statuses, "3502", "bawang_merah")

    assert status["history_start_date"] == "2026-01-01"
    assert status["latest_observation_date"] == "2026-01-30"
    assert status["history_coverage_ratio"] == 1.0
    assert status["history_confidence"] == "HIGH"
    assert status["observation_freshness_days"] == 1
    assert status["active_history_source_counts"] == {"SISKAPERBAPO": 29, "PIHPS": 1}
    assert status["latest_observation_source"] == "PIHPS"
    assert sum(status["active_history_source_counts"].values()) == status["observation_count"]
    assert status["latest_observation_source"] in status["active_history_source_counts"]
    assert status["market_quality"] is None
    assert status["market_quality_availability"] == "UNAVAILABLE_DERIVED_FILE_HAS_FOUR_COLUMNS"
    assert all(no_history[field] is None for field in (
        "history_start_date", "latest_observation_date", "history_coverage_ratio",
        "history_confidence", "latest_observation_source", "observation_freshness_days",
    ))
    assert no_history["active_history_source_counts"] == {"SISKAPERBAPO": 0, "PIHPS": 0}


def test_detectable_event_has_selected_observation_provenance() -> None:
    records = _records("3501", "bawang_merah", 60)
    for index in (35, 36, 37):
        records[index]["price_per_kg"] = 40_000.0
    statuses, events = build_source_aware_anomaly_result(records, FIXED_TIME)

    assert _status(statuses, "3501", "bawang_merah")["series_status"] == "DETECTABLE"
    assert events
    event = events[0]
    assert event["city_id"] == "3501"
    assert event["observation_provenance"] == {
        "data_source": "SISKAPERBAPO",
        "observation_date": event["date"],
        "price_per_kg": event["price"],
    }


def test_registry_requires_exactly_38_unique_nonempty_entries(tmp_path: Path) -> None:
    bad_registry = tmp_path / "kabupaten_jatim.csv"
    bad_registry.write_text("kab_id,nama\n3501,Pacitan\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly 38"):
        load_anomaly_region_registry(bad_registry)


def test_precompute_uses_public_loader_sequence_and_writes_versioned_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    selected = _records("3501", "bawang_merah", 30)

    def fake_load(price_dir: Path) -> list[dict]:
        calls.append("load")
        assert price_dir == tmp_path / "prices"
        return [{"raw": "source-record"}]

    def fake_select(source_records: list[dict]) -> list[dict]:
        calls.append("select")
        assert source_records == [{"raw": "source-record"}]
        return selected

    monkeypatch.setattr(precompute, "load_source_price_history_csvs", fake_load)
    monkeypatch.setattr(precompute, "select_active_prices", fake_select)
    artifact = precompute.main(tmp_path / "prices", tmp_path / "out", FIXED_TIME)
    written = json.loads((tmp_path / "out" / "anomalies_all.json").read_text(encoding="utf-8"))

    assert calls == ["load", "select"]
    assert artifact == written
    assert written["schema_version"] == ANOMALY_ARTIFACT_SCHEMA_VERSION
    assert written["artifact_type"] == "source_aware_anomaly"
    assert written["generated_at"] == "2026-01-31T12:00:00Z"
    assert written["active_source_policy"] == ACTIVE_SOURCE_POLICY
    assert len(written["series_statuses"]) == 266
    assert isinstance(written["events"], list)
    assert not list((tmp_path / "out").glob(".*.tmp"))
    first_bytes = (tmp_path / "out" / "anomalies_all.json").read_bytes()
    precompute.main(tmp_path / "prices", tmp_path / "out", FIXED_TIME)
    assert (tmp_path / "out" / "anomalies_all.json").read_bytes() == first_bytes


def test_history_confidence_thresholds_are_inclusive_and_not_guessed() -> None:
    high = _records("3501", "daging_ayam", 30)
    medium = _records("3502", "daging_ayam", 30)
    low = _records("3503", "daging_ayam", 30)
    for index, row in enumerate(medium):
        row["date"] = dt.date(2026, 1, 1) + dt.timedelta(days=round(index * 39 / 29))
    for index, row in enumerate(low):
        row["date"] = dt.date(2026, 1, 1) + dt.timedelta(days=round(index * 59 / 29))

    statuses, _ = build_source_aware_anomaly_result(high + medium + low, FIXED_TIME)

    assert _status(statuses, "3501", "daging_ayam")["history_confidence"] == "HIGH"
    assert _status(statuses, "3502", "daging_ayam")["history_confidence"] == "MEDIUM"
    assert _status(statuses, "3503", "daging_ayam")["history_confidence"] == "LOW"
