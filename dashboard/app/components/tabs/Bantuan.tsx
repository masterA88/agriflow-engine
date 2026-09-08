"use client";

import { useMemo, useState, useEffect } from "react";
import { Icons } from "../Icons";
import { track } from "../../lib/telemetry";

type FAQ = { q: string; a: string; category: "Peta & Data" | "Distribusi" | "Harga" | "Simulasi" | "WhatsApp" };

const FAQS: FAQ[] = [
  { category: "Peta & Data", q: "Dari mana angka surplus dan defisit?", a: "Produksi per kabupaten dari BPS Jawa Timur dan konsumsi per kapita Susenas (beras per kabupaten; hortikultura memakai rata-rata nasional Kementan), tahun acuan 2022, dikonversi ke ton. Rumusnya: surplus/defisit = produksi dikurangi konsumsi. Metodologi lengkap ada di REAL_DATA_METHODOLOGY.md di repositori." },
  { category: "Peta & Data", q: "Apa arti 'Data per' di atas?", a: "Tanggal data yang benar-benar dilayani API: harga harian terakhir (Siskaperbapo Jatim, PIHPS sebagai cadangan), tahun neraca BPS, tahun IPM, kapan scan anomali dan prakiraan dibuat, serta versi engine. Semua dibaca dari /api/v1/meta." },
  { category: "Distribusi", q: "Bagaimana rekomendasi dihitung?", a: "Empat lapis: (0) tier kota IHK, (1) hard constraint: jarak jalan OSRM di bawah batas komoditas, umur panen di bawah masa simpan, volume minimum, kabupaten tidak terjangkau, override Pemda; (2) skor lima dimensi dengan bobot jarak 22%, volume 22%, harga 22%, masa simpan 18%, iklim rute 16%; (3) alokasi optimal LP transportasi berkapasitas dengan pengali equity 1,30 / 1,15 / 1,05 untuk kabupaten ber-IPM rendah. Kartu match menampilkan semua komponen ini." },
  { category: "Distribusi", q: "Kenapa pemasok berskor tinggi tidak dipilih?", a: "Allocator memaksimalkan total welfare berbobot equity untuk semua defisit sekaligus, jadi pemasok bisa dialihkan ke defisit lain bila totalnya lebih tinggi. Tombol 'Bandingkan pemasok' menampilkan seluruh pemasok layak beserta alokasinya." },
  { category: "Harga", q: "Prakiraan memakai model apa?", a: "TimesFM 2.0 (foundation model deret waktu) untuk 38 kabupaten/kota, dengan pita P10 sampai P90 dari kuantil model (target coverage 80%). Bila TimesFM tidak tersedia saat prakiraan dibuat, sistem jatuh ke seasonal-naive baseline (median bulan yang sama, MAPE 10,4% pada backtest 30 hari) dan panel prakiraan memberi label itu secara eksplisit." },
  { category: "Harga", q: "Bagaimana anomali dideteksi?", a: "Deret harga dipisahkan dari tren dan musiman bulanan, lalu residualnya diuji dengan MAD bergulir (Hampel), dengan syarat bertahan minimal dua hari. Gerbang yang sama dipakai engine untuk mengeluarkan kabupaten yang sedang anomali dari matching." },
  { category: "Simulasi", q: "Apa yang terjadi saat saya mencentang skenario?", a: "Engine dijalankan ulang dari awal dengan kondisi itu: kabupaten yang dinyatakan tidak terjangkau dikeluarkan, profil bobot Ramadan diaktifkan, batas jarak menyusut saat BBM naik, rute Madura diblokir saat Suramadu ditutup. Hasilnya dibandingkan dengan baseline dan match yang dibatalkan atau dialihkan ditampilkan." },
  { category: "Peta & Data", q: "Kenapa hanya enam komoditas dan tahun 2022?", a: "Karena itu batas data publik per kabupaten yang lengkap di semua sumber. Engine menerima komoditas apa pun; begitu BPS merilis produksi per kabupaten komoditas lain atau tahun lebih baru, pipeline yang sama memprosesnya." },
];

export default function Bantuan() {
  const [q, setQ] = useState("");
  const shown = useMemo(() => {
    const k = q.trim().toLowerCase();
    if (!k) return FAQS;
    return FAQS.filter((f) => f.q.toLowerCase().includes(k) || f.a.toLowerCase().includes(k) || f.category.toLowerCase().includes(k));
  }, [q]);
  useEffect(() => {
    const k = q.trim();
    if (!k) return;
    const t = setTimeout(() => track("faq_search", { detail: { query_len: k.length, result_count: shown.length, matched: shown.length > 0 } }), 800);
    return () => clearTimeout(t);
  }, [q, shown.length]);
  return (
    <div className="flex flex-col gap-4 max-w-4xl">
      <div>
        <h2 className="text-lg sm:text-xl font-bold text-white tracking-tight">Bantuan</h2>
        <p className="text-xs text-emerald-100/80 mt-0.5">Cara membaca dashboard, dan dari mana setiap angka berasal.</p>
      </div>
      <div className="bg-white rounded-2xl px-4 py-3 shadow-sm flex items-center gap-3">
        <Icons.Search className="w-4 h-4 text-[#5b7245] shrink-0" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari: skor, equity, prakiraan, anomali, simulasi..." className="flex-1 bg-transparent text-xs text-zinc-800 focus:outline-none placeholder-zinc-400" />
        {q && <button onClick={() => setQ("")} className="text-zinc-400 hover:text-zinc-700 text-xs font-bold">Hapus</button>}
      </div>
      <div className="flex flex-col gap-3">
        {shown.length === 0 && <div className="bg-white rounded-2xl p-8 text-center text-zinc-400 text-xs">Tidak ditemukan.</div>}
        {shown.map((f) => (
          <div key={f.q} className="bg-[#f1f6ef] border border-[#e4eedf] rounded-2xl p-4 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="bg-[#e4eedf] text-[#4e643c] text-[9px] font-extrabold px-2 py-0.5 rounded uppercase tracking-wider">{f.category}</span>
              <h3 className="font-bold text-xs text-zinc-800">{f.q}</h3>
            </div>
            <p className="text-xs text-zinc-700 leading-relaxed">{f.a}</p>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-emerald-100/80">Kode, tes (538 lulus), audit, dan bukti pengujian terbuka di github.com/masterA88/agriflow-engine.</p>
    </div>
  );
}
