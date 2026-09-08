Language / Bahasa: [English](./README.en.md) · **Bahasa Indonesia**

<p align="center"><img src="assets/logo-mark.png" alt="AgriFlow logo" width="300"/></p>

<h1 align="center">AgriFlow</h1>

<p align="center">
  <strong>AI-Powered Food Security Intelligence Platform</strong><br/>
  <em>Platform Matching Demand–Supply Pangan Antarwilayah</em>
</p>

<p align="center"><b>Deteksi · Prediksi · Distribusi</b></p>

<p align="center">
  <img src="https://img.shields.io/badge/PIDI-DIGDAYA%20%C3%97%20Hackathon%202026-1B5E20?style=for-the-badge" alt="Hackathon"/>
  <img src="https://img.shields.io/badge/Problem%20Statement-2%20Matching%20Demand–Supply-4CAF50?style=for-the-badge" alt="PS"/>
  <img src="https://img.shields.io/badge/tests-544%20passing-brightgreen?style=for-the-badge" alt="Tests"/>
</p>

> **Roadmap proyek dibagi 3 Phase.** README teknis lengkap versi sebelumnya diarsipkan di [`README_v13.md`](README_v13.md) (snapshot terbaru), [`README_v12.md`](README_v12.md), dan [`README_v11.md`](README_v11.md).

---

<details>
<summary><b>🖼️ Lihat Research Poster (klik untuk expand)</b></summary>

<br/>

<p align="center"><img src="poster/agriflow-poster.jpg" alt="AgriFlow Research Poster" width="100%"/></p>

</details>

---

# 📍 Phase 1 — Tim & Tautan

## Tim

