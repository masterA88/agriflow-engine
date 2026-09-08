"use client";

// Insight Permintaan: the sellable product, shown as the dashboard sees it.
// Every number here comes from GET /api/v1/insight/demand, which reads only
// the SQL view demand_signal_export (web channel, cells with 5 or more
// unique users). WhatsApp-derived rows cannot reach this page by construction.

import { useEffect, useMemo, useState } from "react";
import { api, type Commodity, type DemandSignalRow, type Kabupaten } from "../../lib/api";
import { track } from "../../lib/telemetry";
import { Icons } from "../Icons";

const SAMPLE_PDF = "/insight/contoh-laporan-sinyal-permintaan.pdf";
const DAYS = 30;

export default function InsightPermintaan({ commodities, kabupaten }: { commodities: Commodity[]; kabupaten: Kabupaten[] }) {
  const [rows, setRows] = useState<DemandSignalRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api.insightDemand({ days: DAYS })
      .then((r) => { if (active) { setRows(r.rows); setError(null); } })
      .catch((e: Error) => { if (active) { setRows([]); setError(e.message); } });
    return () => { active = false; };
  }, []);

  const name = (code: string) => commodities.find((c) => c.code === code)?.nama ?? code;
  const kabName = (id: string) => kabupaten.find((k) => k.id === id)?.nama ?? id;

  const byCommodity = useMemo(() => {
    const m = new Map<string, { users: number; events: number; days: Set<string> }>();
    for (const r of rows ?? []) {
      if (!r.commodity) continue;
      const cur = m.get(r.commodity) ?? { users: 0, events: 0, days: new Set<string>() };
      cur.users += r.unique_users; cur.events += r.event_count; cur.days.add(r.day);
      m.set(r.commodity, cur);
    }
    return [...m.entries()].map(([code, v]) => ({ code, users: v.users, events: v.events, days: v.days.size })).sort((a, b) => b.users - a.users);
  }, [rows]);

  const byKab = useMemo(() => {
    const m = new Map<string, { users: number; events: number }>();
    for (const r of rows ?? []) {
      if (!r.kabupaten_id) continue;
      const cur = m.get(r.kabupaten_id) ?? { users: 0, events: 0 };
      cur.users += r.unique_users; cur.events += r.event_count;
      m.set(r.kabupaten_id, cur);
    }
    return [...m.entries()].map(([id, v]) => ({ id, ...v })).sort((a, b) => b.users - a.users).slice(0, 10);
  }, [rows]);

  const byType = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of rows ?? []) m.set(r.event_type, (m.get(r.event_type) ?? 0) + r.event_count);
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [rows]);

  const maxUsers = Math.max(1, ...byCommodity.map((c) => c.users));
  const empty = rows !== null && rows.length === 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-3">
        <div>
          <h2 className="text-lg sm:text-xl font-bold text-white tracking-tight">Insight Permintaan</h2>
          <p className="text-xs text-emerald-100/80 mt-0.5">
            Sinyal permintaan pangan dari interaksi dashboard, {DAYS} hari terakhir. Produk data yang dijual AgriFlow kepada instansi dan lembaga.
          </p>
        </div>
        <a
          href={SAMPLE_PDF}
          download
          onClick={() => track("download", { detail: { kind: "insight_sample_pdf" } })}
          className="bg-white text-[#5b7245] px-3 py-2 rounded-xl text-xs font-bold shadow-sm flex items-center gap-1.5 hover:bg-zinc-50"
        >
          <Icons.Download className="w-3.5 h-3.5" /> Unduh contoh laporan (PDF)
        </a>
      </div>

      <div className="bg-[#e2edd8] text-[#3f5330] rounded-2xl px-4 py-3 text-xs leading-relaxed">
        <strong>Sumber:</strong> interaksi web first-party yang disetujui pengguna, neraca surplus-defisit BPS 2022, dan keluaran engine AgriFlow.
        Sel dengan kurang dari 5 pengguna unik per hari disuppress di basis data. Percakapan WhatsApp tidak pernah masuk ke laporan ini.
      </div>

      {error && (
        <div className="bg-rose-50 border border-rose-200 text-rose-700 rounded-2xl px-4 py-3 text-xs">
          Insight belum bisa dimuat: {error}
        </div>
      )}

      {empty && !error && (
        <div className="bg-white rounded-2xl p-8 text-center text-zinc-500 text-xs">
          Sinyal permintaan mulai terbentuk setelah 5 pengguna unik per sel. Data akan muncul seiring pemakaian.
        </div>
      )}

      {rows === null && !error && <div className="bg-white rounded-2xl p-6 text-xs text-zinc-400 animate-pulse">Memuat insight...</div>}

      {rows && rows.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-white rounded-2xl shadow-sm p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-bold text-zinc-800">Perhatian per komoditas</span>
              <span className="text-[10px] text-zinc-400">pengguna unik (jumlah harian), {DAYS} hari</span>
            </div>
            <div className="space-y-2">
              {byCommodity.map((c) => (
                <div key={c.code}>
                  <div className="flex justify-between text-xs mb-0.5">
                    <span className="font-semibold text-zinc-800">{name(c.code)}</span>
                    <span className="text-zinc-500">{c.users} pengguna · {c.events} interaksi · {c.days} hari</span>
                  </div>
                  <div className="h-2 rounded-full bg-zinc-100 overflow-hidden">
                    <div className="h-full bg-[#5b7245] rounded-full" style={{ width: `${Math.round((c.users / maxUsers) * 100)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-2xl shadow-sm p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-bold text-zinc-800">Perhatian per kabupaten/kota</span>
              <span className="text-[10px] text-zinc-400">sel yang lolos ambang 5 pengguna</span>
            </div>
            {byKab.length === 0 ? (
              <p className="text-xs text-zinc-500 leading-relaxed">
                Belum ada sel kabupaten yang mencapai 5 pengguna unik dalam satu hari. Pada lalu lintas awal, sinyal per kabupaten
                baru terbaca pada agregasi mingguan; laporan PDF memakai grain itu.
              </p>
            ) : (
              <table className="w-full text-xs">
                <thead className="text-[10px] uppercase text-zinc-400"><tr><th className="text-left py-1">Wilayah</th><th className="text-right py-1">Pengguna</th><th className="text-right py-1">Interaksi</th></tr></thead>
                <tbody>
                  {byKab.map((k) => (
                    <tr key={k.id} className="border-t border-zinc-100">
                      <td className="py-1.5 font-semibold text-zinc-800">{kabName(k.id)}</td>
                      <td className="py-1.5 text-right text-zinc-700">{k.users}</td>
                      <td className="py-1.5 text-right text-zinc-500">{k.events}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="bg-white rounded-2xl shadow-sm p-4 lg:col-span-2">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-bold text-zinc-800">Jenis interaksi yang membentuk sinyal</span>
              <span className="text-[10px] text-zinc-400">{rows.length} sel agregat</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {byType.map(([t, n]) => (
                <span key={t} className="bg-[#f1f6ef] border border-[#e4eedf] text-[#4e643c] rounded-full px-3 py-1 text-[11px] font-semibold">{t} · {n}</span>
              ))}
            </div>
            <p className="text-[11px] text-zinc-500 mt-3 leading-relaxed">
              Sinyal ini mengukur perhatian (apa yang dilihat dan diuji orang), bukan niat beli atau jual. Nilainya muncul saat digabung
              dengan neraca BPS dan keluaran engine: di mana orang bertanya, dan apakah pasokan ada di sana.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
