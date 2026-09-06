# Mengaktifkan Login Dashboard

Panduan langkah demi langkah untuk menyalakan login AgriFlow di lingkungan nyata.

**Tidak ada satu pun langkah di bawah yang perlu dikerjakan di laptop Anda.**
Semuanya lewat browser: Supabase, Vercel, dan Hugging Face Spaces. File `.env`
lokal hanya diperlukan kalau Anda ingin menjalankan sistem di laptop untuk
pengembangan, dan itu opsional.

Selama langkah ini belum dikerjakan, sistem tetap jalan seperti sekarang:
peta publik terbuka, tombol "Masuk" tersembunyi, tidak ada yang rusak.

---

## 1. Supabase (browser)

1. Buat project baru di https://supabase.com/dashboard.
2. Buka **SQL Editor**, tempel isi `db/schema.sql`, jalankan.
   Ini membuat 12 tabel termasuk `subscriber`, `wa_usage_daily`, `payment_order`,
   lalu **mengunci semuanya dengan Row Level Security**.

   Langkah penguncian itu bukan opsional. Supabase otomatis membuka setiap tabel
   di skema `public` lewat PostgREST, dan kunci `anon` bersifat publik karena
   ikut terkirim ke browser setiap pengunjung. Tanpa RLS, siapa pun bisa
   mengambil kunci itu dari devtools lalu membaca tabel `subscriber` atau
   mengubah paketnya sendiri jadi `PRO`, sepenuhnya melewati pemeriksaan JWT
   di API.

3. **Verifikasi penguncian.** Masih di SQL Editor, jalankan:

   ```sql
   SELECT tablename, rowsecurity
     FROM pg_tables
    WHERE schemaname = 'public'
    ORDER BY rowsecurity, tablename;
   ```

   Ke-12 baris harus menunjukkan `rowsecurity = true`. Satu saja bernilai `f`
   berarti tabel itu masih bisa dibaca memakai kunci `anon` yang publik.

   Atau, kalau Anda punya connection string-nya, jalankan pemeriksa otomatis
   yang menguji keempat sifatnya sekaligus (tabel lengkap, RLS menyala, FORCE
   mati, dan peran publik benar-benar tertolak):

   ```bash
   python db/verify_rls.py --db-url "<connection-string-anda>"
   ```

   Keluar dengan kode 0 hanya kalau semuanya benar.

   > Jangan menambahkan `FORCE ROW LEVEL SECURITY`. `FORCE` membuat pemilik
   > tabel ikut terkena RLS, dan karena kita sengaja tidak mendefinisikan
   > policy apa pun, backend FastAPI akan ikut terkunci dan semua query
   > mengembalikan nol baris. Gejalanya mirip "database kosong" padahal datanya
   > ada.

4. Buka **Authentication > Providers**, pastikan **Email** aktif.
   Untuk uji coba internal, matikan "Confirm email" supaya akun langsung bisa dipakai.
4b. Buka **Authentication > URL Configuration**, tambahkan URL domain Vercel
   Anda di **Redirect URLs**, contoh `https://<domain-anda>.vercel.app/**`
   (dan `http://localhost:3000/**` untuk pengembangan lokal). Ini **wajib**
   untuk tautan "lupa kata sandi": `resetPasswordForEmail()` mengirim
   `redirectTo=.../reset-password`, dan Supabase menolak/mengabaikan
   `redirectTo` mana pun yang tidak ada di daftar ini, lalu diam-diam
   memakai **Site URL** sebagai gantinya — gejalanya tautan di email
   membawa pengguna ke halaman yang salah, bukan ke `/reset-password`.
5. Buka **Settings > API** dan salin tiga nilai berikut:

| Nilai | Dipakai di | Sifat |
|---|---|---|
| Project URL | Vercel + HF Spaces | publik |
| `anon` public key | Vercel | publik (aman di browser) |
| Connection string (Settings > Database) | HF Spaces | **RAHASIA** |

