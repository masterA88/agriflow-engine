"use client";

import dynamic from "next/dynamic";
import type { Commodity, Kabupaten, Match, Meta, Summary, SurplusDeficitResponse } from "../../lib/api";
import { fmtDate, fmtIdr, fmtPct, fmtTon } from "../../lib/format";
import DataStatus from "../DataStatus";
import { Icons } from "../Icons";
import KpiCard from "../KpiCard";
import MatchCard from "../MatchCard";
import type { TabKey } from "../Sidebar";

const MapView = dynamic(() => import("../MapView"), { ssr: false });

export default function Beranda({
  commodity, commodities, sd, matches, summary, meta, apiError, kabupaten, selectedKabId,
  onSelectKab, onGo, onExplain, loading,
}: {
  commodity: string;
  commodities: Commodity[];
  sd: SurplusDeficitResponse | null;
  matches: Match[];
  summary: Summary | null;
  meta: Meta | null;
  apiError: string | null;
  kabupaten: Kabupaten[];
  selectedKabId: string | null;
  onSelectKab: (id: string | null) => void;
  onGo: (t: TabKey) => void;
  onExplain: (m: Match) => void;
  loading: boolean;
}) {
  const cs = summary?.per_commodity[commodity];
  const rows = sd?.rows ?? [];
  const surplusRows = rows.filter((r) => r.role === "surplus");
  const deficitRows = rows.filter((r) => r.role === "deficit");
  const prices = rows.map((r) => r.price_per_kg);
  const maxP = prices.length ? Math.max(...prices) : null;
  const minP = prices.length ? Math.min(...prices) : null;
  const maxKab = rows.find((r) => r.price_per_kg === maxP)?.kab_nama;
  const minKab = rows.find((r) => r.price_per_kg === minP)?.kab_nama;
  const name = commodities.find((c) => c.code === commodity)?.nama ?? commodity;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-2">
        <div>
          <h2 className="text-lg sm:text-xl font-bold text-white tracking-tight">Neraca pangan Jawa Timur: {name}</h2>
          <p className="text-xs text-emerald-100/80 mt-0.5">38 kabupaten/kota, neraca produksi dikurangi konsumsi (BPS {summary?.data_as_of.bps_reference_year ?? "2022"}), harga median Siskaperbapo dan PIHPS.</p>
        </div>
        <div className="hidden lg:block"><DataStatus meta={meta} error={apiError} /></div>
      </div>

      {apiError && (
        <div className="bg-white rounded-2xl p-4 text-xs text-rose-700 border border-rose-200 flex items-start gap-2">
          <Icons.AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <span><strong>API tidak terjangkau.</strong> {apiError}. Tidak ada data tiruan yang ditampilkan; muat ulang setelah API bangun (Hugging Face Space bisa tidur beberapa detik).</span>
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-tour="kpi">
        <KpiCard icon={<Icons.Truck className="w-5 h-5" />} label="Surplus siap kirim" value={cs ? fmtTon(cs.surplus_tons) : loading ? "..." : "n/a"} sub={cs ? `${cs.n_surplus_kab} kabupaten` : undefined} />
        <KpiCard icon={<Icons.ShoppingCart className="w-5 h-5" />} label="Defisit" value={cs ? fmtTon(cs.deficit_tons) : loading ? "..." : "n/a"} sub={cs ? `${cs.n_deficit_kab} kabupaten` : undefined} />
        <KpiCard icon={<Icons.Scale className="w-5 h-5" />} label="Kebutuhan tertutup" value={cs ? fmtPct(cs.coverage_pct, 1) : loading ? "..." : "n/a"} sub={cs ? `${cs.n_matches} match, ${fmtTon(cs.matched_tons)}` : undefined} tone={cs && (cs.coverage_pct ?? 0) >= 90 ? "good" : "warn"} />
        <KpiCard icon={<Icons.TrendingUp className="w-5 h-5" />} label="Potensi selisih nilai" value={cs ? fmtIdr(cs.gross_arbitrage_idr, { compact: true }) : loading ? "..." : "n/a"} sub="harga tujuan dikurangi asal, dikali volume" tone="info" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 flex flex-col gap-4">
          <div className="bg-white rounded-2xl shadow-sm overflow-hidden flex flex-col" data-tour="peta">
            <div className="px-4 py-2.5 border-b border-zinc-100 flex justify-between items-center">
              <span className="text-xs font-bold text-zinc-800">Peta surplus, defisit, dan alur match</span>
              <button onClick={() => onGo("peta")} className="text-xs text-[#5b7245] font-bold flex items-center gap-1"><Icons.Search className="w-3.5 h-3.5" /> Peta penuh</button>
            </div>
            <div className="h-[260px] sm:h-[320px] w-full relative">
              <MapView kabupaten={kabupaten} surplusDeficit={rows} matches={matches} onSelectKab={(id) => onSelectKab(id)} selectedKabId={selectedKabId} />
              <div className="absolute bottom-3 left-3 bg-white/95 rounded-xl p-2.5 text-[10px] shadow-lg space-y-1 z-[1000] leading-none">
                <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-emerald-600 inline-block" /> Surplus ({surplusRows.length})</div>
                <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full bg-rose-600 inline-block" /> Defisit ({deficitRows.length})</div>
                <div className="flex items-center gap-2"><span className="w-4 border-t-2 border-dashed border-[#4e643c] inline-block" /> match teratas</div>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl p-4 shadow-sm flex flex-col gap-3">
            <div className="flex justify-between items-center">
              <span className="text-xs font-bold text-zinc-800">Harga median {name}</span>
              <span className="text-[10px] text-zinc-400">harga harian s.d. {fmtDate(meta?.data_as_of.price_history_end)}</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-[#f4f7f2] border border-[#e4ebd3] p-3 rounded-xl">
                <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider block">Termahal (sisi defisit)</span>
                <strong className="text-base font-extrabold text-zinc-800 block">{maxP !== null ? fmtIdr(maxP) + "/kg" : "n/a"}</strong>
                <span className="text-[10px] text-rose-700 font-semibold">{maxKab ?? ""}</span>
              </div>
              <div className="bg-[#f4f7f2] border border-[#e4ebd3] p-3 rounded-xl">
                <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider block">Termurah (sisi surplus)</span>
                <strong className="text-base font-extrabold text-zinc-800 block">{minP !== null ? fmtIdr(minP) + "/kg" : "n/a"}</strong>
                <span className="text-[10px] text-emerald-700 font-semibold">{minKab ?? ""}</span>
              </div>
            </div>
            <p className="text-[10px] text-zinc-500 leading-snug">
              Harga sisi surplus adalah harga produsen, sisi defisit harga konsumen median 2022; selisihnya yang dinilai dimensi harga di skor match. Grafik harian per kota ada di tab Harga &amp; Prakiraan.
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-3" data-tour="rekomendasi">
          <div className="flex justify-between items-center px-1">
            <span className="text-xs font-bold text-white">Rekomendasi teratas engine</span>
            <button onClick={() => onGo("distribusi")} className="text-[11px] text-emerald-100 font-bold hover:underline">Semua ({matches.length})</button>
          </div>
          {loading && matches.length === 0 && <div className="bg-white rounded-2xl p-4 text-xs text-zinc-400 animate-pulse">Menjalankan engine...</div>}
          {!loading && matches.length === 0 && (
            <div className="bg-white rounded-2xl p-4 text-xs text-zinc-600">
              Tidak ada match untuk {name}{selectedKabId ? " di kabupaten terpilih" : ""}. {cs && cs.n_matches === 0 && cs.n_deficit_kab > 0 ? "Semua kabupaten defisit dan tidak ada surplus domestik; engine menyarankan jalur impor." : ""}
            </div>
          )}
          {matches.slice(0, 3).map((m) => (
            <MatchCard key={`${m.surplus.kab_id}-${m.deficit.kab_id}`} m={m} compact onExplain={onExplain} onFocus={(mm) => onSelectKab(mm.deficit.kab_id)} />
          ))}
          {summary && (
            <div className="bg-white rounded-2xl p-3 shadow-sm">
              <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-wider block mb-1.5">Kebutuhan tertutup per komoditas</span>
              <ul className="space-y-1">
                {Object.entries(summary.per_commodity).map(([code, s]) => (
                  <li key={code} className="flex items-center gap-2 text-[11px]">
                    <span className="w-24 truncate text-zinc-600">{commodities.find((c) => c.code === code)?.nama ?? code}</span>
                    <span className="flex-1 h-1.5 bg-zinc-100 rounded overflow-hidden"><span className={`block h-full ${(s.coverage_pct ?? 0) >= 90 ? "bg-emerald-600" : (s.coverage_pct ?? 0) > 0 ? "bg-amber-500" : "bg-rose-500"}`} style={{ width: `${Math.round(s.coverage_pct ?? 0)}%` }} /></span>
                    <span className="w-12 text-right tabular-nums font-semibold text-zinc-800">{fmtPct(s.coverage_pct, 0)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