| Nama | Role | LinkedIn |
|------|------|----------|
| Chelsea | Data Analyst | [Chelsea](https://linkedin.com/in/chelseaayu) |
| Hilmi | Data Architect | [Hilmi](https://linkedin.com/in/hilmi888/) |
| Monika | UX Researcher | [Monika](https://linkedin.com/in/monika-hermiani) |
| Irpan | Data Engineer | [Irpan](https://linkedin.com/in/irpanpilihanrambe) |

## Tautan

| Resource | Link |
|----------|------|
| Pitch Deck | [Canva](https://www.canva.com/design/DAHETj2ulzg/VIvgxVkQ6I9R24ucphy2mQ/view) |
| Dashboard (Live Demo) | [agriflow-engine.vercel.app](https://agriflow-engine.vercel.app/) |
| Proposal (v13) | [docs/AgriFlow_Proposal_v13.pdf](docs/AgriFlow_Proposal_v13.pdf) |
| 📋 Bukti Pendukung | [Lima kategori bukti](#-bukti-pendukung) — setelah Phase 3 |
| 💬 Umpan Balik Pengguna | [5 early tester + 4 wawancara petani](#-umpan-balik-pengguna) |

---

# 🚀 Phase 2 — Yang Sudah Kami Bangun (MVP)

## Masalah

Setiap tahun Indonesia kehilangan triliunan rupiah pangan — **40% terjadi di distribusi, bukan produksi**. Di satu kabupaten petani membuang cabai karena harga jatuh; di kabupaten sebelah harga melonjak karena langka. Pemda sering baru tahu krisis **2–3 minggu kemudian**.

## Solusi

**AgriFlow mencocokkan kabupaten surplus dengan kabupaten defisit** — seperti "Uber untuk pangan", tapi paham masa simpan (perishability), jarak jalan nyata, dan **keadilan untuk daerah tertinggal**. Tiga fungsi inti:

- **Deteksi** — temukan anomali harga (lonjakan/anjlok) dari data harga harian.
- **Prediksi** — perkirakan harga 30 hari ke depan.
- **Distribusi** — cocokkan surplus → defisit secara cerdas & adil.

## Arsitektur (High-Level)

```
   SUMBER DATA NYATA                AGRIFLOW ENGINE                  AKSES
  (BPS · PIHPS · OSRM)        ┌──────────────────────────┐
  produksi · konsumsi ──────▶ │ DETEKSI    anomali harga  │ ──┐
  harga · populasi            │ PREDIKSI   forecast 30 hr │   ├──▶ Dashboard peta
  per-kabupaten Jatim         │ DISTRIBUSI matching 4-lapis│  └──▶ WhatsApp bot
                              └──────────────────────────┘
```

Tiga fungsi (Deteksi · Prediksi · Distribusi) berbagi satu sumber data nyata, lalu disajikan lewat Dashboard & WhatsApp.

📄 **Detail metodologi tiap fitur — alasan pemilihan metode, cara kerja, evaluasi, validasi, dan sitasi paper: [Dokumen Arsitektur (PDF)](docs/AgriFlow_Architecture.pdf).**

## Fitur yang sudah berjalan

| Fungsi | Fitur | Status |
|--------|-------|:------:|
| **Distribusi** | Matching engine 4-lapis (hard constraints → multi-objective scoring → equity) berjalan di **data BPS asli per-kabupaten (2022)** | ✅ |
| **Deteksi** | Deteksi anomali harga Hampel/MAD pada residual deseasonalized (sebelumnya berlabel S-H-ESD) pada harga PIHPS harian **2021–2025** | ✅ |
| **Prediksi** | Forecasting harga 30 hari untuk 38 kabupaten/kota x 7 komoditas. Yang **dilayani sejak 2026-09-08** adalah **TimesFM 2.0 zero-shot** (`timesfm_2.0`) dengan pita P10 sampai P90 dari kuantil model (belum dikalibrasi, belum ada backtest pada data ini; angka akurasinya menyusul setelah backtest rolling-origin dijalankan). Baseline seasonal-naive dengan interval split-conformal tetap ada sebagai fallback dan itulah yang **MAPE 10,8%** pada [backtest holdout](docs/evidence/pengujian.md#3-model-evaluation) | ✅ |
| **Aksesibilitas** | **Chatbot WhatsApp** (tanya harga & rekomendasi) + **Dashboard** peta interaktif | ✅ |
| **Keamanan** | Situs bersifat *login-first*: membuka website menampilkan halaman login lebih dulu. Juri cukup klik **"Masuk sebagai Tamu"** untuk meninjau tanpa membuat akun. Akun Supabase (JWT terverifikasi server-side, Row Level Security di 12 tabel, reset password) siap untuk model berlangganan; data sensitif (langganan & pembayaran) tetap dijaga verifikasi JWT di sisi server. | ✅ |
| **Data nyata** | **6 komoditas** real per-kab: beras premium & medium, cabai merah & rawit, bawang merah & putih + harga PIHPS 5 tahun | ✅ |

> **Kualitas:** 544 tes otomatis lulus (552 terkumpul, 8 di-skip) — engine teruji, dapat direproduksi, dan jujur soal keterbatasannya (lihat [Pengujian & Skenario](#pengujian--skenario) dan Phase 3).
>
> 📁 Bukti lengkapnya ada di [**Bukti Pendukung**](#-bukti-pendukung) setelah Phase 3: lima kategori, termasuk [bukti pengujian](docs/evidence/pengujian.md) dan [usability testing dengan 5 pengguna nyata](docs/evidence/usability-early-testing.md).

### Cuplikan

**Dashboard** — peta Jawa Timur dengan bubble surplus/defisit per kabupaten, daftar *top matches*, plus panel **Forecast & Anomali harga** (ketiga fungsi dalam satu layar):

![Dashboard AgriFlow](assets/dashboard.png)

**WhatsApp Bot** — tanya harga, cari pembeli/pemasok, prediksi & anomali harga lewat chat. Mendukung **Bahasa Indonesia** dan **Bahasa Jawa** (inklusi petani daerah):

| Bahasa Indonesia | Bahasa Jawa |
|:---:|:---:|
| ![WhatsApp Bahasa Indonesia](assets/whatsapp-id.png) | ![WhatsApp Bahasa Jawa](assets/whatsapp-jawa.png) |

## Pengujian & Skenario

Karena output AgriFlow menggerakkan alokasi pangan antar-kabupaten yang menyentuh daerah IPM-rendah, klaim "adil" dan "robust" harus dapat diaudit ulang — bukan sekadar narasi. Suite uji mengunci angka food-balance sebagai *golden numbers* (reproducibility), menjaga parameter kebijakan dari pergeseran tak sengaja (regression-safety), dan menguji deteksi anomali secara adversarial.

**552 tes terkumpul · 544 lulus · 8 di-skip · lintas-OS di CI.** ([keluaran mentah](docs/evidence/runs/pytest.txt))
(Skip = `test_timesfm_importorskip`: dilewati jika pustaka TimesFM tak terpasang di runner; jalur forecasting tetap diuji via fallback + kontrak API.)

Server produksi memuat **data BPS asli secara default** (`DATA_BACKEND=csv`, bawaan). Fixture sintetis 19-komoditas lama tetap dipakai di 13 file test (`DATA_BACKEND=demo`) untuk menguji logika engine di lebih banyak variasi komoditas — tidak pernah disajikan ke pengguna.

| Kategori | Jumlah | Cakupan |
|---|---|---|
| Unit per-layer (L0–L3) | 73 | Tier IPM, constraint jarak/perishability, skor, alokasi equity |
| 25 skenario edge-case (A–F) | 64 | Volume, spasial, temporal, disrupsi, politis, kualitas |
| Validasi data nyata BPS/PIHPS | 57 | Food-balance beras + hortikultura 2022, pipeline reproducible |
| Deteksi anomali harga | 49 | Hampel/MAD sadar-musiman pada residual deseasonalized (sebelumnya berlabel S-H-ESD) |
| Forecast & API | 40 | Endpoint forecast/anomali + fallback |
| Baseline & equity | 39 | greedy/uniform/proporsional vs AgriFlow + skenario langka pasokan |
| Ingest & integrasi | 73 | DB loader, ingest PIHPS, jarak OSRM, bot WhatsApp |
| Autentikasi dashboard & kuota WhatsApp | 117 | Login Supabase, verifikasi JWT server-side, RLS 12 tabel, reset password, kuota gratis WhatsApp (nonaktif default) |

**25 skenario edge-case** memetakan kejadian nyata Jawa Timur, contohnya: Ramadan spike (C1), erupsi Semeru di Lumajang → unreachable (D4), banjir multi-kabupaten sentra padi (D5), kenaikan BBM → biaya logistik naik (E5), dan prioritas reserve kontrak Bulog (E3).

**Hasil kunci:**
- **Equity terbukti saat pasokan langka, biaya efisiensi nol.** *Ini uji-tekan hipotetis, bukan hasil data BPS asli:* Jawa Timur pada data 2022 justru sangat surplus (rasio 6,6×), sehingga nilai equity tidak akan tampak. Untuk menunjukkan cara kerja mekanismenya kami membangun skenario langka buatan (fixture `surplus_deficit_constrained.csv`, surplus 3962t vs defisit 5249t). Di skenario itu greedy murni menelantarkan Madura — Sampang **0%**, Bangkalan **20%**; AgriFlow mengangkat keduanya ke **100%** dengan *coverage agregat identik* (0.6649) dan Gini turun (0.3017 → 0.2905). Kami tidak mengklaim keunggulan equity saat pasokan melimpah, dan tidak mengklaim skenario ini berasal dari data nyata.
- **Anomali sadar-musiman.** Penurunan harga ~60% ter-flag, tapi pola musiman murni (siklus jelang Lebaran) **tidak** memicu false positive; anomali genuine di atas pola musiman tetap terdeteksi.
- **Data mengungkap defisit struktural, bukan bug.** Bawang putih menghasilkan **0 match** di seluruh 38 kabupaten pada data BPS 2022 — Jawa Timur defisit bawang putih di semua kabupaten, konsisten dengan Indonesia sebagai net-importir bawang putih. Engine bekerja benar; datanya yang bicara.

📄 Detail lengkap (kenapa, daftar 25 skenario, sitasi paper): [Dokumen Arsitektur](docs/AgriFlow_Architecture.pdf) §Pengujian & Validasi.

## Kenapa tech stack kami RINGKAS (bukan sebanyak proposal awal)?

Proposal awal mencantumkan stack besar (Qdrant, LangChain, Redis, n8n, multi-cloud, dll). Setelah benar-benar membangun, kami **sengaja memangkasnya** — *honest engineering* untuk skala saat ini (38 kabupaten Jawa Timur):

| Rencana awal | Yang kami pakai | Alasan |
|---|---|---|
| Qdrant (vector DB terpisah) | **Supabase pgvector** | Korpus kecil — tak perlu service vektor sendiri |
| LangChain | **Gemini API langsung** | RAG sesederhana ini tak butuh framework berat |
| Redis cache | **In-process cache** | Beban belum menuntut; engine deterministik |
| 5 platform hosting | **2 (HF Spaces + Vercel)** | Lebih sedikit titik gagal, lebih murah |

**Prinsip kami: pakai yang cukup, bukan yang ramai.** Komponen besar baru bernilai saat skala membenarkannya — dan itulah **Phase 3**.

## 🎙️ Validasi Lapangan — Wawancara Petani

Kami mewawancarai **4 petani lintas komoditas & skala usaha** — dari petani mapan dengan jaringan pasar sampai petani kecil yang terkurung tengkulak — untuk memvalidasi kebutuhan nyata dan menemukan gap AgriFlow. Tiap baris menyertakan **rekaman audio sebagai bukti**.

| Komoditas | Profil Narasumber | Pendapat Singkat | Rekaman & Transkrip |
|---|---|---|---|
| **Bawang Merah** | Denisa Septalian — petani penerus, Nganjuk (Ds. Ngudikan, Kec. Wilangan), 5 thn, lahan ±70 ru | **Setuju bersyarat.** Info harga saja "kurang efektif" karena 100% bergantung tengkulak & tak punya akses luar daerah — antusias bila AgriFlow membuka **akses pembeli luar kota**. | [🎧 Audio](https://drive.google.com/drive/folders/1kdF9KPqycrdN9GewRz6YKFUKWfzCaRVh) · [📄 Transkrip](interview/transcript-bawang-merah.md) |
| **Padi** | Petani 15 thn, lahan ±1 ha; jual gabah ~Rp5.800/kg ke tengkulak yang datang ke sawah | Info harga lintas daerah **membantu** sebagai gambaran; tertarik pembeli luar kota asal prosesnya aman; ragu "ribet" di awal & soal keamanan transaksi. | [🎧 Audio](https://drive.google.com/drive/folders/1-fpMk8UGg41wk1-RZufTyRBNNJwM7he7) · [📄 Transkrip](interview/transcript-padi.md) |
| **Cabai** | Petani baru (8 bln bertani, tanaman 50 HST), Solo/Karanganyar; sebelumnya jagung | **Sangat tertarik** harga real-time antar daerah untuk hitung kelayakan kirim; info FB/WA kini meleset Rp5.000–15.000/kg & hanya level provinsi. Menekankan UI sederhana untuk petani lansia. | [🎧 Audio](https://drive.google.com/drive/folders/1lStLTY4L_9NW-UXAWrfTXwNc0CuiUQT-) · [📄 Transkrip](interview/transcript-cabai.md) |
| **Kentang** | Labib — Dieng, Banjarnegara, ±6 ha, 2 thn; jual ke Pasar Induk Kramat Jati | Info antar daerah berguna sebagai **pembanding & referensi keputusan**, tetap utamakan pedagang langganan. Kunci keberhasilan: **akurasi data + sumber jelas + update real-time**. | [🎧 Audio](https://drive.google.com/drive/folders/1mMVWLv6uQQzlD_KNrkI5eSARXHTlDK9K) · [📄 Transkrip](interview/transcript-kentang.md) |

### Analisis & Kesimpulan — Nilai Plus AgriFlow yang Tervalidasi

- **Masalah inti tervalidasi lintas komoditas.** Keempat petani menyebut keluhan yang sama: harga tidak stabil, panen raya serentak → harga anjlok, dan **butaan informasi harga antar daerah** — persis yang dijawab fungsi **Deteksi + Prediksi**.
- **WhatsApp sebagai kanal — tervalidasi 4/4.** Semua memilih WhatsApp (bisa dibaca ulang, sudah dipakai semua petani) di atas SMS/aplikasi baru → memperkuat keputusan **WhatsApp bot**.
- **Matching surplus→defisit menjawab keluhan paling tajam.** "Tidak ada akses keluar daerah" (bawang merah, padi) adalah problem yang langsung diselesaikan **matching engine 4-lapis**; begitu ditawari pembeli luar kota berharga lebih baik, **keempatnya tertarik**.
- **Prediksi harga punya nilai konkret.** Semua pernah "kesusu" / salah memperkirakan harga (bawang merah sempat jual Rp10.000, dua hari kemudian Rp20.000) → **forecast 30 hari** menjawab kebutuhan ini.
- **Kesediaan membayar ada** — bersyarat manfaat ekonomi terbukti & data akurat. Tak satu pun menolak model berbayar.

> Temuan **gap fitur** dari wawancara (akses transaksi, granularitas harga, transparansi & keamanan) kami petakan secara jujur ke **Phase 3** di bawah.

---

# 🌐 Phase 3 — Rencana Lanjutan & Scaling

Phase 3 memuat dua hal yang kami pisahkan secara jujur: fitur yang sengaja ditunda karena belum dibutuhkan pada skala sekarang, dan batas yang sudah kami ukur pada engine yang berjalan lalu kami jadwalkan perbaikannya.

## Yang ditunda (menunggu data atau beban nyata)

| Rencana | Untuk apa | Pemicu |
|---|---|---|
| Skala nasional 514 kab | Dari 38 kab Jatim ke seluruh Indonesia | spatial partitioning + precompute jarak |
| Exogenous forecasting (indeks ENSO, kalender Ramadan) | Akurasi naik saat guncangan iklim & hari raya | data eksogen tersedia |
| Daging ayam & telur (data real) | Melengkapi 6 komoditas inti | produksi broiler & telur-ras per-kab dirilis |
| Harga granular per kota/pasar | Selisih riil bisa Rp5.000 sampai 15.000/kg (wawancara cabai) | feed harga pasar terbuka |
| Fasilitasi transaksi antar-daerah | Info harga saja "kurang efektif" tanpa saluran jual-beli (wawancara bawang & padi) | kemitraan penyaluran |
| Transparansi sumber & keamanan transaksi | Syarat kepercayaan pengguna (wawancara) | tahap kemitraan resmi |
| Sahabat-AI (Jawa/Madura) + IVR telepon | Inklusi petani lansia & feature-phone | tahap penskalaan kanal |
| Qdrant / Redis / n8n | Vector scale, caching, orkestrasi | saat beban nyata muncul |

## Batas cakupan hari ini (gerbangnya ketersediaan data, bukan arsitektur)

Engine sudah siap memproses data apa pun; yang membatasi adalah ketersediaan data publik per-kabupaten. Begitu sumbernya terbuka, pipeline yang sama langsung memprosesnya tanpa ubah arsitektur.

| Cakupan sekarang | Gerbangnya |
|---|---|
| 6 komoditas inti | menunggu produksi per-kab komoditas lain dirilis BPS |
| Tahun acuan 2022 | tahun terlengkap di semua sumber per-kab; tahun baru tinggal di-ingest |
| Daging ayam & telur belum | 13 komoditas lain masih placeholder sintetis, tidak disajikan ke pengguna (`DATA_BACKEND=csv`) |
| Konsumsi cabai/bawang via angka nasional | konsumsi beras sudah per-kab & dipakai nyata; sisanya menunggu publikasi |
| Harga Tier-2 (kab non-IHK) | Panel Harga Bapanas dalam pemeliharaan; saat feed pulih, 30+ kab langsung tercakup |

## Utang teknis yang sudah kami ukur (perbaikan terjadwal)

Dua batas ini kami ukur sendiri terhadap performa maksimal engine, dengan benchmark yang di-commit dan dapat direproduksi juri.

1. ~~Allocator belum optimal.~~ **Ditutup di v1.1.** Diuji terhadap optimum LP transportation eksak pada data BPS asli: tier stable meninggalkan 25,4% welfare berbobot-ekuitas, tier greedy 11,1%. Bukti nyata: permintaan cabai_merah Sumenep terisi 26% padahal pasokan terjangkau (2.662 ton, radius 200 km) melebihi kebutuhan (1.418 ton), greedy mengalokasikannya lebih dulu ke tempat lain. Jadi ini soal optimalitas, bukan kelangkaan. `ALLOCATOR=lp` sekarang jadi default di API, memakai LP transportation berkapasitas (scipy HiGHS) dengan equity di dalam objective, welfare terukur +3,9% vs greedy pada data BPS asli; greedy tetap tersedia sebagai fallback. Lihat [Backend v1.1](#backend-v11-agustus-2026) dan `benchmarks/output/lp_allocator.json`. Akar lama: `matching_engine/allocation.py:307`.
2. ~~Satukan detektor anomali.~~ **Ditutup di v1.1.** Panel anomali pengguna sudah pakai S-H-ESD robust (`analysis/price_anomaly.py`). Namun gerbang pre-filter D3 internal (`matching_engine/engine.py:62`) masih z-score 3σ non-robust, pada 70.953 observasi PIHPS asli hanya me-recall 14,4% anomali tervalidasi, dan flag D3 mengeluarkan node dari matching sepenuhnya. Sekarang gerbang D3 memakai output scanner Hampel/MAD yang sama dengan panel pengguna (`analysis/anomaly_gate.py`); label API `hampel_mad_v2`, bukan S-H-ESD. Lihat [Backend v1.1](#backend-v11-agustus-2026).

## Scaling up

Peningkatan skala nasional dibatasi laju keterbukaan data publik per-kabupaten, bukan kesiapan teknis. Pendekatan kami: buktikan nilai dulu di skala provinsi dengan data nyata, lalu perluas seiring data tersedia.

---

## Menjalankan (teknis singkat)

```bash
pip install -r requirements.txt
python examples/run_demo_real.py   # demo matching pada data BPS asli 2022
pytest tests/                      # 544 lulus, 8 di-skip
```

Semua angka pengujian yang dikutip di halaman ini dapat dijalankan ulang lewat perintah
yang tercantum di [Bukti Pengujian](docs/evidence/README.md).

Detail engineering lengkap ada di [`README_v12.md`](README_v12.md).

### Backend v1.1 (Agustus 2026)

Perubahan sisi server yang menutup utang teknis Phase 3 butir 1 dan 2 serta temuan audit F1, F3, F7. Semua terverifikasi 544 tes lulus (552 terkumpul, 8 di-skip).

| Perubahan | Di mana | Bukti |
|---|---|---|
| Allocator L3 optimal: LP transportasi berkapasitas (scipy HiGHS), equity di dalam objective; greedy tetap fallback | `matching_engine/allocation.py::lp_optimal_allocate`, `ALLOCATOR=lp` default di API | `python benchmarks/lp_allocator.py` (welfare vs greedy dicatat di `run_metadata.welfare_gain_pct`) |
| Satu detektor anomali: gerbang D3 memakai output scanner Hampel/MAD yang sama dengan panel; label API `hampel_mad_v2` (bukan S-H-ESD) | `analysis/anomaly_gate.py`, `run_matching(anomaly_keys=...)` | `run_metadata.anomaly_gate == "batch_hampel_mad"` |
| Interval prakiraan terkalibrasi pada baseline seasonal-naive (fallback): split-conformal rolling-origin, coverage 80% terukur (sebelumnya 42%) pada MAPE 10,8% yang sama; artefak TimesFM yang dilayani masih memakai kuantil model tanpa kalibrasi | `analysis/forecast_timesfm.py`, field `interval_method` | `python analysis/backtest_baseline.py` |
| Bug kalender (audit F1): Ramadan eksplisit menang atas SCHOOL_START; kebijakan impor dikomposisikan di atas profil event | `matching_engine/engine.py`, `scoring.apply_import_policy` | `tests/test_backend_v11.py::TestCalendarPriority` |
| Endpoint baru: `/api/v1/meta` (data per), `/api/v1/summary` (KPI dihitung), `/api/v1/report.csv`, `/api/v1/matches/explain`, `POST /api/v1/simulate` (preset: semeru, banjir_sentra_padi, banjir_madura, ramadan, bbm_20, impor, suramadu_tutup) | `whatsapp_bot/server.py` | `tests/test_backend_v11.py::TestApiV11` |
| Kartu match membawa `breakdown` 5 dimensi, `base_score`, `equity_multiplier`, `why` | `_serialize_match` | `GET /api/v1/matches` |
| Parameter `city` menerima nama kota (audit F7) | `_resolve_city` | `GET /api/v1/forecast?commodity=cabai_rawit&city=Kota%20Surabaya` |
| Refresh harian artefak (anomali, forecast, backtest) lewat GitHub Actions | `.github/workflows/refresh-data.yml` | commit otomatis `data: daily refresh ...` |

---

# 📋 Bukti Pendukung

Seluruh bukti pendukung AgriFlow disusun mengikuti lima kategori panduan submission. Ringkasan
lengkapnya ada di halaman ini, dan setiap kategori punya halaman rinci di
[`docs/evidence/`](docs/evidence/README.md).

Aturan yang kami pegang: **kalau sesuatu belum dijalankan, statusnya ditulis belum dijalankan.**
Tidak ada hasil yang dikarang untuk mengisi tabel, dan temuan yang tidak menguntungkan kami
tetap dicantumkan. Setiap angka disertai perintah untuk direproduksi.

## Peta lima kategori

| # | Kategori | Status | Halaman rinci |
|---|---|---|---|
| 1 | **Produk digital** | ✅ 9 dari 9 item | [produk-digital.md](docs/evidence/produk-digital.md) |
| 2 | **Pengujian** | ✅ 10 dari 11 item | [pengujian.md](docs/evidence/pengujian.md) |
| 3 | **Pengguna** | ✅ 7 dari 8 item | [pengguna.md](docs/evidence/pengguna.md) |
| 4 | **Implementasi awal non-digital** | ⚠️ 1 dari 9 item, 2 sebagian | [implementasi-non-digital.md](docs/evidence/implementasi-non-digital.md) |
| 5 | **Kesiapan pihak luar** | ✅ 4 dari 7 item | [kesiapan-pihak-luar.md](docs/evidence/kesiapan-pihak-luar.md) |

## Yang paling cepat meyakinkan

| Ingin melihat | Buka |
|---|---|
| Produknya benar-benar jalan | [Respons API produksi live](docs/evidence/runs/api-live-responses.md) — 6 endpoint, diambil 22 Juli 2026 |
| Enginenya benar-benar menghitung | [Demo data BPS asli 2022](docs/evidence/runs/demo_real_bps.txt) — 84 match, 467 ribu ton |
| Pengguna nyata sudah mencobanya | [5 sesi early tester](docs/evidence/usability-early-testing.md) — 100% tugas tuntas |
| Kami menguji diri sendiri dengan keras | [Audit menyeluruh Juli 2026](docs/AgriFlow_Audit_2026-07.pdf) — 7 temuan, termasuk yang menyalahkan kami |

<details>
<summary><b>1️⃣ Bukti produk digital — 9 dari 9 item</b> (klik untuk expand)</summary>

<br/>

Status hari ini: **MVP yang berjalan di produksi**, bukan mockup dan bukan proof of concept.

| Item yang diminta | Status | Bukti |
|---|:---:|---|
| Functional prototype | ✅ | Dashboard + bot WhatsApp + API, ketiganya berjalan |
| MVP | ✅ | Tiga pilar (deteksi, prediksi, distribusi) sudah melayani pengguna |
| Proof of concept | ✅ | [Demo data BPS asli 2022](docs/evidence/runs/demo_real_bps.txt) |
| Source code repository | ✅ | Repositori ini, lisensi terbuka |
| API test | ✅ | [Respons API produksi live](docs/evidence/runs/api-live-responses.md) · 40 tes otomatis endpoint |
| Working dashboard | ✅ | [agriflow-engine.vercel.app](https://agriflow-engine.vercel.app/) |
| Alpha/beta version | ✅ | Versi beta publik, akses tamu tanpa registrasi |
| Demo dengan input & output nyata | ✅ | [Keluaran demo](docs/evidence/runs/demo_real_bps.txt) · [respons API](docs/evidence/runs/api-live-responses.md) |
| Rule engine yang dapat dijalankan | ✅ | [`matching_engine/`](matching_engine) 4 lapis, satu perintah |

Tujuh pemanggilan nyata ke API produksi terekam apa adanya: enam berbalas 200, satu sengaja
dibuat salah untuk memperlihatkan jalur galat dan dibalas 404 yang menyebutkan pasangan
tersedia sehingga pemanggil bisa mengoreksi diri.

**Dua hal yang jujur perlu disebut.** `GET /health` melaporkan `"mock_mode": true`: data
pangannya sepenuhnya nyata (38 kabupaten, 6 komoditas BPS), tetapi lapisan bahasa alaminya
masih balasan tiruan karena kami menjalankan demo publik tanpa kunci berbayar. Repositori juga
belum punya rilis bernomor.

📄 [Halaman lengkap](docs/evidence/produk-digital.md)

</details>

<details>
<summary><b>2️⃣ Bukti pengujian — 10 dari 11 item</b> (klik untuk expand)</summary>

<br/>

| Item yang diminta | Status | Bukti |
|---|:---:|---|
| Test case | ✅ | [544 lulus, 8 skip](docs/evidence/runs/pytest.txt) · [`tests/`](tests) · [CI 4 leg](.github/workflows/test.yml) |
| Hasil eksperimen | ✅ | greedy vs optimal · [sensitivitas bobot](docs/evidence/runs/weight_sensitivity.txt) · [gap dua detektor](docs/evidence/runs/anomaly_detector_gap.txt) |
| Model evaluation | ✅ | [Backtest holdout baseline seasonal-naive, MAPE 10,8%](docs/evidence/runs/backtest_baseline.txt); backtest TimesFM 2.0 belum dijalankan |
| Performance test | ✅ | [latency](docs/evidence/runs/latency.txt) · [skala nasional](docs/evidence/runs/national_scale.txt) · [beban dashboard](docs/evidence/runs/dashboard_load.txt) |
| A/B test | ✅ | [Haversine vs jarak jalan](docs/evidence/runs/ab_test_road_distance.txt) |
| Hasil simulasi | ✅ | 25 skenario edge-case · [skenario pasokan langka](docs/evidence/runs/equity_comparison_constrained.txt) |
| Validation report | ✅ | [Audit menyeluruh](docs/AgriFlow_Audit_2026-07.pdf) · [metodologi data nyata](REAL_DATA_METHODOLOGY.md) |
| Security test awal | ✅ | [Ringkasan](docs/evidence/security-review.md) · 117 tes auth/kuota/RLS |
| Error log | ✅ | [Contoh log JSON](docs/evidence/runs/api-request-log-sample.jsonl) · [`request_log.py`](whatsapp_bot/request_log.py) |
| Usability testing | ✅ | [5 sesi, 20–22 Juli 2026](docs/evidence/usability-early-testing.md) |
| UAT | ⏳ | [Instrumen siap](docs/evidence/uat-test-cases.md), **belum dijalankan** |

**Angka kunci:** p99 engine 69 ms terhadap target 500 ms · 1.096 req/s dengan 0 gagal pada
1.000 pengguna · skala nasional **3.022 ms, masih 6× di atas target** dan itu kami cantumkan
apa adanya.

**Cacat yang kami ketahui:** `tests/test_auth_jwks.py` flaky, tercatat 3 kali (2 di CI leg
Windows py3.11, 1 di lokal), akar masalahnya belum ditemukan dan **tidak kami klaim selesai**.

📄 [Halaman lengkap](docs/evidence/pengujian.md)

</details>

<details>
<summary><b>3️⃣ Bukti pengguna — 7 dari 8 item</b> (klik untuk expand)</summary>

<br/>

| Item yang diminta | Status | Bukti |
|---|:---:|---|
| User feedback | ✅ | [5 berkas sesi + screenshot](docs/evidence/early-testing/) |
| Interview setelah testing | ✅ | Bagian "kesan & umpan balik" di tiap berkas sesi |
| Early tester | ✅ | [5 penguji, 20–22 Juli 2026](docs/evidence/usability-early-testing.md) |
| Completion rate | ✅ | 5 dari 5 sesi tuntas |
| Task success rate | ✅ | **20 dari 20 tugas (100%)** |
| Satisfaction score awal | ✅ | Kemudahan 4,6 · kegunaan 4,8 · rekomendasi 4,4 dari 5 |
| Testimoni pengguna | ✅ | [5 kutipan langsung](docs/evidence/usability-early-testing.md#kutipan) |
| Hasil observasi penggunaan | ⚠️ | Observer hadir tiap sesi, tetapi kolom waktu per tugas dibiarkan kosong |

Peserta, skor per orang, kutipan, apa yang mereka minta, dan apa yang membatasi umpan balik
ini semuanya ada di [**Umpan Balik Pengguna**](#-umpan-balik-pengguna) di bawah, lengkap dengan
tautan ke tiap berkas sesi.

📄 [Halaman lengkap](docs/evidence/pengguna.md)

</details>

<details>
<summary><b>4️⃣ Bukti implementasi awal non-digital — 1 dari 9 item, 2 sebagian</b> (klik untuk expand)</summary>

<br/>

**Ini kategori paling tipis kami, dan kami tidak berpura-pura sebaliknya.**

| Item yang diminta | Status | Keterangan |
|---|:---:|---|
| Demonstrasi metode | ✅ | 5 sesi demonstrasi langsung ke pengguna, didampingi observer |
| Simulasi proses | ⚠️ | 25 skenario simulasi ada, tetapi dijalankan sebagai kode, bukan role-play manusia |
| Prototype layanan publik | ⚠️ | Dashboard dapat diakses publik, tetapi bentuknya digital |
| Pilot layanan | ❌ | Surat kesediaan uji coba sudah ada, pelaksanaannya belum |
| Role-play | ❌ | Belum |
| Kelas atau modul terbatas | ❌ | Belum |
| Policy sandbox | ❌ | Belum ada pembahasan formal dengan regulator |
| Uji SOP | ❌ | SOP operasional belum disusun |
| Kegiatan komunitas terbatas | ❌ | Belum |

AgriFlow lahir sebagai produk digital yang langsung diuji lewat kanal digital. Uji SOP dan
policy sandbox baru masuk akal setelah ada mitra institusional yang menjalankan alokasi
berdasarkan keluaran AgriFlow; selama keluarannya masih saran kepada pengguna perorangan,
tidak ada SOP yang bisa diuji.

📄 [Halaman lengkap](docs/evidence/implementasi-non-digital.md)

</details>

<details>
<summary><b>5️⃣ Bukti kesiapan pihak luar — 4 dari 7 item</b> (klik untuk expand)</summary>

<br/>

| Item yang diminta | Status | Bukti |
|---|:---:|---|
| Letter of Intent | ✅ | Surat kesediaan uji coba bertanda tangan, 20 Juli 2026 |
| Kesediaan uji coba | ✅ | Piloting Jawa Timur, dashboard + chatbot WhatsApp |
| Validasi ahli domain | ✅ | Peneliti pascadoktoral BRIN menguji langsung dan memberi umpan balik |
| Bukti akses data | ✅ | [BPS](sample_data/bps_real/PROVENANCE.md) · [PIHPS Bapanas](sample_data/price_history/SOURCE.md) · OSRM |
| Kesepakatan eksplorasi | ⚠️ | Surat menyatakan dirinya "dasar pembahasan lebih lanjut", pembahasannya belum berjalan |
| Surat dukungan institusional | ❌ | Belum |
| Notulensi pembahasan pilot | ❌ | Belum, karena pembahasannya belum berlangsung |

Penandatangan: **Medina Uli Alba Somala, PhD**, Peneliti Pascadoktoral, Badan Riset dan Inovasi
Nasional. Suratnya menyatakan dirinya **pernyataan minat awal, bukan perjanjian mengikat**, dan
kami mengutipnya apa adanya. Berkas suratnya sengaja tidak dipublikasikan di repositori ini
karena memuat nomor telepon, alamat, dan tanda tangan pribadi; salinannya dapat diserahkan
langsung kepada panitia.

Seluruh data pangan terunut sampai berkas sumbernya: 70.953 baris harga harian PIHPS
2021–2025, produksi dan konsumsi BPS 38 kabupaten. Semuanya data publik, dan kami **tidak**
mengklaim punya perjanjian berbagi data istimewa.

📄 [Halaman lengkap](docs/evidence/kesiapan-pihak-luar.md)

</details>

---

# 💬 Umpan Balik Pengguna

Bukti pendukung di atas menjawab "apakah produknya bekerja". Bagian ini menjawab pertanyaan
yang berbeda: **apa kata orang yang memakainya.** Seluruh berkas sesi asli beserta screenshot
yang diambil saat itu ikut disertakan, jadi tidak ada yang perlu dipercaya begitu saja.

## Early tester — 5 sesi, 20 sampai 22 Juli 2026

Setiap peserta diberi empat tugas yang sama: cek harga komoditasnya di kabupaten sendiri, cari
pembeli untuk surplus, lihat prediksi atau anomali harga, dan temukan informasi yang dicari di
peta dashboard.

| Responden | Profil | Kanal | Tugas | Mudah | Berguna | Rekomendasi | Berkas sesi |
|---|---|---|:---:|:---:|:---:|:---:|---|
| **Aji** | Cabai, Kalanganyar, 8 bln | Dashboard + WA | 4/4 | 5 | 5 | 5 | [📄](docs/evidence/early-testing/Aji_cabai_kalanganyar.docx) |
| **Denisa Septalian Alhamda** | Bawang merah, Nganjuk, 5 thn | Dashboard | 4/4 | 5 | 5 | 4 | [📄](docs/evidence/early-testing/Deniz_bawang%20merah_nganjuk.docx) |
| **Labib** | Kentang, Dieng, 2 thn | Dashboard | 4/4 | 4 | 5 | 4 | [📄](docs/evidence/early-testing/labib_kentang_dieng.docx) |
| **Anisa** | Padi, Tapanuli Selatan, 15 thn | Dashboard + WA | 4/4 | 4 | 4 | 4 | [📄](docs/evidence/early-testing/anisa_padi_tapanuli%20selatan.docx) |
| **Medina Uli Alba Somala, PhD** | Peneliti Pascadoktoral, BRIN | Dashboard + WA | 4/4 | 5 | 5 | 5 | [📄](docs/evidence/early-testing/Alba_Peneliti%20Pascadoktoral.docx) |
| | | **Rata-rata** | **100%** | **4,6** | **4,8** | **4,4** | |

## Apa kata mereka

> "Sistem bagus dan canggih" — **Aji**, petani cabai

> "Inovasi bagus, harga yang dipatok juga masuk akal, meskipun mungkin untuk tahap awal akan
> coba paket pay as you go terlebih dahulu" — **Denisa**, petani bawang merah

> "inovasi bagus dengan harga murah" — **Labib**, petani kentang

> "inovasi yang bagus dan mudah digunakan" — **Anisa**, petani padi

> "inovasi yang sangat bagus dan bermanfaat bagi nusa dan bangsa" — **Medina Uli Alba Somala,
> PhD**, peneliti pascadoktoral BRIN

## Yang mereka minta, dan apa yang kami lakukan

Skor tinggi mudah didapat pada sesi yang dimoderasi pembuatnya sendiri. Yang lebih berguna
adalah pola yang berulang:

| Yang kami dengar | Berapa peserta | Tanggapan kami |
|---|:---:|---|
| Informasi penjual/supplier | **3 dari 5** | Masuk backlog. Permintaan ini sudah muncul lebih dulu di wawancara lapangan sebelum produk ada, jadi dua metode berbeda menunjuk hal yang sama |
| Susah membaca prediksi baseline | 1 | Cocok dengan temuan terukur bahwa [interval kepercayaan peramal memang belum terkalibrasi](docs/evidence/pengujian.md#3-model-evaluation): pita berlabel 80% baru mencapai 42% |
| Tarif berlangganan membingungkan | 1 | Penjelasan harga perlu diperbaiki sebelum penyebaran luas |
| Tampilan di ponsel kurang bagus | 1 | Perbaikan responsif |
| Ingin jual beli langsung di platform | 1 | Di luar cakupan saat ini. AgriFlow mempertemukan, belum memfasilitasi transaksi |

## Yang membatasi umpan balik ini

Kami tulis di sini, bukan di catatan kaki:

- **Seluruh sesi dimoderasi anggota tim.** Kehadiran pembuat produk menaikkan tingkat
  keberhasilan dan menahan kritik. Angka 4 dari 4 sebaiknya dibaca "tugasnya bisa
  diselesaikan", bukan "bisa diselesaikan tanpa bantuan".
- **Lima peserta itu sedikit**, dan segmen paling berisiko, petani berusia lanjut dengan
  literasi digital rendah, belum terwakili sama sekali.
- **Waktu per tugas tidak dicatat**, padahal kolomnya tersedia di lembar sesi.

[Protokol putaran 2](docs/evidence/usability-test-protocol.md) dirancang khusus menutup ketiganya:
moderator dari luar tim, kuota peserta literasi rendah, dan pencatatan waktu wajib.

## Umpan balik sebelum produk ada

Terpisah dari sesi di atas, kami mewawancarai **4 petani lintas komoditas dengan rekaman audio**
pada Mei sampai Juli 2026, saat belum ada produk yang bisa dicoba. Isinya bukti *kebutuhan*,
bukan bukti *kemudahan pakai*, dan tidak kami hitung sebagai usability testing. Tabel lengkapnya
di [Validasi Lapangan](#-validasi-lapangan--wawancara-petani).

📄 Rekap lengkap lima sesi: [usability-early-testing.md](docs/evidence/usability-early-testing.md) ·
Kategori bukti pengguna: [pengguna.md](docs/evidence/pengguna.md)

---

## Lisensi

MIT License — &copy; 2026 Hilmi. Lihat [`LICENSE`](LICENSE).

<p align="center"><em>Deteksi · Prediksi · Distribusi — untuk ketahanan pangan Indonesia.</em></p>
