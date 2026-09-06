# Audit Keamanan AgriFlow, September 2026

Penulis: Hilmi (https://master-hilmi.vercel.app/)
Tanggal: 6 September 2026
Cakupan: dashboard Next.js di Vercel, API FastAPI di Hugging Face Spaces, konfigurasi Supabase, pipeline CI, dan dependensi kedua stack.

Dokumen ini mencatat apa yang ditemukan, apa yang sudah diperbaiki di kode, dan apa yang masih harus dilakukan oleh operator di luar repo. Bagian terakhir adalah daftar variabel lingkungan untuk postur produksi.

## 1. Ringkasan

Kondisi sebelum audit: kedua deployment sudah punya dasar yang baik (header HSTS dan nosniff di Vercel, verifikasi JWT yang fail-closed, RLS di Supabase, tidak ada rahasia di riwayat git). Namun API publik masih memakai default demo di semua sisi: tidak ada pembatas laju, CORS terbuka untuk seluruh pelanggan Vercel dan Hugging Face, dokumentasi OpenAPI terbuka, endpoint `/health` membocorkan postur konfigurasi, dan `/chat` menerima identitas pengirim dari klien. Dashboard belum punya Content Security Policy dan memakai Next.js 16.2.6 yang membawa beberapa advisori tingkat tinggi, termasuk bypass proxy.

Kondisi setelah audit: 20 temuan, 17 selesai di kode, 3 memerlukan tindakan operator (bagian 5). Suite pengujian naik dari 544 ke 593 kasus, semuanya lulus.

## 2. Temuan dan status

Tingkat mengikuti CVSS kualitatif: Tinggi berarti dapat dieksploitasi tanpa kredensial dan berdampak pada ketersediaan atau integritas; Sedang berarti butuh kondisi tertentu atau hanya berdampak pada kerahasiaan konfigurasi; Rendah berarti pengerasan defensif.

| No | Tingkat | Komponen | Temuan | Status |
|---|---|---|---|---|
| 1 | Tinggi | API | Tidak ada pembatas laju. `/api/v1/simulate` menjalankan solver LP dan `/chat` memanggil Gemini per permintaan, sehingga satu klien dapat menghabiskan satu worker. | Selesai: `RateLimitMiddleware`, dua tier (umum 240/menit, berat 30/menit), 429 dengan `Retry-After`. |
| 2 | Tinggi | Dashboard | Next.js 16.2.6 membawa 7 advisori tingkat tinggi (bypass proxy di App Router, SSRF di Server Actions, DoS optimasi gambar, cache confusion). | Selesai: naik ke 16.3.4, `npm audit` bersih. |
| 3 | Tinggi | API | `pyjwt` 2.10.1 (11 advisori) dan `python-multipart` 0.0.28 (3 advisori) yang dipakai persis di jalur verifikasi token dan parsing webhook Twilio. | Selesai: `pyjwt` 2.13.0, `python-multipart` 0.0.32. |
| 4 | Tinggi | API | Webhook `/whatsapp` menerima permintaan tanpa tanda tangan Twilio secara default (`TWILIO_VALIDATE_SIGNATURE=false`, `MOCK_MODE=true`). Siapa pun dapat mengirim pesan atas nama nomor mana pun. | Selesai di kode: `APP_ENV=production` menolak boot bila validasi tanda tangan mati. Butuh operator (bagian 5). |
| 5 | Sedang | API | `/chat` menghormati field `from` dari klien. Dengan kuota aktif, perintah STATUS, UPGRADE, dan BAYAR berjalan sebagai nomor siapa pun. | Selesai: field diabaikan saat produksi. |
| 6 | Sedang | API | CORS mengizinkan regex `https://.*\.(vercel\.app|hf\.space)`, yaitu semua pelanggan kedua platform, dengan `allow_headers=*`. | Selesai: daftar eksplisit + regex terbatas pada nama proyek; header dibatasi ke `Authorization` dan `Content-Type`; kredensial tidak pernah diizinkan. |
| 7 | Sedang | API | `/docs`, `/redoc`, `/openapi.json` terbuka di produksi. | Selesai: mati saat produksi kecuali `API_DOCS_ENABLED=true`. |
| 8 | Sedang | API | `/health` mengembalikan `phone_hash_salted`, `auth_configured`, `require_auth`, `mock_mode`, `billing_mock`, `quota_backend`. Ini peta konfigurasi untuk penyerang. | Selesai: produksi hanya menjawab `status`, `version`, `data_loaded`. |
| 9 | Sedang | Dashboard | Tidak ada Content Security Policy. Injeksi skrip apa pun akan berjalan penuh. | Selesai: CSP berbasis nonce per permintaan di `proxy.ts` dengan `strict-dynamic`, `frame-ancestors 'none'`, `object-src 'none'`, `form-action 'self'`. Font Inter dipindah ke `next/font` agar tidak ada sumber pihak ketiga selain ubin peta OpenStreetMap. |
| 10 | Sedang | API | Tidak ada header keamanan pada respons API. Halaman HTML pembayaran tanpa CSP. | Selesai: `SecurityHeadersMiddleware` (nosniff, DENY, CSP tolak-semua untuk JSON, CSP khusus form untuk HTML, `Cache-Control: no-store`, HSTS bila di balik HTTPS). |
| 11 | Sedang | API | Verifikasi JWT tidak memeriksa `iss`. Token sah dari proyek Supabase lain dengan JWKS yang dikendalikan penyerang tidak akan tertolak oleh algoritma atau audience. | Selesai: `iss` wajib sama dengan `{SUPABASE_URL}/auth/v1`; `exp` dan `sub` wajib ada; toleransi jam 30 detik. |
| 12 | Sedang | API | `SimulateRequest` tanpa batas: daftar kabupaten tak terbatas, `bbm_pct=1e308` membuat biaya bahan bakar tak hingga masuk ke solver, `limit` negatif atau raksasa. | Selesai: semua field dibatasi (daftar maksimal 100, `bbm_pct` antara -90 dan 1000, `limit` 1 sampai 500, `allocator` hanya `lp`, `greedy`, `stable`). |
| 13 | Sedang | API | Tidak ada batas ukuran body permintaan. | Selesai: `BodySizeLimitMiddleware`, default 64 KiB, 413 sebelum parsing; pesan chat dan WhatsApp dibatasi 1000 karakter. |
| 14 | Sedang | Kontainer | Kontainer berjalan sebagai root; `.dockerignore` hanya mengecualikan `.env` di root, bukan `whatsapp_bot/.env`, dan tidak mengecualikan `.state/`. | Selesai: user `agriflow` uid 1000, pola `**/.env*`, `.state/` dan `.tmp/` dikecualikan, `HEALTHCHECK`, uvicorn dengan `--proxy-headers`. |
| 15 | Rendah | API | Ekspor CSV tidak menetralkan sel yang diawali `=`, `+`, `-`, `@` (injeksi formula spreadsheet). | Selesai: awalan apostrof pada sel string berbahaya. |
| 16 | Rendah | API | `/billing/pay/{order_id}` dan `/billing/confirm` menerima id sembarang dan menggemakan id yang tidak dikenal di pesan 404. | Selesai: format `AF-<8 hex>` divalidasi, id tidak digemakan, nilai di HTML di-escape. |
| 17 | Rendah | CI | Workflow tanpa blok `permissions` (token default bisa write), tidak ada audit dependensi, tidak ada pemindaian rahasia, tidak ada CodeQL, tidak ada Dependabot. | Selesai: `permissions: contents: read` di semua workflow; `security.yml` baru (pip-audit, npm audit, gitleaks, CodeQL, uji postur produksi); `dependabot.yml` untuk pip, npm, dan GitHub Actions. |
| 18 | Rendah | Dashboard | Header `X-Powered-By: Next.js` dan tanpa `Cross-Origin-Opener-Policy`. | Selesai: `poweredByHeader: false`, COOP `same-origin`, `X-DNS-Prefetch-Control: off`. |
| 19 | Rendah | Repo | Tidak ada `SECURITY.md`. | Selesai. |
| 20 | Informasi | Supabase | RLS ada di skema dan ada pemeriksa `db/verify_rls.py`, tetapi audit ini tidak punya connection string untuk memverifikasi proyek produksi. | Butuh operator (bagian 5). |

## 3. Yang diverifikasi dan tidak berubah

- Tidak ada rahasia di riwayat git. Pemindaian pola kunci (Google, Twilio, Hugging Face, JWT, connection string Postgres) atas seluruh riwayat dan working tree kosong. File `.env` tidak pernah di-commit.
- Verifikasi JWT sudah benar sejak awal: algoritma dibatasi, `alg=none` ditolak, audience diperiksa, kegagalan tidak membedakan sebab (tidak ada oracle).
- Login dashboard: tidak ada pendaftaran mandiri, error dinetralkan (tidak ada enumerasi akun), `next=` hanya menerima path relatif (tidak ada open redirect), dev-login dikompilasi keluar bila `NEXT_PUBLIC_DEV_LOGIN` tidak diset saat build.
- Vercel: `ssoProtection` aktif untuk semua deployment kecuali domain produksi, sehingga URL preview tidak dapat diakses publik.
- Kueri database memakai parameter SQLAlchemy `text()` dengan bind, tidak ada format string.
- Cookie tamu dan cookie dev hanya memengaruhi halaman mana yang dirender, bukan data. Data dilindungi di API.

## 4. Verifikasi

| Pemeriksaan | Hasil |
|---|---|
| `pytest` seluruh suite | 593 lulus, 1 dilewati |
| `tests/test_security_hardening.py` (baru) | 34 kasus: header, batas body, pembatas laju per IP dan per tier, cakupan CORS, postur produksi, batas input |
| `tests/test_auth_jwks.py` (ditambah) | penolakan `iss` salah dan `iss` hilang; uji algorithm confusion dirakit manual karena PyJWT 2.13 menolak mencetak token HS256 dengan kunci publik |
| `npm audit --omit=dev` | 0 kerentanan (sebelumnya 7 tinggi, 1 rendah) |
| `pip-audit` | 0 kerentanan pada paket yang diperbarui (sebelumnya 15 advisori di 2 paket) |
| `next build` | berhasil, semua rute dirender per permintaan (syarat nonce) |
| Uji browser Playwright lokal | 5 halaman, nonce hadir di setiap respons, skrip berjalan, 12 ubin peta dimuat, tidak ada pelanggaran CSP setelah font dipindah ke `next/font` |
| Probe API lokal | header keamanan hadir di JSON, 404, dan 429; permintaan `/chat` ke-31 dalam satu menit menerima 429 |

## 5. Tindakan operator (di luar repo)

1. **Hugging Face Space, variabel.** Setelah kunci Gemini dan Twilio nyata terpasang, set:
   `APP_ENV=production`, `MOCK_MODE=false`, `TWILIO_VALIDATE_SIGNATURE=true`, `BILLING_MOCK=false` (atau biarkan `true` selama kuota mati, dan set `SECURITY_POSTURE_STRICT=false` sebagai pengecualian sadar), `PHONE_HASH_SALT=<64 hex>`. Server menolak boot bila ada yang tertinggal, dan menulis alasannya di log sebagai baris `security.posture`.
2. **Supabase.** Jalankan `python db/verify_rls.py --db-url "<connection string>"` terhadap proyek produksi dan simpan keluarannya. Skema sudah benar; yang belum terbukti hanyalah bahwa skema itulah yang terpasang.
3. **Vercel.** Pastikan `NEXT_PUBLIC_DEV_LOGIN` tidak ada di environment Production maupun Preview. Audit ini tidak punya akses baca ke daftar variabel (MCP Vercel tidak mengembalikannya), jadi periksa manual di Project Settings.
4. **Setelah deploy API berikutnya**, ulangi probe berikut dari luar dan pastikan hasilnya sama dengan bagian 4:

   ```bash
   H=https://masteraaa123-agriflow-api.hf.space
   curl -sI $H/api/v1/commodities | grep -i "content-security-policy\|x-ratelimit"
   curl -s -o /dev/null -w "%{http_code}\n" $H/docs          # 404 saat produksi
   curl -s $H/health                                          # tiga field saja
   curl -s -o /dev/null -D - -X OPTIONS $H/api/v1/matches \
     -H "Origin: https://evil.vercel.app" \
     -H "Access-Control-Request-Method: GET" | grep -i allow-origin   # kosong
   ```

## 6. Referensi variabel lingkungan baru

| Variabel | Default | Arti |
|---|---|---|
| `APP_ENV` | `development` | `production` mengaktifkan pemeriksaan postur, `/health` minimal, `/chat` anonim, dokumentasi mati |
| `SECURITY_POSTURE_STRICT` | `true` | `false` mengubah penolakan boot menjadi peringatan |
| `API_DOCS_ENABLED` | `true` di dev, `false` di prod | Swagger UI dan `openapi.json` |
| `RATE_LIMIT_ENABLED` | `true` | pembatas laju per IP |
| `RATE_LIMIT_PER_MINUTE` | `240` | tier umum |
| `RATE_LIMIT_HEAVY_PER_MINUTE` | `30` | `/chat`, `/whatsapp`, `/billing/*`, `/api/v1/simulate`, `/api/v1/matches/explain`, `/api/v1/report.csv` |
| `TRUST_PROXY` | `true` | ambil IP klien dari hop pertama `X-Forwarded-For` |
| `MAX_BODY_BYTES` | `65536` | batas body permintaan |
| `MAX_MESSAGE_CHARS` | `1000` | panjang pesan chat dan WhatsApp |
| `CORS_ALLOWED_ORIGINS` | kosong | origin tambahan, dipisah koma |
| `CORS_ALLOWED_ORIGIN_REGEX` | `^https://agriflow-engine(-[a-z0-9-]+)?\.vercel\.app$` | regex origin preview |

## 7. Yang sengaja tidak diubah

- `REQUIRE_AUTH` tetap `false` secara default. Data peta adalah data referensi pemerintah dan keputusan untuk membuka atau menutupnya adalah keputusan produk, bukan keamanan. Postur produksi mencatatnya tetapi tidak memaksa.
- Cookie tamu untuk juri tetap ada. Ia hanya menentukan halaman, bukan data.
- Pembatas laju berjalan di memori per replika. Untuk beberapa replika, angka efektif adalah kelipatan jumlah replika. Ini cukup untuk satu Space; bila nanti diskalakan, pindahkan ke Redis atau WAF Hugging Face.
- Id pesanan `AF-<8 hex>` (32 bit) tetap. Dengan tier berat 30 permintaan per menit, enumerasi tidak praktis, dan format ini tertanam di perintah WhatsApp `BAYAR`.
