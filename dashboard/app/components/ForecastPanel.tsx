"use client";

/**
 * ForecastPanel: 90 days of observed prices and the 30-day forecast on one
 * axis, with the P10 to P90 band. The interval label comes from the API
 * (split conformal since v1.1) and the point method is always shown.
 */

import { useMemo } from "react";
import type { ForecastResponse, PriceHistoryResponse } from "../lib/api";
import { fmtDate, fmtIdr } from "../lib/format";

const W = 640, H = 200, PL = 56, PR = 12, PT = 14, PB = 28;

function Chart({ history, forecast }: { history: PriceHistoryResponse | null; forecast: ForecastResponse }) {
  const model = useMemo(() => {
    const hist = history?.points ?? [];
    const fc = forecast.forecasts;
    const n = hist.length + fc.length;
    const vals = [...hist.map((p) => p.price), ...fc.flatMap((p) => [p.p10, p.p90, p.point])];
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const pad = (hi - lo) * 0.12 || 1000;
    lo -= pad; hi += pad;
    const plotW = W - PL - PR, plotH = H - PT - PB;
    const x = (i: number) => PL + (n <= 1 ? 0 : (i / (n - 1)) * plotW);
    const y = (v: number) => PT + plotH - ((v - lo) / (hi - lo)) * plotH;
    const histPath = hist.length ? "M " + hist.map((p, i) => `${x(i)},${y(p.price)}`).join(" L ") : "";
    const off = hist.length;
    const fcPath = "M " + fc.map((p, i) => `${x(off + i)},${y(p.point)}`).join(" L ");
    const band = `M ${fc.map((p, i) => `${x(off + i)},${y(p.p90)}`).join(" L ")} L ${[...fc].reverse().map((p, i) => `${x(off + fc.length - 1 - i)},${y(p.p10)}`).join(" L ")} Z`;
    const splitX = hist.length ? x(off - 1) : x(0);
    const ticks: { x: number; label: string }[] = [];
    const all = [...hist.map((p) => p.date), ...fc.map((p) => p.date)];
    const step = Math.max(1, Math.round(n / 6));
    for (let i = 0; i < n; i += step) ticks.push({ x: x(i), label: fmtDate(all[i], false) });
    const yt = [0.1, 0.5, 0.9].map((f) => ({ y: y(lo + (hi - lo) * f), label: fmtIdr(lo + (hi - lo) * f, { compact: true }) }));
    return { histPath, fcPath, band, splitX, ticks, yt, lo, hi };
  }, [history, forecast]);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Harga observasi dan prakiraan 30 hari">
      {model.yt.map((t, i) => (
        <g key={i}>
          <line x1={PL} y1={t.y} x2={W - PR} y2={t.y} stroke="#e4e4e7" strokeWidth={1} />
          <text x={PL - 4} y={t.y + 3} textAnchor="end" fontSize={9} fill="#71717a">{t.label}</text>
        </g>
      ))}
      <path d={model.band} fill="#5b7245" fillOpacity={0.16} />
      {model.histPath && <path d={model.histPath} fill="none" stroke="#27272a" strokeWidth={1.6} strokeLinejoin="round" />}
      <path d={model.fcPath} fill="none" stroke="#5b7245" strokeWidth={2.2} strokeLinejoin="round" />
      <line x1={model.splitX} y1={PT} x2={model.splitX} y2={H - PB} stroke="#a1a1aa" strokeDasharray="3 3" />
      <text x={model.splitX + 3} y={PT + 9} fontSize={8} fill="#71717a">prakiraan →</text>
      {model.ticks.map((t) => (
        <text key={t.x} x={t.x} y={H - PB + 13} textAnchor="middle" fontSize={9} fill="#71717a">{t.label}</text>
      ))}
      <line x1={PL} y1={H - PB} x2={W - PR} y2={H - PB} stroke="#d4d4d8" />
    </svg>
  );
}

export default function ForecastPanel({ forecast, history, loading, error }: {
  forecast: ForecastResponse | null; history: PriceHistoryResponse | null; loading: boolean; error: string | null;
}) {
  if (error) return <div className="rounded-lg p-3 bg-rose-50 text-xs text-rose-700 border border-rose-200">{error}</div>;
  if (loading) return <div className="rounded-lg p-3 text-xs text-zinc-400 animate-pulse">Memuat prakiraan...</div>;
  if (!forecast) return <div className="rounded-lg p-3 text-xs text-zinc-500">Belum ada prakiraan untuk pasangan komoditas dan kota ini. Prakiraan tersedia untuk 38 kabupaten/kota.</div>;

  const isBaseline = forecast.method === "seasonal_naive_baseline";
  const conformal = forecast.interval_method === "split_conformal_rolling_origin";
  const first = forecast.forecasts[0];
  const last = forecast.forecasts[forecast.forecasts.length - 1];
  const lastObs = history?.points[history.points.length - 1];

  return (
    <div className="flex flex-col">
      <div className="px-3 py-2 border-b border-zinc-100 flex items-center justify-between gap-2 flex-wrap">
        <div>
          <span className="text-xs font-semibold text-zinc-800">Harga {forecast.city_name}: 90 hari observasi + 30 hari prakiraan</span>
          <span className="ml-2 text-[10px] text-zinc-400">observasi s.d. {fmtDate(forecast.history_end_date)}</span>
        </div>
        <div className="flex gap-1.5">
          <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${isBaseline ? "bg-amber-100 text-amber-800" : "bg-indigo-100 text-indigo-800"}`}>
            {isBaseline ? "seasonal-naive baseline" : forecast.method}
          </span>
          {conformal && <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-emerald-100 text-emerald-800">pita 80% terkalibrasi (conformal)</span>}
        </div>
      </div>
      <div className="px-2 pt-1"><Chart history={history} forecast={forecast} /></div>
      <div className="px-3 py-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] border-t border-zinc-100">
        {lastObs && <span className="text-zinc-500">Observasi terakhir: <b className="text-zinc-800">{fmtIdr(lastObs.price)}/kg</b></span>}
        <span className="text-zinc-500">Hari 1 ({fmtDate(first.date, false)}): <b className="text-zinc-800">{fmtIdr(first.point)}/kg</b></span>
        <span className="text-zinc-500">Hari 30 ({fmtDate(last.date, false)}): <b className="text-zinc-800">{fmtIdr(last.point)}/kg</b></span>
        <span className="text-zinc-400">Rentang hari 30: {fmtIdr(last.p10)} sampai {fmtIdr(last.p90)}</span>
      </div>
      <div className="px-3 pb-2 flex flex-wrap gap-3 text-[10px] text-zinc-500">
        <span className="flex items-center gap-1"><span className="w-4 h-0.5 bg-zinc-800 inline-block" /> observasi harga aktif (SISKAPERBAPO + PIHPS)</span>
        <span className="flex items-center gap-1"><span className="w-4 h-0.5 bg-[#5b7245] inline-block" /> prakiraan titik</span>
        <span className="flex items-center gap-1"><span className="w-4 h-3 bg-[#5b7245]/20 inline-block rounded-sm" /> P10 sampai P90</span>
        {isBaseline && <span className="text-amber-700">Median bulan-yang-sama, bukan foundation model. MAPE backtest 10,8%.</span>}
        {conformal && forecast.calibration_residuals ? <span>Kalibrasi pada {forecast.calibration_residuals} residual rolling-origin.</span> : null}
      </div>
    </div>
  );
}
