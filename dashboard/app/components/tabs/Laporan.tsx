"use client";

import { api, type Commodity, type Meta, type Summary } from "../../lib/api";
import { fmtDate, fmtDateTime, fmtIdr, fmtPct, fmtTon } from "../../lib/format";
import { Icons } from "../Icons";
import KpiCard from "../KpiCard";
import { track } from "../../lib/telemetry";

export default function Laporan({ summary, meta, commodities }: { summary: Summary | null; meta: Meta | null; commodities: Commodity[] }) {
  const t = summary?.totals;
  const name = (code: string) => commodities.find((c) => c.code === code)?.nama ?? code;
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg sm:text-xl font-bold text-white tracking-tight">Laporan &amp; KPI</h2>
        <p className="text-xs text-emerald-100/80 mt-0.5">Semua angka dihitung dari run engine yang sedang dilayani (<code>/api/v1/summary</code>). Unduhan berisi daftar match yang sama dengan yang tampil di peta.</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard label="Kebutuhan tertutup" value={t ? fmtPct(t.coverage_pct) : "..."} sub={t ? `${fmtTon(t.matched_tons)} dari ${fmtTon(t.deficit_tons)} defisit` : undefined} tone="good" />
        <KpiCard label="Jumlah match" value={t ? String(t.n_matches) : "..."} sub={meta ? `${meta.engine_run.candidate_pairs_evaluated} pasangan kandidat dievaluasi` : undefined} />
        <KpiCard label="Potensi selisih nilai" value={t ? fmtIdr(t.gross_arbitrage_idr, { compact: true }) : "..."} sub="harga tujuan dikurangi asal × volume; bukan realisasi" tone="info" />
        <KpiCard label="Welfare vs greedy" value={meta?.engine_run.welfare_gain_pct !== null && meta?.engine_run.welfare_gain_pct !== undefined ? `+${meta.engine_run.welfare_gain_pct.toFixed(1)}%` : "n/a"} sub={meta ? `allocator ${meta.allocator}, ${meta.engine_run.latency_ms?.toFixed(0)} ms` : undefined} tone="warn" />
      </div>

      <div className="bg-white rounded-2xl shadow-sm overflow-hidden">
        <div className="px-4 py-3 border-b border-zinc-100 flex items-center justify-between">
          <span className="text-sm font-bold text-zinc-800">Neraca per komoditas</span>
          <a href={api.reportCsvUrl()} onClick={() => track("download", { detail: { kind: "report_csv_all" } })} download className="text-xs font-bold text-white bg-[#5b7245] hover:bg-[#4f643c] px-3 py-1.5 rounded-lg flex items-center gap-1.5"><Icons.Download className="w-3.5 h-3.5" /> Semua match (CSV)</a>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-zinc-400 bg-zinc-50/60">
                <th className="text-left px-4 py-2">Komoditas</th>
                <th className="text-right px-3 py-2">Surplus</th>
                <th className="text-right px-3 py-2">Defisit</th>
                <th className="text-right px-3 py-2">Tercocokkan</th>
                <th className="text-right px-3 py-2">Tertutup</th>
                <th className="text-right px-3 py-2">Match</th>
                <th className="text-right px-3 py-2">IPM&lt;68 terpenuhi</th>
                <th className="text-left px-3 py-2">Belum terpasok</th>
                <th className="text-right px-4 py-2">Unduh</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {summary ? Object.entries(summary.per_commodity).map(([code, s]) => (
                <tr key={code} className="hover:bg-zinc-50/60">
                  <td className="px-4 py-2.5 font-bold text-zinc-800 whitespace-nowrap">{name(code)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{fmtTon(s.surplus_tons)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{fmtTon(s.deficit_tons)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{fmtTon(s.matched_tons)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums font-semibold">{fmtPct(s.coverage_pct, 0)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{s.n_matches}{s.equity_boosted_matches ? <span className="text-[9px] text-[#b33c3c] ml-1">({s.equity_boosted_matches} equity)</span> : null}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{fmtPct(s.low_ipm_deficit_fulfillment_pct, 0)}</td>
                  <td className="px-3 py-2.5 text-zinc-500 max-w-[220px] truncate" title={s.unmatched_deficit_kab.join(", ")}>{s.unmatched_deficit_kab.length ? s.unmatched_deficit_kab.join(", ") : "semua terpasok"}</td>
                  <td className="px-4 py-2.5 text-right"><a href={api.reportCsvUrl(code)} onClick={() => track("download", { commodity: code, detail: { kind: "report_csv" } })} download className="text-[10px] font-bold text-[#5b7245] hover:underline">CSV</a></td>
                </tr>
              )) : (
                <tr><td colSpan={9} className="px-4 py-6 text-center text-zinc-400">Memuat...</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="bg-white rounded-2xl p-4 shadow-sm text-xs space-y-1.5">
          <span className="text-sm font-bold text-zinc-800 block mb-1">Data per</span>
          <Row k="Harga harian (Siskaperbapo + PIHPS)" v={`s.d. ${fmtDate(meta?.data_as_of.price_history_end)}`} />
          <Row k="Neraca BPS" v={`tahun ${meta?.data_as_of.bps_reference_year ?? "?"}, IPM ${meta?.data_as_of.ipm_year ?? "?"}`} />
          <Row k="Scan anomali" v={fmtDateTime(meta?.data_as_of.anomaly_scan_generated_at)} />
          <Row k="Prakiraan" v={`${fmtDateTime(meta?.data_as_of.forecast_generated_at)} (${meta?.data_as_of.forecast_interval_methods.join(", ") ?? ""})`} />
          <Row k="Jarak jalan" v={meta?.data_as_of.road_distance ?? "?"} />
          <Row k="Engine" v={`v${meta?.engine_version ?? "?"}${meta?.git_commit ? ` (${meta.git_commit})` : ""}, allocator ${meta?.allocator}, gerbang anomali ${meta?.anomaly_gate} (${meta?.anomaly_gate_active_pairs ?? 0} pasangan aktif)`} />
        </div>
        <div className="bg-white rounded-2xl p-4 shadow-sm text-xs space-y-2">
          <span className="text-sm font-bold text-zinc-800 block mb-1">Akses mesin ke mesin</span>
          <p className="text-zinc-600 leading-relaxed">Setiap panel punya endpoint JSON publik untuk TPID, Bappeda, atau peneliti:</p>
          <ul className="font-mono text-[10px] text-zinc-700 space-y-0.5">
            {["/api/v1/summary", "/api/v1/matches?commodity=", "/api/v1/matches/explain?deficit_kab_id=&commodity=", "/api/v1/surplus-deficit?commodity=", "/api/v1/forecast?commodity=&city=", "/api/v1/price-history?commodity=&city=", "/api/v1/anomalies", "/api/v1/meta", "POST /api/v1/simulate"].map((p) => <li key={p}>{p}</li>)}
          </ul>
          <p className="text-[10px] text-zinc-400 leading-relaxed">Laporan PDF berformat resmi belum tersedia; yang ada adalah CSV dan JSON dari data yang sama. Kami tidak menampilkan angka realisasi penyaluran karena AgriFlow belum menjalankan distribusi fisik.</p>
        </div>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return <div className="flex gap-2"><span className="w-28 shrink-0 text-zinc-400">{k}</span><span className="text-zinc-700">{v}</span></div>;
}
