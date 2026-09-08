"""
analysis/anomaly_gate.py  --  Bridge between the batch anomaly scan and the
engine's D3 pre-filter.

WHY THIS EXISTS
---------------
Until v1.1 the engine's D3 gate (matching_engine/engine.py) used its own
3-sigma z-score against a per-commodity (median, std) pair, while the
dashboard served anomalies from the deseasonalised Hampel/MAD scanner in
analysis/price_anomaly.py. benchmarks/anomaly_detector_gap.py measured the
z-score gate recalling only 14.4% of the scanner's persistent anomalies, and
a D3 hit removes a node from matching entirely. Two detectors, two answers.

This module turns the scanner's output into the set the engine consumes:
    {(city_id, commodity_code), ...}
for anomalies that are still "live" as of a reference date. The engine then
excludes exactly those nodes, so the panel and the matcher agree.

The file is pure Python with no heavy imports so the API server can call it
at startup without pulling numpy.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Iterable, Optional, Set, Tuple

AnomalyKey = Tuple[str, str]  # (city_id / kab_id, commodity_code)

DEFAULT_WINDOW_DAYS = 14


def _parse_date(value: str) -> _dt.date:
    return _dt.date.fromisoformat(value[:10])


def recent_anomaly_keys(
    records: Iterable[dict],
    as_of: Optional[_dt.date] = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    persistent_only: bool = True,
) -> Set[AnomalyKey]:
    """
    Reduce scanner records to the (city_id, commodity_code) pairs that had an
    anomaly inside the last `window_days` ending at `as_of`.

    as_of defaults to the newest anomaly date in the records, which for the
    committed 2021 to 2025 PIHPS scan is the end of the series. Pass an
    explicit date in production once ingestion is scheduled.

    persistent_only keeps the scanner's own persistence rule (flag must last
    two or more days) so a single-day blip never removes a kabupaten from the
    matching pool.
    """
    records = list(records)
    if not records:
        return set()
    dates = [_parse_date(r["date"]) for r in records if r.get("date")]
    if not dates:
        return set()
    if as_of is None:
        as_of = max(dates)
    cutoff = as_of - _dt.timedelta(days=window_days)

    keys: Set[AnomalyKey] = set()
    for r in records:
        if persistent_only and not r.get("persistent", False):
            continue
        d = _parse_date(r["date"])
        if cutoff <= d <= as_of:
            keys.add((str(r["city_id"]), str(r["commodity_code"])))
    return keys


def load_anomaly_keys(
    path: str | Path,
    as_of: Optional[_dt.date] = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    persistent_only: bool = True,
) -> Set[AnomalyKey]:
    """Read anomalies_all.json and return the live-anomaly key set."""
    p = Path(path)
    if not p.exists():
        return set()
    with p.open(encoding="utf-8") as fh:
        records = json.load(fh)
    # Source-aware artifact (schema v2+) wraps the flat event list in a dict
    # under "events"; older scans were a bare list. Accept both.
    if isinstance(records, dict):
        records = records.get("events", [])
    return recent_anomaly_keys(
        records, as_of=as_of, window_days=window_days,
        persistent_only=persistent_only,
    )


def latest_anomaly_date(path: str | Path) -> Optional[_dt.date]:
    """Newest anomaly date in the scan file, or None if the file is missing."""
    p = Path(path)
    if not p.exists():
        return None
    with p.open(encoding="utf-8") as fh:
        records = json.load(fh)
    if isinstance(records, dict):
        records = records.get("events", [])
    dates = [_parse_date(r["date"]) for r in records if r.get("date")]
    return max(dates) if dates else None
