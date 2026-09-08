"""Siskaperbapo Jatim market-price scraper.

The public website serves a seven-day HTML table for one commodity at a time.
Raw market-level observations are intentionally kept separate from the existing
PIHPS price-history files: every commodity is written to
``sample_data/raw_data/siskaperbapo_<id>_<name>_raw.csv``.  Run
``python sample_data/cleaning_siskaperbapo.py`` afterwards to produce the
median Kabupaten/Kota price history consumed by AgriFlow.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://siskaperbapo.jatimprov.go.id/harga-komoditas"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW_DIR = ROOT / "sample_data" / "raw_data"
DELAY_SECONDS = 1.5
MAX_RETRIES = 3
TIMEOUT_SECONDS = 20
RAW_FIELDS = ["tanggal", "kab_kota", "pasar", "komoditas_id", "komoditas_nama", "harga"]
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


def _slug(value: str) -> str:
    base = value.split("/", maxsplit=1)[0].strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", base).strip("_") or "komoditas"


def raw_csv_path(raw_dir: Path, commodity_id: str, commodity_name: str) -> Path:
    return raw_dir / f"siskaperbapo_{commodity_id}_{_slug(commodity_name)}_raw.csv"


def progress_path(raw_csv: Path) -> Path:
    return raw_csv.with_suffix(raw_csv.suffix + ".progress.json")


class SiskaperbapoClient:
    """Stateful HTTP client that maintains the site session and CSRF token."""

    def __init__(self, timeout: int = TIMEOUT_SECONDS) -> None:
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.timeout = timeout
        self._csrf_token: Optional[str] = None
        self._soup_cache: Optional[BeautifulSoup] = None

    def _refresh_csrf(self) -> str:
        response = self.session.get(BASE_URL, timeout=self.timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        token_input = soup.find("input", {"name": "csrf_token"})
        token_meta = soup.find("meta", {"name": "csrf-token"})
        token = (
            token_input.get("value") if token_input else None
        ) or (
            token_meta.get("content") if token_meta else None
        )
        if not token:
            raise RuntimeError("csrf_token tidak ditemukan; struktur situs mungkin berubah.")
        self._csrf_token = token
        self._soup_cache = soup
        return token

    def get_commodities(self) -> list[dict[str, str]]:
        if self._soup_cache is None:
            self._refresh_csrf()
        assert self._soup_cache is not None
        select = self._soup_cache.find("select", {"name": "komoditas"})
        if not select:
            raise RuntimeError("Dropdown komoditas tidak ditemukan; cek struktur situs.")
        return [
            {"id": option.get("value", "").strip(), "nama": option.get_text(strip=True)}
            for option in select.find_all("option")
            if option.get("value", "").strip()
        ]


    def fetch_week(self, commodity_id: str, end_date: date) -> str:
        """Fetch the site's seven-day price table ending on ``end_date``."""
        last_error: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if not self._csrf_token:
                    self._refresh_csrf()
                response = self.session.post(
                    BASE_URL,
                    data={
                        "csrf_token": self._csrf_token,
                        "tanggal_akhir": end_date.isoformat(),
                        "komoditas": commodity_id,
                    },
                    timeout=self.timeout,
                )
                if response.status_code in {403, 419}:
                    self._csrf_token = None
                    response.raise_for_status()
                response.raise_for_status()
                if "Perbandingan harga komoditas" not in response.text:
                    self._csrf_token = None
                    raise RuntimeError("Respons tidak berisi tabel harga Siskaperbapo.")
                return response.text
            except Exception as exc:  # requests + HTML changes need the same retry path
                last_error = exc
                print(f"  retry {attempt}/{MAX_RETRIES}: {exc}", file=sys.stderr)
                time.sleep(2 * attempt)
        raise RuntimeError(
            f"Gagal mengambil komoditas={commodity_id}, tanggal_akhir={end_date}: {last_error}"
        )


def parse_table(html: str, commodity_id: str, commodity_name: str) -> list[dict[str, str]]:
    """Parse one Siskaperbapo seven-day table into market-level raw records."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return []
    rows = table.find_all("tr")
    if not rows:
        return []
    header = [cell.get_text(strip=True) for cell in rows[0].find_all(["th", "td"])]
    dates = header[2:]
    if not dates:
        return []

    records: list[dict[str, str]] = []
    current_area: Optional[str] = None
    for html_row in rows[1:]:
        cells = [cell.get_text(strip=True) for cell in html_row.find_all(["th", "td"])]
        if len(cells) < 2:
            continue
        number, location = cells[0], cells[1]
        if number == "#":
            continue
        if re.fullmatch(r"\d+", number):
            current_area = location
            continue
        if current_area is None or not re.fullmatch(r"\d+\.\d+", number):
            continue
        for observation_date, raw_price in zip(dates, cells[2:]):
            price = raw_price.replace(".", "").replace(",", "").strip()
            if not price or price == "-":
                continue
            try:
                int(price)
                date.fromisoformat(observation_date)
            except ValueError:
                continue
            records.append({
                "tanggal": observation_date,
                "kab_kota": current_area,
                "pasar": location,
                "komoditas_id": commodity_id,
                "komoditas_nama": commodity_name,
                "harga": price,
            })
    return records


def _load_progress(raw_csv: Path) -> set[str]:
    path = progress_path(raw_csv)
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as handle:
        return set(json.load(handle))


def _save_progress(raw_csv: Path, completed: set[str]) -> None:
    with progress_path(raw_csv).open("w", encoding="utf-8") as handle:
        json.dump(sorted(completed), handle, ensure_ascii=False)


def _existing_keys(raw_csv: Path) -> set[tuple[str, str, str, str]]:
    if not raw_csv.exists():
        return set()
    with raw_csv.open(newline="", encoding="utf-8") as handle:
        return {
            (row["tanggal"], row["kab_kota"], row["pasar"], row["komoditas_id"])
            for row in csv.DictReader(handle)
        }


def _checkpoints(start: date, end: date) -> list[date]:
    points: list[date] = []
    cursor = end
    while cursor >= start:
        points.append(cursor)
        cursor -= timedelta(days=7)
    if points[-1] != start:
        points.append(start)
    return points


def save_commodity_list(client: SiskaperbapoClient, raw_dir: Path) -> list[dict[str, str]]:
    """Refresh the source commodity catalogue beside the raw observations."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    commodities = client.get_commodities()
    path = raw_dir / "siskaperbapo_komoditas.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "nama"])
        writer.writeheader()
        writer.writerows(commodities)
    return commodities


