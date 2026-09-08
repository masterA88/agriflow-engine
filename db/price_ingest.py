"""Offline price-history loading and optional Postgres ingestion for AgriFlow.

The legacy :func:`load_price_history_csvs` function intentionally remains PIHPS-only
and returns its original four-field row contract. New integrations must explicitly
use :func:`load_source_price_history_csvs` and :func:`select_active_prices`:

* PIHPS `*_cleaned.csv` files and Siskaperbapo `*_jatim.csv` files are read separately.
* Every source record retains `data_source` provenance.
* PIHPS sub-grades may be averaged within PIHPS after commodity normalisation.
* A valid Siskaperbapo district median wins only for the identical
  `(date, city_id, commodity_code)` key; PIHPS is the fallback.
* The two sources are never averaged together.
"""

from __future__ import annotations

import csv
import datetime
import math
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

PIHPS_SOURCE = "PIHPS"
SISKAPERBAPO_SOURCE = "SISKAPERBAPO"
_REQUIRED_COLUMNS = frozenset({"date", "city_id", "commodity_code", "price_per_kg"})

# ---------------------------------------------------------------------------
# Commodity code normalisation table
# Keys:   commodity_code values as they appear in PIHPS/Siskaperbapo CSV files
# Values: AgriFlow canonical codes (must match commodity.code in schema.sql)
# ---------------------------------------------------------------------------
COMMODITY_MAP: Dict[str, str] = {
    # Direct matches — no change needed, but listed explicitly for clarity
    "bawang_merah": "bawang_merah",
    "bawang_putih": "bawang_putih",
    "daging_ayam":  "daging_ayam",
    "telur_ayam":   "telur_ayam",
    # Spelling normalisation: source uses Indonesian colloquial 'cabe', engine uses BI 'cabai'
    "cabe_rawit":   "cabai_rawit",
    # Rice grade aggregation: source sub-grades → AgriFlow canonical grades
    "beras_medium_1": "beras_medium",
    "beras_medium_2": "beras_medium",
    "beras_super_1":  "beras_premium",
    "beras_super_2":  "beras_premium",
}

# Canonical codes that ENGINE knows about (subset of komoditas_constraints.csv
# that this dataset covers). Used for validation.
KNOWN_ENGINE_CODES = frozenset(COMMODITY_MAP.values())


def _normalise_row(csv_path: Path, lineno: int, row: Dict[str, str], source: str) -> Dict:
    """Validate one shared price-history row and attach its trusted source label."""
    try:
        raw_code = row["commodity_code"].strip()
        canonical = COMMODITY_MAP.get(raw_code)
        if canonical is None:
            raise ValueError(
                f"{csv_path.name}:{lineno}: unrecognised commodity_code {raw_code!r} "
                "— add it to COMMODITY_MAP in db/price_ingest.py"
            )
        date_val = datetime.date.fromisoformat(row["date"].strip())
        city_id = row["city_id"].strip()
        price = float(row["price_per_kg"].strip())
    except KeyError as exc:
        raise ValueError(f"{csv_path.name}:{lineno}: missing required column {exc.args[0]!r}") from exc
    except ValueError as exc:
        if str(exc).startswith(f"{csv_path.name}:{lineno}:"):
            raise
        raise ValueError(f"{csv_path.name}:{lineno}: invalid date or price") from exc

    if not city_id:
        raise ValueError(f"{csv_path.name}:{lineno}: city_id must not be empty")
    if not math.isfinite(price) or price <= 0:
        raise ValueError(f"{csv_path.name}:{lineno}: price_per_kg must be finite and positive")

    return {
        "date": date_val,
        "city_id": city_id,
        "commodity_code": canonical,
        "price_per_kg": price,
        "data_source": source,
    }


def _read_source_file(csv_path: Path, source: str) -> List[Dict]:
    """Read a single source file using the common four-column CSV contract."""
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or ())
        missing = sorted(_REQUIRED_COLUMNS - fieldnames)
        if missing:
            raise ValueError(f"{csv_path.name}: missing required columns: {', '.join(missing)}")
        return [
            _normalise_row(csv_path, lineno, row, source)
            for lineno, row in enumerate(reader, start=2)
        ]


