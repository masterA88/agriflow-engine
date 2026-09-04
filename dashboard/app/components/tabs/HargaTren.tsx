"use client";

import { useMemo, useState } from "react";
import { useAnalysis } from "../../hooks/useDashboardData";
import type { Commodity, Kabupaten, Meta } from "../../lib/api";
import { fmtDate } from "../../lib/format";
import AnomalyPanel from "../AnomalyPanel";
import ForecastPanel from "../ForecastPanel";

// Forecasts and daily prices exist for all 38 kabupaten/kota (SISKAPERBAPO + PIHPS fallback).
// This list enumerates the supported commodities, not the regions — regions come from the `kabupaten` prop.
const FORECAST_COMMODITIES = ["bawang_merah", "bawang_putih", "beras_medium", "beras_premium", "cabai_rawit", "daging_ayam", "telur_ayam"];
const FORECAST_LABEL: Record<string, string> = {
  daging_ayam: "Daging Ayam (harga saja)", telur_ayam: "Telur Ayam (harga saja)",
};

export default function HargaTren({
  commodity, commodities, kabupaten, meta, initialCity,
}: {
  commodity: string;
  commodities: Commodity[];
  kabupaten: Kabupaten[];
  meta: Meta | null;
  initialCity?: string | null;
}) {
  const cities = useMemo(() => kabupaten, [kabupaten]);
  // Local picks are remembered together with the props they were made under,
  // so a new commodity or a notification click resets them without an effect.
  const [cityPick, setCityPick] = useState<{ under: string | null; id: string } | null>(null);
  const [codePick, setCodePick] = useState<{ under: string; code: string } | null>(null);
  const defaultCity = initialCity && cities.some((c) => c.id === initialCity) ? initialCity : "3578";
  const city = cityPick && cityPick.under === initialCity ? cityPick.id : defaultCity;
  const defaultCode = FORECAST_COMMODITIES.includes(commodity) ? commodity : "bawang_merah";
  const code = codePick && codePick.under === commodity ? codePick.code : defaultCode;
  const setCity = (id: string) => setCityPick({ under: initialCity ?? null, id });
  const setCode = (c: string) => setCodePick({ under: commodity, code: c });

  const a = useAnalysis(code, city);
  const cityName = cities.find((c) => c.id === city)?.nama ?? city;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-3">
        <div>
          <h2 className="text-lg sm:text-xl font-bold text-white tracking-tight">Harga &amp; prakiraan: {cityName}</h2>
          <p className="text-xs text-emerald-100/80 mt-0.5">Harga harian 38 kabupaten/kota (SISKAPERBAPO + PIHPS), prakiraan 30 hari dengan pita 80% terkalibrasi, dan anomali dari scanner Hampel/MAD.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <label className="bg-white rounded-full px-3 py-1.5 shadow-sm flex items-center gap-2 text-[10px] font-bold text-zinc-400 uppercase">
            Komoditas
            <select className="text-xs bg-white text-[#5b7245] font-extrabold focus:outline-none normal-case" value={code} onChange={(e) => setCode(e.target.value)}>
              {FORECAST_COMMODITIES.map((c) => (
                <option key={c} value={c}>{FORECAST_LABEL[c] ?? commodities.find((x) => x.code === c)?.nama ?? c}</option>
              ))}
            </select>
          </label>
          <label className="bg-white rounded-full px-3 py-1.5 shadow-sm flex items-center gap-2 text-[10px] font-bold text-zinc-400 uppercase">
            Kabupaten/Kota
            <select className="text-xs bg-white text-[#5b7245] font-extrabold focus:outline-none normal-case" value={city} onChange={(e) => setCity(e.target.value)}>
              {cities.map((c) => <option key={c.id} value={c.id}>{c.nama}</option>)}
            </select>
          </label>
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-sm overflow-hidden">
        <ForecastPanel forecast={a.forecast} history={a.history} loading={a.loading} error={a.error} />
      </div>

      <div className="bg-white rounded-2xl shadow-sm overflow-hidden">
        <AnomalyPanel anomalies={a.anomalies} loading={a.loading} error={a.error} totalCount={a.anomalyTotal} />
      </div>

      <p className="text-[11px] text-emerald-100/80">
        Scan anomali {fmtDate(meta?.data_as_of.anomaly_scan_generated_at)} · prakiraan dibuat {fmtDate(meta?.data_as_of.forecast_generated_at)} · metode interval: {meta?.data_as_of.forecast_interval_methods.join(", ") ?? "..."}. Harga harian dari SISKAPERBAPO (semua 38 kabupaten/kota) dengan PIHPS sebagai fallback.
      </p>
    </div>
  );
}