def _scrape_commodity(
    client: SiskaperbapoClient,
    commodity_id: str,
    commodity_name: str,
    start: date,
    end: date,
    raw_dir: Path,
    resume: bool,
) -> tuple[int, int]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_csv = raw_csv_path(raw_dir, commodity_id, commodity_name)
    completed = _load_progress(raw_csv) if resume else set()
    known_rows = _existing_keys(raw_csv)
    wrote = skipped = 0

    with raw_csv.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RAW_FIELDS)
        if raw_csv.stat().st_size == 0:
            writer.writeheader()
        for checkpoint in _checkpoints(start, end):
            progress_key = f"{commodity_id}|{checkpoint.isoformat()}"
            if progress_key in completed:
                skipped += 1
                continue
            print(f"{commodity_name} ({commodity_id}) — hingga {checkpoint.isoformat()}")
            html = client.fetch_week(commodity_id, checkpoint)
            records = [
                row for row in parse_table(html, commodity_id, commodity_name)
                if start.isoformat() <= row["tanggal"] <= end.isoformat()
            ]
            if not records:
                raise RuntimeError(
                    f"Tidak ada record valid untuk {commodity_id} hingga {checkpoint}; "
                    "checkpoint tidak ditandai selesai."
                )
            for row in records:
                record_key = (row["tanggal"], row["kab_kota"], row["pasar"], row["komoditas_id"])
                if record_key not in known_rows:
                    writer.writerow(row)
                    known_rows.add(record_key)
                    wrote += 1
            handle.flush()
            completed.add(progress_key)
            _save_progress(raw_csv, completed)
            time.sleep(DELAY_SECONDS)
    return wrote, skipped


def scrape_range(
    commodity_ids: list[str],
    commodity_map: dict[str, str],
    start: date,
    end: date,
    raw_dir: Path = DEFAULT_RAW_DIR,
    resume: bool = True,
) -> dict[str, int]:
    """Scrape a historical range into one resumable raw CSV per commodity.

    ``resume=False`` re-fetches checkpoints but keeps the immutable raw rows and
    suppresses exact duplicate observations; it never deletes existing evidence.
    """
    if start > end:
        raise ValueError("start harus sebelum atau sama dengan end")
    client = SiskaperbapoClient()
    summary: dict[str, int] = {}
    for commodity_id in commodity_ids:
        commodity_name = commodity_map.get(commodity_id, commodity_id)
        wrote, skipped = _scrape_commodity(
            client, commodity_id, commodity_name, start, end, raw_dir, resume
        )
        summary[commodity_id] = wrote
        print(f"  -> {wrote:,} row baru; {skipped:,} checkpoint dilanjutkan dari progress.")
    return summary


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%d/%m/%Y").date()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape harga pasar Siskaperbapo ke sample_data/raw_data per komoditas.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh:
  python data_sources/siskaperbapo.py --list-komoditas
  python data_sources/siskaperbapo.py --komoditas 16,39 --start 01/01/2020 --end 31/12/2025
  python data_sources/siskaperbapo.py --komoditas 16 --today

Lalu normalisasi dengan:
  python sample_data/cleaning_siskaperbapo.py
""",
    )
    parser.add_argument("--start", help="Tanggal awal dd/mm/yyyy")
    parser.add_argument("--end", help="Tanggal akhir dd/mm/yyyy")
    parser.add_argument("--today", action="store_true", help="Ambil harga hari ini")
    parser.add_argument("--komoditas", default="all", help="ID dipisah koma, atau 'all'")
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--list-komoditas", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    client = SiskaperbapoClient()
    commodities = save_commodity_list(client, args.raw_dir)
    commodity_map = {item["id"]: item["nama"] for item in commodities}
    if args.list_komoditas:
        print(f"{len(commodities)} komoditas disimpan di {args.raw_dir / 'siskaperbapo_komoditas.csv'}")
        return
    if args.komoditas == "all":
        commodity_ids = list(commodity_map)
    else:
        commodity_ids = [item.strip() for item in args.komoditas.split(",") if item.strip()]
        unknown = sorted(set(commodity_ids) - set(commodity_map))
        if unknown:
            parser.error(f"ID komoditas tidak tersedia di situs: {', '.join(unknown)}")
    if args.today:
        start = end = date.today()
    elif args.start and args.end:
        start, end = _parse_date(args.start), _parse_date(args.end)
    else:
        parser.error("Isi --start dan --end, atau gunakan --today.")
    scrape_range(commodity_ids, commodity_map, start, end, args.raw_dir, not args.no_resume)


if __name__ == "__main__":
    main()
