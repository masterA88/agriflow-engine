"""Normalise raw Siskaperbapo market prices into AgriFlow price-history CSVs.

Raw observations stay immutable in ``sample_data/raw_data``.  This module writes
one ``<commodity>_jatim.csv`` file per supported commodity, using the
median of valid market prices for each date and Kabupaten/Kota.
"""
from __future__ import annotations

import argparse
import csv
import re
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_DIR = ROOT / "sample_data" / "raw_data"
DEFAULT_OUTPUT_DIR = ROOT / "sample_data" / "price_history"
DEFAULT_KABUPATEN_CSV = ROOT / "sample_data" / "kabupaten_jatim.csv"
DEFAULT_AUDIT_PATH = DEFAULT_OUTPUT_DIR / "siskaperbapo_excluded_records.csv"

# Output codes deliberately follow the existing PIHPS price-history contract.
SUPPORTED_COMMODITIES = {
    "2": "beras_super_1",
    "4": "beras_medium_1",
    "13": "daging_ayam",
    "16": "telur_ayam",
    "39": "bawang_merah",
    "49": "bawang_putih",
    "50": "cabe_rawit",
}

# (start_date, end_date, kab/kota, market, commodity_id, malformed price)
# All entries below were manually verified in Siskaperbapo as source input errors.
CONFIRMED_INPUT_ERROR_RULES = (
    ("2021-05-15", "2021-05-15", "Kabupaten Kediri", "Pasar Pamenang", "16", 2200),
    ("2021-08-16", "2021-08-16", "Kota Madiun", "Pasar Srijaya", "16", 2100),
    ("2022-01-26", "2022-01-27", "Kabupaten Tulungagung", "Pasar Ngemplak", "16", 2000),
    ("2022-06-26", "2022-06-26", "Kabupaten Madiun", "Pasar Dolopo", "16", 2000),
    ("2022-09-17", "2022-09-17", "Kabupaten Lamongan", "Pasar Sidoharjo", "16", 2700),
    ("2022-10-19", "2022-10-27", "Kabupaten Banyuwangi", "Pasar Jajag", "16", 2500),
    ("2023-01-21", "2023-01-21", "Kabupaten Tulungagung", "Pasar Ngunut", "16", 2600),
    ("2023-03-30", "2023-03-30", "Kabupaten Ponorogo", "Pasar Legi", "16", 2000),
    ("2023-04-03", "2023-04-03", "Kabupaten Situbondo", "Pasar Sumber Kolak", "16", 6900),
    ("2023-05-18", "2023-05-18", "Kota Probolinggo", "Pasar Wonoasih", "16", 3100),
    ("2024-07-20", "2024-07-24", "Kabupaten Ponorogo", "Pasar Sumoroto", "16", 2600),
    ("2024-12-30", "2025-01-01", "Kabupaten Ponorogo", "Pasar Legi", "16", 3000),
    ("2025-11-29", "2025-11-29", "Kabupaten Tulungagung", "Pasar Bandung", "16", 280),
)


def _normalise_area_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name.strip().lower())
    return re.sub(r"^(kabupaten|kab\.)\s+", "", name)


def _is_confirmed_input_error(row: dict[str, str], price: int) -> bool:
    return any(
        start <= row["tanggal"] <= end
        and row["kab_kota"] == kab
        and row["pasar"] == pasar
        and row["komoditas_id"] == commodity_id
        and price == bad_price
        for start, end, kab, pasar, commodity_id, bad_price in CONFIRMED_INPUT_ERROR_RULES
    )


def _load_area_ids(kabupaten_csv: Path) -> dict[str, str]:
    with kabupaten_csv.open(newline="", encoding="utf-8") as handle:
        return {
            _normalise_area_name(row["nama"]): row["kab_id"].strip()
            for row in csv.DictReader(handle)
        }


def _raw_files(raw_dir: Path) -> list[Path]:
    files = sorted(raw_dir.glob("siskaperbapo_*_raw.csv"))
    if not files:
        raise FileNotFoundError(
            f"Tidak ada file raw Siskaperbapo di {raw_dir}. "
            "Jalankan data_sources/siskaperbapo.py terlebih dahulu."
        )
    return files


