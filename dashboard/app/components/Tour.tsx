"use client";

import { Icons } from "./Icons";

export const TOUR_STEPS = [
  { title: "Komoditas dengan data BPS asli", desc: "Pilih komoditas di kanan atas. Enam komoditas ini punya neraca produksi dan konsumsi per kabupaten dari BPS 2022; peta, rekomendasi, dan KPI berubah mengikutinya." },
  { title: "Data per", desc: "Pil di kiri atas menampilkan tanggal data yang benar-benar dilayani API: harga harian, neraca BPS, versi engine, dan allocator. Angka ini datang dari /api/v1/meta, bukan diketik." },
  { title: "Rekomendasi yang bisa dijelaskan", desc: "Setiap kartu memuat skor lima dimensi, pengali equity, dan alasan dalam bahasa manusia. Tombol 'Bandingkan pemasok' menampilkan semua pemasok yang layak dan mengapa yang lain tidak dipilih." },
  { title: "Simulasi what-if", desc: "Centang erupsi Semeru, banjir sentra padi, Ramadan, atau BBM naik, lalu jalankan ulang engine. Hasilnya dibandingkan dengan baseline hari ini, termasuk match yang dibatalkan dan dialihkan." },
];

export default function Tour({ step, onStep, onClose }: { step: number | null; onStep: (s: number) => void; onClose: () => void }) {
  if (step === null) return null;
  const s = TOUR_STEPS[step];
  return (
    <div className="fixed inset-0 bg-black/60 z-[99998] flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-5 space-y-4">
        <div className="flex justify-between items-center text-[10px] text-[#5b7245] font-bold uppercase tracking-wider">
          <span className="flex items-center gap-1"><Icons.HelpCircle className="w-3 h-3" /> Panduan</span>
          <span>Langkah {step + 1} dari {TOUR_STEPS.length}</span>
        </div>
        <div className="space-y-1.5">
          <h3 className="font-bold text-sm text-zinc-900">{s.title}</h3>
          <p className="text-xs text-zinc-600 leading-relaxed">{s.desc}</p>
        </div>
        <div className="flex justify-between items-center pt-3 border-t border-zinc-100">
          <button onClick={onClose} className="text-xs text-zinc-400 hover:text-zinc-700 font-semibold">Lewati</button>
          <div className="flex gap-2">
            {step > 0 && <button onClick={() => onStep(step - 1)} className="border border-zinc-200 text-zinc-700 rounded-lg px-3 py-1.5 text-xs font-semibold hover:bg-zinc-50">Kembali</button>}
            {step < TOUR_STEPS.length - 1
              ? <button onClick={() => onStep(step + 1)} className="bg-[#5b7245] text-white rounded-lg px-4 py-1.5 text-xs font-bold hover:bg-[#4f643c]">Lanjut</button>
              : <button onClick={onClose} className="bg-[#5b7245] text-white rounded-lg px-4 py-1.5 text-xs font-bold hover:bg-[#4f643c]">Selesai</button>}
          </div>
        </div>
      </div>
    </div>
  );
}
