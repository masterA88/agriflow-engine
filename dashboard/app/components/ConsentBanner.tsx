"use client";

// Consent notice for behaviour telemetry, per UU PDP 27/2022 articles 20 to 22:
// explicit, specific per purpose, informed, recorded, withdrawable. Both
// purposes are named, including the aggregated report sold to institutions,
// because collecting under one purpose and selling under another is the
// purpose-limitation failure the legal brief flags. "Tolak" is as easy as
// "Setuju" and the dashboard works either way.

import Link from "next/link";
import { useConsent, writeConsent, track, flush } from "../lib/telemetry";

export default function ConsentBanner() {
  const consent = useConsent();
  if (consent !== "none") return null;

  const accept = () => {
    writeConsent("accepted");
    track("optin", { detail: { decision: "accept", path: location.pathname } });
    flush(false);
  };
  const decline = () => {
    writeConsent("declined");
  };

  return (
    <div role="dialog" aria-live="polite" aria-label="Pemberitahuan pengumpulan data" className="fixed inset-x-0 bottom-0 z-[9000] p-3 sm:p-4">
      <div className="mx-auto max-w-3xl rounded-2xl bg-white shadow-2xl border border-zinc-200 p-4 sm:p-5 text-zinc-800">
        <p className="text-sm font-bold">AgriFlow mencatat cara Anda memakai dashboard ini.</p>
        <p className="mt-1.5 text-xs leading-relaxed text-zinc-600">
          Yang dicatat: halaman dan fitur yang dibuka, serta komoditas dan wilayah yang dipilih. Tidak ada isi pesan,
          nama, nomor telepon, atau alamat email. Tujuannya dua: memperbaiki layanan, dan menyusun laporan agregat
          sinyal permintaan pangan untuk instansi pemerintah dan lembaga. Laporan itu hanya berisi angka gabungan;
          sel dengan kurang dari 5 pengguna unik tidak pernah ditampilkan. Data tidak bisa ditautkan lintas hari.
          Anda dapat menarik persetujuan kapan saja lewat halaman{" "}
          <Link href="/privasi" className="text-[#5b7245] font-semibold underline">Privasi</Link>, dan penarikan berlaku seketika.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button onClick={accept} className="px-4 py-2 rounded-xl text-xs font-bold bg-[#5b7245] text-white hover:bg-[#4f643c]">Setuju</button>
          <button onClick={decline} className="px-4 py-2 rounded-xl text-xs font-bold bg-zinc-100 text-zinc-800 hover:bg-zinc-200">Tolak</button>
        </div>
      </div>
    </div>
  );
}
