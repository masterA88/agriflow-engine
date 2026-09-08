# Bukti Pendukung AgriFlow

Halaman ini adalah pintu masuk tunggal ke seluruh bukti pendukung AgriFlow, disusun mengikuti
lima kategori yang diminta panduan submission. Setiap baris menunjuk artefak yang bisa dibuka,
dan setiap angka disertai perintah untuk direproduksi.

Aturan yang kami pegang di seluruh halaman ini: **kalau sesuatu belum dijalankan, statusnya
ditulis belum dijalankan.** Tidak ada hasil yang dikarang untuk mengisi tabel, dan temuan yang
tidak menguntungkan kami tetap dicantumkan.

Terakhir diperbarui: **22 Juli 2026**.

---

## Peta lima kategori

| # | Kategori | Status | Halaman |
|---|---|---|---|
| 1 | **Bukti produk digital** | ✅ 9 dari 9 item | [produk-digital.md](produk-digital.md) |
| 2 | **Bukti pengujian** | ✅ 10 dari 11 item | [pengujian.md](pengujian.md) |
| 3 | **Bukti pengguna** | ✅ 7 dari 8 item | [pengguna.md](pengguna.md) |
| 4 | **Bukti implementasi awal non-digital** | ⚠️ 1 dari 9 item, 2 sebagian | [implementasi-non-digital.md](implementasi-non-digital.md) |
| 5 | **Bukti kesiapan pihak luar** | ✅ 4 dari 7 item | [kesiapan-pihak-luar.md](kesiapan-pihak-luar.md) |

Kategori 4 adalah yang paling tipis, dan kami tidak menutupinya. AgriFlow lahir sebagai produk
digital, sehingga bukti non-digitalnya terbatas pada demonstrasi metode kepada pengguna.
Rinciannya, termasuk apa yang belum ada, di
[halamannya sendiri](implementasi-non-digital.md).

---

## Yang paling cepat meyakinkan

Bila waktu terbatas, empat tautan ini yang paling padat isinya:

| Ingin melihat | Buka |
|---|---|
| Produknya benar-benar jalan | [Respons API produksi live](runs/api-live-responses.md), 6 endpoint, diambil hari ini |
| Enginenya benar-benar menghitung | [Demo data BPS asli 2022](runs/demo_real_bps.txt), 84 match, 467 ribu ton |
| Pengguna nyata sudah mencobanya | [5 sesi early tester](usability-early-testing.md), 100% tugas tuntas |
| Kami menguji diri sendiri dengan keras | [Audit menyeluruh Juli 2026](../AgriFlow_Audit_2026-07.pdf), 7 temuan, termasuk yang menyalahkan kami |

---

## Ringkasan per kategori

### 1. Bukti produk digital → [selengkapnya](produk-digital.md)

Repositori ini sendiri, dashboard yang hidup di
[agriflow-engine.vercel.app](https://agriflow-engine.vercel.app/), API produksi di Hugging Face
Space dengan [respons nyata yang terekam](runs/api-live-responses.md), rule engine 4 lapis yang
bisa dijalankan siapa pun lewat satu perintah, dan bot WhatsApp. Statusnya **MVP yang
berjalan**, bukan mockup.

### 2. Bukti pengujian → [selengkapnya](pengujian.md)

597 tes lulus lintas OS di CI, backtest baseline seasonal-naive dengan MAPE 10,8% dan interval terkalibrasi 80% (model TimesFM 2.0 yang dilayani belum di-backtest), uji performa sampai skala
nasional, A/B test jarak jalan, 25 skenario simulasi, uji keamanan awal, error log terstruktur,
dan laporan audit menyeluruh. Yang belum ada hanya UAT.

### 3. Bukti pengguna → [selengkapnya](pengguna.md)

Lima sesi early tester berbasis tugas dengan task success 100% dan skor kepuasan 4,4 sampai 4,8
dari 5, ditambah empat wawancara petani dengan rekaman audio. Keterbatasannya, terutama karena
sesi dimoderasi anggota tim, ditulis bersama hasilnya.

### 4. Bukti implementasi awal non-digital → [selengkapnya](implementasi-non-digital.md)

Yang ada: demonstrasi metode langsung ke pengguna di lima sesi. Yang belum ada: pilot layanan,
role-play, policy sandbox, uji SOP, kelas terbatas, dan kegiatan komunitas.

### 5. Bukti kesiapan pihak luar → [selengkapnya](kesiapan-pihak-luar.md)

Satu surat kesediaan uji coba bertanda tangan dari peneliti BRIN, validasi dari ahli domain
yang sama, dan bukti akses data resmi BPS serta PIHPS yang terunut sampai berkas sumbernya.

---

## Struktur berkas

```
docs/evidence/
├── README.md                        ← halaman ini, pintu masuk lima kategori
├── produk-digital.md                ← kategori 1
├── pengujian.md                     ← kategori 2
├── pengguna.md                      ← kategori 3
├── implementasi-non-digital.md      ← kategori 4
├── kesiapan-pihak-luar.md           ← kategori 5
├── usability-early-testing.md       ← hasil 5 sesi early tester
├── usability-test-protocol.md       ← instrumen putaran 2
├── uat-test-cases.md                ← instrumen UAT, belum dijalankan
├── security-review.md               ← cakupan uji keamanan awal
├── early-testing/                   ← berkas sesi asli + screenshot
└── runs/                            ← keluaran mentah tiap perintah
```