> `service_role` key **tidak** dipakai di mana pun pada proyek ini. Kalau suatu
> saat Anda memakainya, jangan pernah menaruhnya di variabel `NEXT_PUBLIC_*`,
> karena semua `NEXT_PUBLIC_*` ikut terkirim ke browser pengguna.

---

## 2. Vercel — dashboard (browser)

Project Settings > Environment Variables:

```
NEXT_PUBLIC_SUPABASE_URL       = https://xxxxxxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY  = eyJhbGciOi...
NEXT_PUBLIC_API_URL            = https://masteraaa123-agriflow-api.hf.space
```

Redeploy. Setelah ini tombol **Masuk** muncul, `/login`, `/account`,
`/forgot-password`, dan `/reset-password` hidup, dan `proxy.ts` mulai
menjaga `/account` di sisi server.

---

## 3. Hugging Face Spaces — API (browser)

Space Settings > Variables and secrets:

```
SUPABASE_URL      = https://xxxxxxxx.supabase.co     (Variable)
REQUIRE_AUTH      = false                            (Variable — lihat catatan)
PHONE_HASH_SALT   = <64 karakter acak>               (Secret)
```

Kalau project Supabase Anda memakai skema lama HS256, ganti `SUPABASE_URL`
dengan `SUPABASE_JWT_SECRET` (Secret). Salah satu saja, bukan keduanya.

Membuat salt:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Postur produksi (ditambahkan September 2026)

Begitu kunci Gemini dan Twilio nyata terpasang, tambahkan `APP_ENV=production`
(Variable). Server lalu menolak boot selama masih ada default demo yang aktif:
`MOCK_MODE=true`, `TWILIO_VALIDATE_SIGNATURE=false`, `BILLING_MOCK=true`,
atau `PHONE_HASH_SALT` kosong. Alasannya tercetak di log Space sebagai baris
`security.posture`. Daftar lengkap variabel, temuan audit, dan probe untuk
memverifikasi deployment ada di `docs/SECURITY_AUDIT_2026-09.md`.

### Kapan REQUIRE_AUTH dinyalakan

- `false` — peta, prediksi, dan anomali terbuka untuk umum. **Pakai ini saat
  penjurian**, supaya juri bisa mencoba tanpa membuat akun.
- `true` — ketiganya jadi khusus pelanggan. Pakai setelah ada pelanggan nyata.

`/billing/status` selalu butuh token, apa pun nilai flag ini, karena tanpa itu
siapa pun bisa menebak-nebak nomor telepon mana yang berlangganan.

---

## Catatan: ganti kata sandi tanpa kata sandi lama

Halaman `/reset-password` memberi formulir kepada siapa pun yang punya sesi
aktif, bukan hanya yang baru saja mengeklik tautan pemulihan. Ini disengaja:
mengandalkan sesi yang ada lebih tahan terhadap refresh halaman daripada
menunggu satu kali kejadian `PASSWORD_RECOVERY`.

Konsekuensinya perlu Anda sadari: pengguna yang sudah masuk dapat mengganti
kata sandinya **tanpa memasukkan kata sandi lama**. Kalau seseorang menemukan
komputer yang tidak terkunci dengan sesi AgriFlow masih hidup, ia bisa
mengambil alih akun itu.

Untuk akun dinas yang dipakai bergantian, periksa pengaturan autentikasi di
project Supabase Anda untuk opsi yang mewajibkan autentikasi ulang sebelum
perubahan kata sandi. Belum diverifikasi terhadap project sungguhan, jadi
perlakukan ini sebagai hal yang harus dicek saat penyiapan, bukan sebagai
langkah yang sudah terbukti.

---

## 4. Verifikasi

```bash
curl -s https://<api-anda>/health | python -m json.tool
```

Yang harus terlihat:

```json
{
  "auth_configured": true,      // ← kalau false, env belum terbaca
  "require_auth": false,
  "phone_hash_salted": true,    // ← kalau false, PHONE_HASH_SALT belum diset
  "quota_enabled": false
}
```

