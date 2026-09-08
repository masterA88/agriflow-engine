"use client";

import { useConsent, writeConsent, track, flush } from "../lib/telemetry";

export default function ConsentControls() {
  const state = useConsent();

  const label = state === "accepted" ? "Anda saat ini menyetujui pencatatan." : state === "declined" ? "Anda saat ini menolak pencatatan." : "Belum ada pilihan tersimpan di peramban ini.";

  return (
    <div className="mt-10 rounded-2xl border border-zinc-200 bg-white p-4">
      <p className="text-sm font-semibold">{label}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          onClick={() => { writeConsent("accepted"); track("optin", { detail: { decision: "accept", path: "/privasi" } }); flush(false); }}
          className="px-4 py-2 rounded-xl text-xs font-bold bg-[#5b7245] text-white hover:bg-[#4f643c]"
        >
          Setuju
        </button>
        <button
          onClick={() => { flush(true); writeConsent("declined"); }}
          className="px-4 py-2 rounded-xl text-xs font-bold bg-zinc-100 text-zinc-800 hover:bg-zinc-200"
        >
          Tarik persetujuan
        </button>
      </div>
    </div>
  );
}
