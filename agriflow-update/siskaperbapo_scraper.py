"""
Scraper Siskaperbapo Jatim (https://siskaperbapo.jatimprov.go.id/harga-komoditas)
====================================================================================

CARA KERJA SITUS
-----------------
Situs ini SERVER-RENDERED (bukan JSON API). Alurnya:
  1. GET  /harga-komoditas          -> ambil cookie session + csrf_token (hidden input)
  2. POST /harga-komoditas          -> body: csrf_token, tanggal_akhir (YYYY-MM-DD), komoditas (id)
  3. Response HTML berisi tabel "rolling 7 hari" (tanggal_akhir - 6 hari s/d tanggal_akhir)
     untuk SATU komoditas, semua kab/kota & pasar di Jatim.

Karena satu request = 1 komoditas x 7 hari, untuk historical scraping cukup panggil
per kelipatan 7 hari (hemat request), atau panggil harian kalau butuh cross-check /
handle data yang telat masuk (data hari kemarin kadang direvisi).

STRUKTUR TABEL
--------------
Kolom "No" menandai level:
  - "#"      -> baris agregat Propinsi Jawa Timur (skip, bukan level pasar)
  - "1", "2", ... (integer)      -> header Kab/Kota (nilai biasanya "-", skip)
  - "1.1", "1.2", ... (desimal)  -> baris PASAR (level paling granular, ini yang kita ambil)

OUTPUT
------
CSV long-format: tanggal, kab_kota, pasar, komoditas_id, komoditas_nama, harga

CATATAN PENTING
----------------
- Data situs ini diinput manual harian oleh petugas -> bukan realtime sungguhan.
  Untuk kebutuhan "realtime" di AgriFlow, cukup jalankan scraper ini terjadwal
  (misal cron tiap beberapa jam) dengan tanggal_akhir = hari ini.
- Belum sempat saya test end-to-end (domain situs tidak whitelist di sandbox saya),
  jadi jalankan & debug di sisi kamu. Kalau ada perubahan struktur HTML/nama field,
  edit bagian parse_table() / FORM FIELD NAMES di bawah.
- Sopan ke server: ada delay antar request (DELAY_SECONDS) dan retry sederhana.
"""

import argparse
import csv
import json
import os
import re
import time
import sys
from datetime import date, datetime, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://siskaperbapo.jatimprov.go.id/harga-komoditas"
DELAY_SECONDS = 1.5          # jeda antar request, jangan di-set 0 (etika scraping situs pemerintah)
MAX_RETRIES = 3
TIMEOUT = 20

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}


class SiskaperbapoClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._csrf_token: Optional[str] = None

    def _refresh_csrf(self) -> str:
        """GET halaman utama untuk ambil cookie sesi + csrf_token terbaru.
        Token biasanya 1x pakai / expire per sesi, jadi kita refresh tiap kali
        sebelum POST supaya tidak kena 419/403 karena token basi."""
        resp = self.session.get(BASE_URL, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        token_input = soup.find("input", {"name": "csrf_token"})
        if token_input and token_input.get("value"):
            self._csrf_token = token_input["value"]
        else:
            # fallback: kadang token taruh di <meta name="csrf-token" content="...">
            meta = soup.find("meta", {"name": "csrf-token"})
            if meta and meta.get("content"):
                self._csrf_token = meta["content"]
            else:
                raise RuntimeError(
                    "csrf_token tidak ditemukan di halaman. "
                    "Struktur HTML situs mungkin berubah - cek manual via DevTools."
                )
        self._soup_cache = soup
        return self._csrf_token

    def get_komoditas_list(self) -> list[dict]:
        """Ambil daftar {id, nama} komoditas dari <select name="komoditas">
        di halaman utama. Panggil setelah _refresh_csrf() supaya self._soup_cache terisi."""
        if not hasattr(self, "_soup_cache"):
            self._refresh_csrf()
        select = self._soup_cache.find("select", {"name": "komoditas"})
        if not select:
            raise RuntimeError("Dropdown komoditas tidak ditemukan - cek struktur HTML.")
        items = []
        for opt in select.find_all("option"):
            val = opt.get("value", "").strip()
            if not val:
                continue
            items.append({"id": val, "nama": opt.get_text(strip=True)})
        return items


    def fetch_week(self, komoditas_id: str, tanggal_akhir: date) -> str:
        """POST untuk ambil tabel 7-hari (s/d tanggal_akhir) untuk 1 komoditas.
        Return: raw HTML response."""
        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if not self._csrf_token:
                    self._refresh_csrf()
                payload = {
                    "csrf_token": self._csrf_token,
                    "tanggal_akhir": tanggal_akhir.strftime("%Y-%m-%d"),
                    "komoditas": komoditas_id,
                }
                resp = self.session.post(BASE_URL, data=payload, headers=HEADERS, timeout=TIMEOUT)
                resp.raise_for_status()

                # Kalau token basi, situs biasanya balikin halaman form kosong / status 419/403.
                # Deteksi kasar: kalau tidak ada tabel "Perbandingan harga komoditas", refresh & retry.
                if "Perbandingan harga komoditas" not in resp.text:
                    self._csrf_token = None  # paksa refresh token di percobaan berikutnya
                    raise RuntimeError("Response tidak berisi tabel harga (kemungkinan token expired).")

                return resp.text
            except Exception as e:  # noqa: BLE001
                last_err = e
                print(f"  [retry {attempt}/{MAX_RETRIES}] {e}", file=sys.stderr)
                time.sleep(2 * attempt)
        raise RuntimeError(f"Gagal fetch komoditas={komoditas_id} tanggal_akhir={tanggal_akhir}: {last_err}")


def save_komoditas_list(client: "SiskaperbapoClient", out_path: str = "komoditas_list.csv") -> list[dict]:
    """Ambil & simpan daftar SEMUA komoditas_id yang ada di dropdown situs ke CSV.
    Panggil ini dulu sebelum scraping massal, supaya tahu id mana yang mau dipakai
    (atau langsung pakai semua dengan --komoditas all)."""
    items = client.get_komoditas_list()
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "nama"])
        writer.writeheader()
        writer.writerows(items)
    print(f"Ditemukan {len(items)} komoditas -> disimpan ke {out_path}")
    for it in items:
        print(f"  {it['id']:>4}  {it['nama']}")
    return items


