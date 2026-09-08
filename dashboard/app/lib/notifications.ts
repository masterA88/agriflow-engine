// Notifications are derived from data the API actually served: recent
// scanner anomalies, equity-boosted matches, unmatched deficits, and the
// data-as-of stamps. No hand-written "10 menit lalu" items.

import type { AnomalyRecord, Match, Meta, Summary } from "./api";
import { COMMODITY_NAMES, fmtDate, fmtDateTime, fmtPct, shortKab } from "./format";

export type NotifCategory = "Perlu Tindakan" | "Rekomendasi Engine" | "Update Data";

export type NotificationItem = {
  id: string;
  type: "warning" | "info" | "success" | "ai" | "data";
  title: string;
  text: string;
  when: string;      // human date, from the data itself
  sortKey: string;   // ISO for ordering
  category: NotifCategory;
  action?: { tab: string; commodity?: string; kabId?: string };
};

export function deriveNotifications(args: {
  anomalies: AnomalyRecord[];
  matches: Match[];
  summary: Summary | null;
  meta: Meta | null;
  commodities: { code: string; nama: string }[];
}): NotificationItem[] {
  const { anomalies, matches, summary, meta } = args;
  const out: NotificationItem[] = [];
  const name = (code: string) => args.commodities.find((c) => c.code === code)?.nama ?? COMMODITY_NAMES[code] ?? code;

  for (const a of anomalies.slice(0, 4)) {
    const sign = a.deviation_pct >= 0 ? "+" : "";
    out.push({
      id: `anom-${a.date}-${a.city_id}-${a.commodity_code}`,
      type: "warning",
      title: `${a.type === "SPIKE" ? "Lonjakan" : "Penurunan"} harga ${name(a.commodity_code)} di ${a.city_name}`,
      text: `${sign}${a.deviation_pct.toFixed(1)}% terhadap median bergulir (Rp ${a.price.toLocaleString("id-ID")}/kg), ${a.persistent ? "persisten 2 hari atau lebih" : "satu hari"}.`,
      when: fmtDate(a.date),
      sortKey: a.date,
      category: "Perlu Tindakan",
      action: { tab: "harga", commodity: a.commodity_code, kabId: a.city_id },
    });
  }

  const boosted = matches.filter((m) => m.equity_multiplier >= 1.15).slice(0, 3);
  for (const m of boosted) {
    out.push({
      id: `eq-${m.surplus.kab_id}-${m.deficit.kab_id}-${m.commodity_code}`,
      type: "ai",
      title: `Prioritas equity: ${shortKab(m.surplus.kab_nama)} ke ${shortKab(m.deficit.kab_nama)}`,
      text: `${m.matched_volume_tons.toLocaleString("id-ID", { maximumFractionDigits: 0 })} t ${m.commodity_nama}, ${m.distance_km.toFixed(0)} km, skor ${m.final_score.toFixed(0)} (equity x${m.equity_multiplier.toFixed(2)}, IPM ${m.deficit_ipm.toFixed(1)}).`,
      when: meta?.data_as_of.price_history_end ? `data ${fmtDate(meta.data_as_of.price_history_end)}` : "engine run",
      sortKey: meta?.data_as_of.price_history_end ?? "0000",
      category: "Rekomendasi Engine",
      action: { tab: "distribusi", commodity: m.commodity_code, kabId: m.deficit.kab_id },
    });
  }

  if (summary) {
    for (const [code, s] of Object.entries(summary.per_commodity)) {
      if (s.n_deficit_kab > 0 && (s.coverage_pct ?? 0) < 50) {
        out.push({
          id: `cov-${code}`,
          type: "warning",
          title: `${name(code)}: kebutuhan tertutup ${fmtPct(s.coverage_pct, 0)}`,
          text: s.n_matches === 0
            ? `${s.n_deficit_kab} kabupaten defisit tanpa pemasok domestik yang layak. Engine menyarankan jalur impor (external_opportunity).`
            : `${s.unmatched_deficit_kab.length} kabupaten belum terpasok: ${s.unmatched_deficit_kab.slice(0, 4).join(", ")}.`,
          when: `BPS ${summary.data_as_of.bps_reference_year}`,
          sortKey: "0001",
          category: "Perlu Tindakan",
          action: { tab: "distribusi", commodity: code },
        });
      }
    }
  }

  if (meta) {
    out.push({
      id: "data-refresh",
      type: "data",
      title: "Data diperbarui",
      text: `Harga harian s.d. ${fmtDate(meta.data_as_of.price_history_end)}, scan anomali ${fmtDateTime(meta.data_as_of.anomaly_scan_generated_at)}, prakiraan ${fmtDateTime(meta.data_as_of.forecast_generated_at)}, neraca BPS ${meta.data_as_of.bps_reference_year}.`,
      when: fmtDateTime(meta.data_as_of.anomaly_scan_generated_at),
      sortKey: meta.data_as_of.anomaly_scan_generated_at ?? "0000",
      category: "Update Data",
      action: { tab: "laporan" },
    });
    if (meta.engine_run.welfare_gain_pct !== null) {
      out.push({
        id: "engine-lp",
        type: "success",
        title: `Allocator ${meta.allocator === "lp_optimal" ? "LP optimal" : meta.allocator} aktif`,
        text: `Welfare berbobot equity ${meta.engine_run.welfare_gain_pct >= 0 ? "+" : ""}${meta.engine_run.welfare_gain_pct.toFixed(1)}% dibanding greedy, ${meta.coverage.matches} match, ${meta.engine_run.latency_ms?.toFixed(0)} ms.`,
        when: `engine v${meta.engine_version}`,
        sortKey: "0000",
        category: "Update Data",
        action: { tab: "laporan" },
      });
    }
  }

  return out.sort((a, b) => (a.sortKey < b.sortKey ? 1 : -1));
}