def _read_raw_rows(
    raw_dir: Path,
    area_ids: dict[str, str],
) -> tuple[list[dict[str, str]], list[str]]:
    """Read one or more commodity raw files, keeping the last duplicate row."""
    required = set(("tanggal", "kab_kota", "pasar", "komoditas_id", "komoditas_nama", "harga"))
    deduplicated: dict[tuple[str, str, str, str], dict[str, str]] = {}
    unmapped_areas: set[str] = set()
    skipped: list[str] = []

    for path in _raw_files(raw_dir):
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise ValueError(f"{path.name}: header raw tidak sesuai {sorted(required)}")
            for line_number, row in enumerate(reader, start=2):
                commodity_id = row["komoditas_id"].strip()
                if commodity_id not in SUPPORTED_COMMODITIES:
                    skipped.append(f"{path.name}:{line_number} komoditas_id={commodity_id}")
                    continue
                try:
                    date.fromisoformat(row["tanggal"].strip())
                    price = int(row["harga"].strip())
                except ValueError as exc:
                    raise ValueError(f"{path.name}:{line_number}: tanggal/harga tidak valid") from exc
                if price <= 0:
                    skipped.append(f"{path.name}:{line_number} harga tidak positif")
                    continue
                area_key = _normalise_area_name(row["kab_kota"])
                if area_key not in area_ids:
                    unmapped_areas.add(row["kab_kota"])
                    continue
                cleaned_row = {
                    key: row[key].strip() for key in required
                }
                cleaned_row["kab_id"] = area_ids[area_key]
                key = (
                    cleaned_row["tanggal"],
                    cleaned_row["kab_kota"],
                    cleaned_row["pasar"],
                    commodity_id,
                )
                # A later append is the latest available version from the source.
                deduplicated[key] = cleaned_row

    if unmapped_areas:
        names = ", ".join(sorted(unmapped_areas))
        raise ValueError(f"Nama kabupaten/kota belum punya mapping BPS: {names}")
    return list(deduplicated.values()), skipped


def _write_audit(audit_path: Path, excluded: Iterable[dict[str, str]]) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["tanggal", "kab_kota", "pasar", "komoditas_id", "komoditas_nama", "harga", "reason"]
    with audit_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(excluded)


def clean_siskaperbapo(
    raw_dir: Path = DEFAULT_RAW_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    kabupaten_csv: Path = DEFAULT_KABUPATEN_CSV,
    audit_path: Path = DEFAULT_AUDIT_PATH,
) -> dict[str, int]:
    """Create one daily median-price CSV per supported Siskaperbapo commodity.

    The original raw files are never edited.  Only manually confirmed source input
    errors are excluded; no statistical outlier is removed automatically.
    """
    area_ids = _load_area_ids(kabupaten_csv)
    raw_rows, skipped = _read_raw_rows(raw_dir, area_ids)
    groups: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    excluded: list[dict[str, str]] = []

    for row in raw_rows:
        price = int(row["harga"])
        if _is_confirmed_input_error(row, price):
            excluded.append({
                **{field: row[field] for field in ("tanggal", "kab_kota", "pasar", "komoditas_id", "komoditas_nama", "harga")},
                "reason": "CONFIRMED_SOURCE_INPUT_ERROR",
            })
            continue
        commodity_code = SUPPORTED_COMMODITIES[row["komoditas_id"]]
        groups[(commodity_code, row["kab_id"], row["tanggal"])].append(price)

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_audit(audit_path, excluded)
    by_commodity: dict[str, list[dict[str, str]]] = defaultdict(list)
    for (commodity_code, kab_id, observation_date), prices in sorted(groups.items()):
        by_commodity[commodity_code].append({
            "date": observation_date,
            "city_id": kab_id,
            "commodity_code": commodity_code,
            "price_per_kg": f"{statistics.median(prices):g}",
        })

    result: dict[str, int] = {}
    for commodity_code, rows in by_commodity.items():
        output_path = output_dir / f"{commodity_code}_jatim.csv"
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["date", "city_id", "commodity_code", "price_per_kg"],
            )
            writer.writeheader()
            writer.writerows(rows)
        result[commodity_code] = len(rows)

    print(f"Raw valid: {len(raw_rows):,}; excluded confirmed errors: {len(excluded):,}.")
    if skipped:
        print(f"Skipped unsupported/invalid rows: {len(skipped):,}.")
    for commodity_code, row_count in sorted(result.items()):
        print(f"{commodity_code}: {row_count:,} rows -> {commodity_code}_jatim.csv")
    print(f"Audit: {audit_path}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean raw Siskaperbapo prices with Kabupaten/Kota medians.")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--kabupaten-csv", type=Path, default=DEFAULT_KABUPATEN_CSV)
    parser.add_argument("--audit-path", type=Path, default=DEFAULT_AUDIT_PATH)
    args = parser.parse_args()
    clean_siskaperbapo(args.raw_dir, args.output_dir, args.kabupaten_csv, args.audit_path)


if __name__ == "__main__":
    main()