def parse_table(html: str, komoditas_id: str, komoditas_nama: str) -> list[dict]:
    """Parse tabel harga dari HTML response menjadi list of dict (long format)."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        return []

    rows = table.find_all("tr")
    if not rows:
        return []

    # Header: No | Lokasi | tanggal1 | tanggal2 | ... | tanggal7
    header_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
    date_columns = header_cells[2:]  # kolom setelah "No" dan "Lokasi"

    records = []
    current_kabkota = None

    for tr in rows[1:]:
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 2:
            continue

        no, lokasi = cells[0], cells[1]
        harga_cells = cells[2:]

        if no == "#":
            # baris agregat provinsi - skip, bukan level pasar
            continue

        if re.fullmatch(r"\d+", no):
            # header kab/kota, misal "1", "2" -> set konteks, tidak disimpan sebagai record
            current_kabkota = lokasi
            continue

        if re.fullmatch(r"\d+\.\d+", no):
            # baris pasar level granular
            for tanggal_str, harga_str in zip(date_columns, harga_cells):
                harga_clean = harga_str.replace(".", "").replace(",", "").strip()
                if not harga_clean or harga_clean == "-":
                    continue
                try:
                    harga_val = int(harga_clean)
                except ValueError:
                    continue
                records.append({
                    "tanggal": tanggal_str,
                    "kab_kota": current_kabkota,
                    "pasar": lokasi,
                    "komoditas_id": komoditas_id,
                    "komoditas_nama": komoditas_nama,
                    "harga": harga_val,
                })

    return records


def _progress_path(out_csv: str) -> str:
    return out_csv + ".progress.json"


def _load_progress(out_csv: str) -> set:
    """Progress disimpan sebagai set string 'komoditas_id|tanggal_akhir_iso' yang SUDAH
    berhasil di-fetch & ditulis ke CSV. Dipakai untuk resume kalau proses terhenti di tengah."""
    path = _progress_path(out_csv)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def _save_progress(out_csv: str, done: set):
    with open(_progress_path(out_csv), "w", encoding="utf-8") as f:
        json.dump(sorted(done), f)


def scrape_range(komoditas_ids: list[str], komoditas_map: dict, start: date, end: date,
                  out_csv: str = "siskaperbapo_harga.csv", resume: bool = True):
    """Scrape rentang tanggal untuk daftar komoditas, step 7 hari (karena 1 request = 7 hari).

    - Menulis ke CSV secara INCREMENTAL (append per checkpoint yang selesai), bukan nunggu
      semuanya kelar di akhir -> aman untuk range panjang (misal 5 tahun / ribuan request).
    - RESUMABLE: kalau proses berhenti (error, listrik mati, dst), jalankan ulang perintah
      yang sama -> checkpoint yang sudah selesai otomatis dilewati (dibaca dari file
      '<out_csv>.progress.json'). Set resume=False untuk mulai dari nol.
    - Dedup ditangani lewat progress-tracking per (komoditas_id, tanggal_akhir checkpoint),
      bukan per baris, supaya tetap ringan untuk data besar.
    """
    client = SiskaperbapoClient()

    # titik-titik tanggal_akhir yang perlu dipanggil supaya seluruh range ter-cover
    checkpoints = []
    cursor = end
    while cursor >= start:
        checkpoints.append(cursor)
        cursor -= timedelta(days=7)
    if checkpoints[-1] != start:
        checkpoints.append(start)  # pastikan ujung awal range ikut ter-cover

    done = _load_progress(out_csv) if resume else set()
    file_exists = os.path.exists(out_csv) and os.path.getsize(out_csv) > 0
    fieldnames = ["tanggal", "kab_kota", "pasar", "komoditas_id", "komoditas_nama", "harga"]

    total_calls = len(komoditas_ids) * len(checkpoints)
    call_no = 0
    skipped = 0

    with open(out_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        for kid in komoditas_ids:
            kname = komoditas_map.get(kid, kid)
            for tgl_akhir in checkpoints:
                call_no += 1
                progress_key = f"{kid}|{tgl_akhir.isoformat()}"
                if progress_key in done:
                    skipped += 1
                    continue

                print(f"[{call_no}/{total_calls}] komoditas={kname} ({kid}) tanggal_akhir={tgl_akhir}")
                try:
                    html = client.fetch_week(kid, tgl_akhir)
                    recs = parse_table(html, kid, kname)
                    for r in recs:
                        writer.writerow(r)
                    f.flush()
                    done.add(progress_key)
                    _save_progress(out_csv, done)  # simpan progress tiap checkpoint sukses
                except Exception as e:  # noqa: BLE001
                    print(f"  GAGAL total untuk checkpoint ini, lanjut ke berikutnya: {e}", file=sys.stderr)
                time.sleep(DELAY_SECONDS)

    print(f"\nSelesai. {call_no - skipped} checkpoint baru diambil, {skipped} dilewati (sudah ada). "
          f"Data tersimpan (append) di {out_csv}.")
    print("Catatan: karena mode append, mungkin ada baris duplikat lintas jalankan-ulang "
          "kalau resume=False dipakai. Untuk data final bersih, dedup di langkah load-ke-DB "
          "berdasarkan (tanggal, pasar, komoditas_id).")


def scrape_today(komoditas_ids: list[str], komoditas_map: dict, out_csv: str = "siskaperbapo_harian.csv"):
    """Mode 'realtime': ambil data hari ini saja untuk semua komoditas.
    Cocok dijalankan terjadwal (cron) tiap beberapa jam untuk update AgriFlow."""
    today = date.today()
    scrape_range(komoditas_ids, komoditas_map, start=today, end=today, out_csv=out_csv)


def parse_ddmmyyyy(s: str) -> date:
    return datetime.strptime(s, "%d/%m/%Y").date()


def main():
    parser = argparse.ArgumentParser(
        description="Scraper harga komoditas Siskaperbapo Jatim.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Contoh pemakaian:

  # 1) Lihat & simpan semua komoditas_id yang ada di situs
  python siskaperbapo_scraper.py --list-komoditas

  # 2) Scrape 1 komoditas, rentang tanggal tertentu
  python siskaperbapo_scraper.py --start 01/01/2020 --end 08/08/2026 --komoditas 38

  # 3) Scrape SEMUA komoditas, 5 tahun terakhir (bisa berjam-jam, jalan lagi kalau putus - resumable)
  python siskaperbapo_scraper.py --start 08/08/2021 --end 08/08/2026 --komoditas all --out harga_5tahun.csv

  # 4) Mode harian untuk cron/scheduler AgriFlow (hanya hari ini, semua komoditas)
  python siskaperbapo_scraper.py --today --komoditas all --out siskaperbapo_harian.csv
""",
    )
    parser.add_argument("--start", type=str, help="Tanggal mulai, format dd/mm/yyyy")
    parser.add_argument("--end", type=str, help="Tanggal akhir, format dd/mm/yyyy")
    parser.add_argument("--today", action="store_true",
                         help="Scrape hari ini saja (override --start/--end). Untuk mode 'realtime' harian.")
    parser.add_argument("--komoditas", type=str, default="all",
                         help="'all' untuk semua komoditas, atau id dipisah koma, misal '38,12,5'")
    parser.add_argument("--out", type=str, default="siskaperbapo_harga.csv", help="Path file CSV output")
    parser.add_argument("--list-komoditas", action="store_true",
                         help="Cuma tampilkan & simpan daftar komoditas_id ke komoditas_list.csv, lalu keluar")
    parser.add_argument("--no-resume", action="store_true",
                         help="Mulai dari nol, abaikan progress checkpoint sebelumnya")
    args = parser.parse_args()

    client = SiskaperbapoClient()
    komoditas_list = save_komoditas_list(client)  # selalu ambil & simpan daftar terbaru
    komoditas_map = {k["id"]: k["nama"] for k in komoditas_list}

    if args.list_komoditas:
        return  # sudah dicetak & disimpan oleh save_komoditas_list di atas

    if args.komoditas == "all":
        ids = list(komoditas_map.keys())
    else:
        ids = [x.strip() for x in args.komoditas.split(",") if x.strip()]
        unknown = [i for i in ids if i not in komoditas_map]
        if unknown:
            print(f"PERINGATAN: id komoditas tidak dikenali (tetap dicoba): {unknown}", file=sys.stderr)

    if args.today:
        scrape_today(ids, komoditas_map, out_csv=args.out)
        return

    if not args.start or not args.end:
        parser.error("Wajib isi --start dan --end (format dd/mm/yyyy), atau pakai --today, atau --list-komoditas")

    start_date = parse_ddmmyyyy(args.start)
    end_date = parse_ddmmyyyy(args.end)
    if start_date > end_date:
        parser.error("--start harus lebih awal atau sama dengan --end")

    n_checkpoints = (end_date - start_date).days // 7 + 2
    est_calls = len(ids) * n_checkpoints
    est_minutes = est_calls * DELAY_SECONDS / 60
    print(f"Estimasi: {len(ids)} komoditas x ~{n_checkpoints} checkpoint = ~{est_calls} request "
          f"(~{est_minutes:.1f} menit dengan delay {DELAY_SECONDS}s/request)\n")

    scrape_range(ids, komoditas_map, start=start_date, end=end_date,
                 out_csv=args.out, resume=not args.no_resume)


if __name__ == "__main__":
    main()