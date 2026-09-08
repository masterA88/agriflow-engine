"use client";

// What-if simulator. Toggles map to the engine's own scenario presets; the
// result is a diff against the served baseline, straight from POST /simulate.

import { useEffect, useState } from "react";
import { api, type Match, type SimulateResponse } from "../lib/api";
import { fmtPct, fmtTon, shortKab } from "../lib/format";
import { Icons } from "./Icons";
import { track } from "../lib/telemetry";

const PRESET_ORDER = ["semeru", "banjir_sentra_padi", "banjir_madura", "suramadu_tutup", "ramadan", "bbm_20", "impor"];

export default function SimulatorPanel({
  commodity, onResult,
}: {
  commodity: string;
  onResult?: (matches: Match[] | null, unreachable: string[]) => void;
}) {
  const [presets, setPresets] = useState<Record<string, string>>({});
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [bbm, setBbm] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [res, setRes] = useState<SimulateResponse | null>(null);

  useEffect(() => {
    api.simulatePresets().then(setPresets).catch((e: Error) => setError(e.message));
  }, []);

  function toggle(k: string) {
    setChosen((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  }

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.simulate({ presets: [...chosen], bbm_pct: bbm, commodity, limit: 100 });
      setRes(r);
      onResult?.(r.matches, r.scenario.applied.unreachable_kab);
      track("simulate_run", { commodity, detail: { presets: [...chosen].join(",") || "none", bbm_pct: bbm, n_matches: r.matches.length } });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setChosen(new Set());
    setBbm(0);
    setRes(null);
    onResult?.(null, []);
  }

  const keys = [...PRESET_ORDER.filter((k) => presets[k]), ...Object.keys(presets).filter((k) => !PRESET_ORDER.includes(k))];

  return (
    <div className="bg-white rounded-2xl shadow-sm p-4 flex flex-col gap-3" data-tour="simulasi">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-bold text-zinc-800 flex items-center gap-1.5"><Icons.Sliders className="w-4 h-4 text-[#5b7245]" /> Simulasi what-if</span>
        <span className="text-[10px] text-zinc-400">POST /api/v1/simulate</span>
      </div>
      <p className="text-[11px] text-zinc-500 leading-snug">
        Skenario yang sama dengan yang terkunci di test suite, dijalankan ulang oleh engine terhadap data hari ini. Hasilnya dibandingkan dengan baseline yang sedang dilayani.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
        {keys.map((k) => (
          <label key={k} className={`flex items-start gap-2 text-[11px] rounded-lg px-2.5 py-2 cursor-pointer border ${chosen.has(k) ? "border-[#5b7245] bg-[#f4f7f2]" : "border-zinc-100 hover:bg-zinc-50"}`}>
            <input type="checkbox" checked={chosen.has(k)} onChange={() => toggle(k)} className="mt-0.5 accent-[#5b7245]" />
            <span className="text-zinc-700 leading-snug">{presets[k]}</span>
          </label>
        ))}
      </div>

      <div className="flex items-center gap-3 text-[11px]">
        <label className="text-zinc-600 whitespace-nowrap">BBM naik</label>
        <input type="range" min={0} max={50} step={5} value={bbm} onChange={(e) => setBbm(Number(e.target.value))} className="flex-1 accent-[#5b7245]" />
        <span className="w-10 text-right font-bold tabular-nums">{bbm}%</span>
      </div>

      <div className="flex gap-2">
        <button onClick={run} disabled={busy} className="flex-1 bg-[#5b7245] hover:bg-[#4f643c] disabled:bg-zinc-300 text-white rounded-xl py-2 text-xs font-bold flex items-center justify-center gap-1.5">
          <Icons.Play className="w-3.5 h-3.5" /> {busy ? "Menjalankan engine..." : "Jalankan ulang engine"}
        </button>
        {res && <button onClick={reset} className="px-3 rounded-xl text-xs font-bold text-zinc-600 bg-zinc-100 hover:bg-zinc-200">Reset</button>}
      </div>

      {error && <div className="text-[11px] text-rose-700 bg-rose-50 border border-rose-200 rounded-lg p-2">{error}</div>}

      {res && (
        <div className="border-t border-zinc-100 pt-3 flex flex-col gap-2">
          <div className="text-[10px] text-zinc-500">
            {res.scenario.labels.length ? res.scenario.labels.join(" · ") : "Tanpa preset"}{res.scenario.applied.bbm_pct ? ` · BBM +${res.scenario.applied.bbm_pct}%` : ""}
            {res.scenario.active_event ? ` · event ${res.scenario.active_event}` : ""} · {res.delta.latency_ms?.toFixed(0)} ms
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <Delta label="Tercocokkan" base={fmtTon(res.baseline.matched_tons)} now={fmtTon(res.result.matched_tons)} delta={res.delta.matched_tons} unit=" t" />
            <Delta label="Kebutuhan tertutup" base={fmtPct(res.baseline.coverage_pct)} now={fmtPct(res.result.coverage_pct)} delta={res.delta.coverage_pct} unit=" poin" />
            <Delta label="Jumlah match" base={String(res.baseline.n_matches)} now={String(res.result.n_matches)} delta={res.delta.n_matches} unit="" />
          </div>
          {(res.removed_matches.length > 0 || res.added_matches.length > 0) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
              <ChangeList title={`Dibatalkan (${res.removed_matches.length})`} items={res.removed_matches} tone="rose" />
              <ChangeList title={`Dialihkan / baru (${res.added_matches.length})`} items={res.added_matches} tone="emerald" />
            </div>
          )}
          {res.warnings.length > 0 && (
            <details className="text-[10px] text-zinc-500">
              <summary className="cursor-pointer font-semibold">Peringatan engine ({res.warnings.length})</summary>
              <ul className="list-disc pl-4 mt-1 space-y-0.5">{res.warnings.slice(0, 12).map((w, i) => <li key={i}>{w}</li>)}</ul>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

function Delta({ label, base, now, delta, unit }: { label: string; base: string; now: string; delta: number | null; unit: string }) {
  const d = delta ?? 0;
  const tone = d < 0 ? "text-rose-600" : d > 0 ? "text-emerald-700" : "text-zinc-500";
  return (
    <div className="bg-[#f4f7f2] rounded-lg p-2">
      <span className="text-[9px] font-bold text-zinc-400 uppercase tracking-wider block">{label}</span>
      <span className="text-sm font-extrabold text-zinc-800 block tabular-nums">{now}</span>
      <span className={`text-[10px] font-semibold ${tone}`}>{d > 0 ? "+" : ""}{delta === null ? "n/a" : d.toLocaleString("id-ID", { maximumFractionDigits: 1 })}{unit} vs {base}</span>
    </div>
  );
}

function ChangeList({ title, items, tone }: { title: string; items: Match[]; tone: "rose" | "emerald" }) {
  const cls = tone === "rose" ? "bg-rose-50 text-rose-800" : "bg-emerald-50 text-emerald-800";
  return (
    <div className={`rounded-lg p-2 ${cls}`}>
      <span className="font-bold block mb-1">{title}</span>
      <ul className="space-y-0.5 max-h-32 overflow-y-auto">
        {items.slice(0, 8).map((m, i) => (
          <li key={i} className="truncate">{shortKab(m.surplus.kab_nama)} → {shortKab(m.deficit.kab_nama)} · {fmtTon(m.matched_volume_tons)} {m.commodity_nama}</li>
        ))}
        {items.length > 8 && <li className="opacity-70">+{items.length - 8} lainnya</li>}
      </ul>
    </div>
  );
}