def _aggregate_pihps(records: Iterable[Dict]) -> List[Dict]:
    """Average only PIHPS rows that collapse after sub-grade normalisation."""
    accumulated: Dict[Tuple[datetime.date, str, str], List[float]] = {}
    for row in records:
        key = (row["date"], row["city_id"], row["commodity_code"])
        accumulated.setdefault(key, []).append(row["price_per_kg"])

    result = [
        {
            "date": date_val,
            "city_id": city_id,
            "commodity_code": commodity_code,
            "price_per_kg": sum(prices) / len(prices),
            "data_source": PIHPS_SOURCE,
        }
        for (date_val, city_id, commodity_code), prices in accumulated.items()
    ]
    result.sort(key=lambda row: (row["commodity_code"], row["city_id"], row["date"]))
    return result


def _assert_unique_siskaperbapo(records: Iterable[Dict]) -> List[Dict]:
    """Reject duplicate derived district medians instead of masking bad input."""
    result = list(records)
    seen: set[Tuple[datetime.date, str, str]] = set()
    for row in result:
        key = (row["date"], row["city_id"], row["commodity_code"])
        if key in seen:
            raise ValueError(
                "Duplicate Siskaperbapo record for "
                f"date={key[0].isoformat()}, city_id={key[1]!r}, commodity_code={key[2]!r}"
            )
        seen.add(key)
    return result


def load_source_price_history_csvs(directory: str | Path) -> List[Dict]:
    """Load PIHPS and Siskaperbapo records with provenance, without precedence.

    PIHPS input is discovered with ``*_cleaned.csv`` and Siskaperbapo derived
    district-median input with ``*_jatim.csv``. The returned rows always contain
    ``date``, ``city_id``, ``commodity_code``, ``price_per_kg``, and ``data_source``.
    Valid records from both sources are retained for comparison. Use
    :func:`select_active_prices` to apply Siskaperbapo-first precedence.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"Price history directory not found: {directory}")

    pihps_files = sorted(directory.glob("*_cleaned.csv"))
    siskaperbapo_files = sorted(directory.glob("*_jatim.csv"))
    if not pihps_files and not siskaperbapo_files:
        raise FileNotFoundError(
            "No recognised PIHPS *_cleaned.csv or Siskaperbapo *_jatim.csv files "
            f"found in: {directory}"
        )

    pihps_records = _aggregate_pihps(
        row
        for csv_path in pihps_files
        for row in _read_source_file(csv_path, PIHPS_SOURCE)
    )
    siskaperbapo_records = _assert_unique_siskaperbapo(
        row
        for csv_path in siskaperbapo_files
        for row in _read_source_file(csv_path, SISKAPERBAPO_SOURCE)
    )
    rows = pihps_records + siskaperbapo_records
    rows.sort(
        key=lambda row: (
            row["commodity_code"], row["city_id"], row["date"], row["data_source"]
        )
    )
    return rows


def select_active_prices(source_records: Iterable[Dict]) -> List[Dict]:
    """Select Siskaperbapo first and PIHPS only as exact-key fallback.

    The input must contain source-aware records from
    :func:`load_source_price_history_csvs`. This function retains no hidden state
    and never averages records belonging to different sources.
    """
    selected: Dict[Tuple[datetime.date, str, str], Dict] = {}
    seen_source_keys: set[Tuple[datetime.date, str, str, str]] = set()
    for row in source_records:
        source = row.get("data_source")
        if source not in {PIHPS_SOURCE, SISKAPERBAPO_SOURCE}:
            raise ValueError(f"Unsupported data_source {source!r}")
        key = (row["date"], row["city_id"], row["commodity_code"])
        source_key = (*key, source)
        if source_key in seen_source_keys:
            raise ValueError(
                "Duplicate source record for "
                f"date={key[0].isoformat()}, city_id={key[1]!r}, "
                f"commodity_code={key[2]!r}, data_source={source!r}"
            )
        seen_source_keys.add(source_key)
        if source == SISKAPERBAPO_SOURCE or key not in selected:
            selected[key] = row

    rows = list(selected.values())
    rows.sort(key=lambda row: (row["commodity_code"], row["city_id"], row["date"]))
    return rows


def load_price_history_csvs(directory: str | Path) -> List[Dict]:
    """Load legacy PIHPS ``*_cleaned.csv`` data using the original four-field contract.

    This compatibility API intentionally ignores ``*_jatim.csv`` Siskaperbapo
    files. New callers that need source provenance and precedence must use
    :func:`load_source_price_history_csvs` followed by :func:`select_active_prices`.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"Price history directory not found: {directory}")

    pihps_files = sorted(directory.glob("*_cleaned.csv"))
    if not pihps_files:
        raise FileNotFoundError(f"No *_cleaned.csv files found in: {directory}")

    pihps_rows = _aggregate_pihps(
        row
        for csv_path in pihps_files
        for row in _read_source_file(csv_path, PIHPS_SOURCE)
    )
    return [
        {
            "date": row["date"],
            "city_id": row["city_id"],
            "commodity_code": row["commodity_code"],
            "price_per_kg": row["price_per_kg"],
        }
        for row in pihps_rows
    ]


