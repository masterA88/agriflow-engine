"""
analysis/precompute_anomalies.py  --  Precompute all Hampel/MAD (deseasonalised) anomalies to JSON.

Run offline (locally or in CI) to produce sample_data/anomalies/anomalies_all.json.
The backend serves from this file at runtime -- zero runtime computation on HF Space.

Usage:
    python analysis/precompute_anomalies.py
    python analysis/precompute_anomalies.py --price-dir sample_data/price_history
                                             --out-dir sample_data/anomalies

Output is a versioned source-aware artifact object with all 266 region/commodity
status members and zero or more provenance-bearing anomaly events.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.price_anomaly import (
    ACTIVE_SOURCE_POLICY,
    ANOMALY_ARTIFACT_SCHEMA_VERSION,
    build_source_aware_anomaly_result,
)
from db.price_ingest import load_source_price_history_csvs, select_active_prices

# Honest method label served by the API (was "shesd_v2" until v1.1, see audit F3).
ANOMALY_METHOD = "hampel_mad_v2"


def _utc_timestamp(value: datetime.datetime | None = None) -> datetime.datetime:
    """Capture one UTC instant for all metadata in a single artifact."""
    timestamp = value or datetime.datetime.now(datetime.timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
    return timestamp.astimezone(datetime.timezone.utc)


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Publish a complete artifact, never a partially written JSON document."""
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent,
        prefix=f".{path.name}.", suffix=".tmp", delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temp_path, path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def build_artifact(
    active_records: list[dict],
    generated_at: datetime.datetime | None = None,
) -> dict:
    """Build the versioned artifact from selected source-aware observations."""
    timestamp = _utc_timestamp(generated_at)
    statuses, events = build_source_aware_anomaly_result(active_records, timestamp)
    return {
        "schema_version": ANOMALY_ARTIFACT_SCHEMA_VERSION,
        "artifact_type": "source_aware_anomaly",
        "generated_at": timestamp.isoformat().replace("+00:00", "Z"),
        "method": "shesd_v2",
        "active_source_policy": ACTIVE_SOURCE_POLICY,
        "series_statuses": statuses,
        "events": events,
    }


def main(
    price_dir: Path,
    out_dir: Path,
    generated_at: datetime.datetime | None = None,
) -> dict:
    """Load, select, evaluate, and atomically publish one anomaly artifact."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "anomalies_all.json"

    print(f"Loading source-aware price history from {price_dir} ...")
    source_records = load_source_price_history_csvs(price_dir)
    active_records = select_active_prices(source_records)
    artifact = build_artifact(active_records, generated_at)
    _atomic_write_json(out_path, artifact)

    size_kb = out_path.stat().st_size / 1024
    print(
        f"  Wrote {len(artifact['series_statuses'])} statuses and "
        f"{len(artifact['events'])} events to {out_path} ({size_kb:.1f} KB)"
    )
    return artifact

    # v1.1: provenance sidecar so the API can report "data per" honestly.
    import datetime as _dt
    dates = sorted(r["date"] for r in records)
    meta = {
        "method": ANOMALY_METHOD,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "params": {"window": 30, "k": 3.0, "trend_window": 30, "persist": 2},
        "n_records": len(records),
        "first_anomaly_date": dates[0] if dates else None,
        "last_anomaly_date": dates[-1] if dates else None,
        "price_dir": str(price_dir),
    }
    with (out_dir / "meta.json").open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)
    print(f"  Wrote provenance to {out_dir / 'meta.json'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Precompute Hampel/MAD anomaly scan to JSON.")
    parser.add_argument(
        "--price-dir",
        type=Path,
        default=ROOT / "sample_data" / "price_history",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "sample_data" / "anomalies",
    )
    args = parser.parse_args()
    main(args.price_dir, args.out_dir)
