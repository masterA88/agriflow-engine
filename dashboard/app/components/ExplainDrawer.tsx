"use client";

import { useEffect, useState } from "react";
import { api, type ExplainResponse, type Match } from "../lib/api";
import { fmtIdr, fmtTon, shortKab } from "../lib/format";
import { Icons } from "./Icons";
import { track } from "../lib/telemetry";

type Loaded = { key: string; data: ExplainResponse | null; error: string | null };

function keyOf(m: Match | null): string {
  return m ? `${m.deficit.kab_id}|${m.commodity_code}` : "";
}

export default function ExplainDrawer({ match, onClose }: { match: Match | null; onClose: () => void }) {
  const [loaded, setLoaded] = useState<Loaded>({ key: "", data: null, error: null });
  const key = keyOf(match);
  const ready = loaded.key === key;
  const data = ready ? loaded.data : null;
  const error = ready ? loaded.error : null;

  useEffect(() => {
    if (!match) return;
    const k = keyOf(match);
    let active = true;
    api.explain({ deficit_kab_id: match.deficit.kab_id, commodity: match.commodity_code, limit: 8 })
      .then((d) => { if (!active) return; setLoaded({ key: k, data: d, error: null }); track("explain_view", { commodity: match.commodity_code, kabupaten_id: match.deficit.kab_id, detail: { deficit_kab_id: match.deficit.kab_id } }); })
      .catch((e: Error) => active && setLoaded({ key: k, data: null, error: e.message }));
    return () => { active = false; };
  }, [match]);

  if (!match) return null;

  return (
    <div className="fixed inset-0 z-[10001] flex justify-end">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div className="relative w-full sm:w-[520px] h-full bg-white shadow-2xl overflow-y-auto p-5 flex flex-col gap-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider">Semua pemasok layak untuk</span>
            <h3 className="text-base font-extrabold text-zinc-900">{shortKab(match.deficit.kab_nama)} · {match.commodity_nama}</h3>
            {data && (
              <p className="text-[11px] text-zinc-500 mt-0.5">
                Kebutuhan {fmtTon(data.deficit.volume_tons)} · IPM {data.deficit.ipm.toFixed(1)} · harga tujuan {fmtIdr(data.deficit.price_per_kg)}/kg · {data.n_viable_suppliers} pemasok lolos hard constraint
              </p>
            )}
          </div>
          <button onClick={onClose} className="text-zinc-400 hover:text-zinc-700" aria-label="Tutup"><Icons.X className="w-5 h-5" /></button>
        </div>

        {error && <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-3">{error}</div>}
        {!ready && <div className="text-xs text-zinc-400 animate-pulse">Menghitung ulang skor semua pemasok...</div>}

        {data && (
          <>
            <div className="text-[11px] text-zinc-600 bg-zinc-50 rounded-lg p-3 leading-relaxed">
              Bobot yang dipakai: {Object.entries(data.weights_used).map(([k, v]) => `${k} ${(v * 100).toFixed(0)}%`).join(" · ")}.
              {" "}Allocator: <strong>{data.allocator}</strong>. {data.reason_not_chosen}
            </div>
            <ol className="space-y-2">
              {data.ranking.map((r, i) => (
                <li key={r.surplus_kab_id} className={`rounded-xl border p-3 ${r.chosen ? "border-[#5b7245] bg-[#f4f7f2]" : "border-zinc-100 bg-white"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-bold text-zinc-900">
                      <span className="text-zinc-400 mr-1">#{i + 1}</span>{shortKab(r.surplus_kab)}
                      {r.chosen && <span className="ml-2 text-[9px] font-extrabold px-1.5 py-0.5 rounded bg-[#5b7245] text-white">DIPILIH · {fmtTon(r.allocated_tons)}</span>}
                    </span>
                    <span className="text-xs font-extrabold tabular-nums text-zinc-800">{r.final_score.toFixed(1)}</span>
                  </div>
                  <div className="text-[10px] text-zinc-500 mt-0.5">
                    {r.distance_km.toFixed(0)} km · tersedia {fmtTon(r.available_tons)} · base {r.base_score.toFixed(1)} × equity {r.equity_multiplier.toFixed(2)}
                  </div>
                  <div className="grid grid-cols-5 gap-1 mt-1.5">
                    {(["distance", "volume", "price", "perishability", "climate"] as const).map((k) => (
                      <div key={k} className="text-center">
                        <div className="h-1 bg-zinc-100 rounded overflow-hidden"><div className="h-full bg-[#5b7245]" style={{ width: `${Math.round(r.breakdown[k] * 100)}%` }} /></div>
                        <span className="text-[8px] text-zinc-400">{k === "perishability" ? "simpan" : k === "distance" ? "jarak" : k === "volume" ? "volume" : k === "price" ? "harga" : "iklim"}</span>
                      </div>
                    ))}
                  </div>
                </li>
              ))}
            </ol>
          </>
        )}
      </div>
    </div>
  );
}