def ingest_to_postgres(rows: List[Dict], db_url: str) -> int:
    """
    Upsert `rows` (as returned by load_price_history_csvs) into the
    price_history table.

    GATED: db_url must be a non-empty string.  Pass an explicit DSN — this
    function never reads environment variables, so callers stay in control.

    SQL used: INSERT ... ON CONFLICT (date, city_id, commodity_code) DO UPDATE
    so the operation is idempotent and safe to re-run.

    Returns the number of rows upserted.

    Requires: sqlalchemy + psycopg2-binary installed.
    """
    if not db_url or not db_url.strip():
        raise RuntimeError(
            "ingest_to_postgres() requires an explicit db_url (non-empty string). "
            "Pass the Supabase DSN directly — this function never reads env vars."
        )

    try:
        from sqlalchemy import create_engine, text  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "sqlalchemy is not installed. Run: pip install sqlalchemy psycopg2-binary"
        ) from exc

    engine = create_engine(db_url, pool_pre_ping=True, future=True)
    upsert_sql = text("""
        INSERT INTO price_history (date, city_id, commodity_code, price_per_kg, data_source)
        VALUES (:date, :city_id, :commodity_code, :price_per_kg, 'PIHPS')
        ON CONFLICT (date, city_id, commodity_code)
        DO UPDATE SET
            price_per_kg = EXCLUDED.price_per_kg,
            data_source  = EXCLUDED.data_source
    """)

    count = 0
    with engine.begin() as conn:
        for row in rows:
            conn.execute(
                upsert_sql,
                {
                    "date":           row["date"],
                    "city_id":        row["city_id"],
                    "commodity_code": row["commodity_code"],
                    "price_per_kg":   row["price_per_kg"],
                },
            )
            count += 1

    return count


def latest_prices(rows: List[Dict]) -> Dict[Tuple[str, str], float]:
    """
    Return the most-recent observed price per (city_id, commodity_code) pair.

    Input: the list returned by load_price_history_csvs().
    Output: dict[(city_id, commodity_code)] -> price_per_kg (float)

    "Most recent" is determined by the date field (datetime.date comparison).
    When multiple rows exist for the same key, the one with the latest date wins.

    Usage pattern (replacing synthetic Tier-1 prices in the engine):

        from db.price_ingest import load_price_history_csvs, latest_prices

        price_dir = Path("sample_data/price_history")
        rows = load_price_history_csvs(price_dir)
        latest = latest_prices(rows)

        # In the Tier-1 node builder:
        real_price = latest.get(
            (node.kabupaten.id, node.commodity.code),
            node.price_per_kg  # fallback: keep synthetic if no real data
        )
    """
    best: Dict[Tuple[str, str], Tuple[datetime.date, float]] = {}
    for row in rows:
        key = (row["city_id"], row["commodity_code"])
        date_val: datetime.date = row["date"]
        price: float = row["price_per_kg"]
        if key not in best or date_val > best[key][0]:
            best[key] = (date_val, price)

    return {k: v[1] for k, v in best.items()}