Lalu pastikan pintu terkunci benar-benar terkunci:

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  "https://<api-anda>/billing/status?phone=%2B628123456789"
# harus 401
```

---

## Skala: apa yang sudah terbukti

Diukur dengan `python benchmarks/dashboard_load.py --users 2000`:

| Metrik | Hasil |
|---|---|
| Pengguna serentak | 2.000 |
| Permintaan | 10.000 (5 per pengguna) |
| Throughput | ~1.124 req/detik |
| p99 muat halaman penuh | 211 ms |
| Gagal | 0 |

Verifikasi JWT bukan hambatan: ~40.000 verifikasi/detik/core, sekitar 0,025 ms
per permintaan.

**Kalau perlu lebih dari itu:**

1. Tambah worker: `uvicorn --workers 4`. Engine bersifat baca-saja setelah
   startup, jadi menambah worker aman.
2. Kalau paywall WhatsApp dinyalakan (`QUOTA_ENABLED=true`) **wajib** pindah ke
   `QUOTA_BACKEND=postgres`. Penyimpanan JSON menulis ulang seluruh berkas tiap
   permintaan (60 ms pada 5.000 pengguna) dan tidak aman untuk banyak worker.
3. Jaga anggaran koneksi: `worker x (DB_POOL_SIZE + DB_MAX_OVERFLOW)` harus di
   bawah batas paket Supabase Anda.

---

## Lapisan pengamanan

Empat lapis, dan penting untuk tahu mana yang benar-benar menjaga data:

| Lapis | Berkas | Fungsi |
|---|---|---|
| Tampilan | `AccountMenu.tsx`, `AuthProvider` | Menyembunyikan menu. **Bukan** pengamanan. |
| Optimistis | `proxy.ts` | Memantulkan pengunjung dari `/account`. Cookie palsu bisa lolos. |
| **Otoritatif** | `whatsapp_bot/auth.py` | **Verifikasi tanda tangan JWT. Ini yang menjaga jalur API.** |
| **Otoritatif** | RLS di `db/schema.sql` | **Menutup jalur PostgREST. Tanpa ini kunci `anon` yang publik bisa membaca `subscriber` langsung, melewati semua lapis di atas.** |

Urutan ini disengaja dan sesuai anjuran dokumentasi Next.js: proxy untuk
pemeriksaan optimistis, otorisasi sesungguhnya di lapisan data.

Dua lapis otoritatif itu menjaga dua pintu yang berbeda, dan keduanya perlu.
Memverifikasi JWT di API tidak ada gunanya kalau tabel yang sama masih bisa
dibaca langsung lewat PostgREST memakai kunci `anon`.

Kasus penolakan yang sudah diuji (`tests/test_auth.py`, 29 pengujian): tanda
tangan palsu, token tanpa tanda tangan (`alg: none`), token kedaluwarsa,
audience salah, secret project lain, header tanpa skema Bearer, dan tanpa
header sama sekali.

---

## Kalau ada yang tidak beres

| Gejala | Penyebab yang paling sering |
|---|---|
| Tombol Masuk tidak muncul | `NEXT_PUBLIC_SUPABASE_*` belum diset di Vercel, atau belum redeploy |
| Semua permintaan 401 | `SUPABASE_URL` di API berbeda project dengan yang di Vercel |
| Login berhasil lalu keluar sendiri | Cookie diblokir; pastikan dashboard dan API sama-sama HTTPS |
| `/health` bilang `auth_configured: false` | Env belum terbaca Space; restart Space setelah menyimpan |
| `phone_hash_salted: false` | `PHONE_HASH_SALT` kosong. Mengubahnya nanti akan mereset semua identitas |
| Tautan "lupa kata sandi" membawa ke halaman yang salah, bukan `/reset-password` | Domain Vercel belum ada di **Authentication > URL Configuration > Redirect URLs** (lihat langkah 4b) |
| `/reset-password` selalu bilang tautan tidak valid, walau baru diklik | Tautan sudah pernah dipakai (satu kali pakai) atau kedaluwarsa — di Supabase, kirim ulang lewat `/forgot-password` |
