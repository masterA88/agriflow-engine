"use client";

import dynamic from "next/dynamic";
import { useState } from "react";
import { api, type Kabupaten, type Match, type Meta, type SurplusDeficitResponse } from "../../lib/api";
import { fmtTon } from "../../lib/format";
import { Icons } from "../Icons";
import MatchCard from "../MatchCard";
import { track } from "../../lib/telemetry";

const MapView = dynamic(() => import("../MapView"), { ssr: false });

export default function Distribusi({
  commodity, name, sd, matches, meta, kabupaten, selectedKabId, onSelectKab, onExplain, loading, error,
}: {
  commodity: string;
  name: string;
  sd: SurplusDeficitResponse | null;
  matches: Match[];
  meta: Meta | null;
  kabupaten: Kabupaten[];
  selectedKabId: string | null;
  onSelectKab: (id: string | null) => void;
  onExplain: (m: Match) => void;
  loading: boolean;
  error: string | null;
}) {
  const [focus, setFocus] = useState<Match | null>(null);
  const kabName = kabupaten.find((k) => k.id === selectedKabId)?.nama;
  const total = matches.reduce((s, m) => s + m.matched_volume_tons, 0);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-2">
        <div>
          <h2 className="text-lg sm:text-xl font-bold text-white tracking-tight">Rekomendasi distribusi: {name}</h2>
          <p className="text-xs text-emerald-100/80 mt-0.5">
            {matches.length} match, {fmtTon(total)} · allocator {meta?.allocator ?? "..."}{meta?.engine_run.welfare_gain_pct !== null && meta?.engine_run.welfare_gain_pct !== undefined ? `, welfare +${meta.engine_run.welfare_gain_pct.toFixed(1)}% vs greedy` : ""} · diurutkan skor akhir
          </p>
        </div>
        <div className="flex gap-2">
          {selectedKabId && (
            <button onClick={() => onSelectKab(null)} className="bg-white text-[#5b7245] px-3 py-1.5 rounded-xl text-xs font-bold shadow-sm">Filter: {kabName} ✕</button>
          )}
          <a href={api.reportCsvUrl(commodity)} onClick={() => track("download", { commodity, detail: { kind: "report_csv" } })} className="bg-white text-zinc-800 px-3 py-1.5 rounded-xl text-xs font-bold shadow-sm flex items-center gap-1.5" download>
            <Icons.Download className="w-3.5 h-3.5" /> CSV
          </a>
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-sm overflow-hidden h-[300px] sm:h-[360px] relative">
        <MapView kabupaten={kabupaten} surplusDeficit={sd?.rows ?? []} matches={matches} onSelectKab={(id) => onSelectKab(id)} selectedKabId={selectedKabId} flowLimit={30} highlightMatch={focus} />
      </div>

      {error && <div className="bg-white rounded-2xl p-4 text-xs text-rose-700">{error}</div>}
      {loading && matches.length === 0 && <div className="bg-white rounded-2xl p-4 text-xs text-zinc-400 animate-pulse">Menjalankan engine...</div>}
      {!loading && matches.length === 0 && !error && (
        <div className="bg-white rounded-2xl p-6 text-xs text-zinc-600">Tidak ada match yang lolos hard constraint untuk filter ini.</div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {matches.map((m) => (
          <MatchCard
            key={`${m.surplus.kab_id}-${m.deficit.kab_id}-${m.commodity_code}`}
            m={m}
            onExplain={onExplain}
            onFocus={(mm) => setFocus(focus === mm ? null : mm)}
            highlight={focus === m}
          />
        ))}
      </div>
    </div>
  );
}
