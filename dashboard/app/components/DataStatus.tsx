"use client";

// The "Data per" pill. Every value comes from /api/v1/meta, so the badge can
// never claim freshness the artefacts do not have.

import type { Meta } from "../lib/api";
import { fmtDate } from "../lib/format";
import { Icons } from "./Icons";

export default function DataStatus({ meta, error, compact = false }: { meta: Meta | null; error: string | null; compact?: boolean }) {
  if (error) {
    return (
      <div className="bg-rose-50 text-rose-800 border border-rose-200 rounded-full px-3 py-1.5 text-[11px] font-semibold flex items-center gap-1.5">
        <Icons.AlertTriangle className="w-3.5 h-3.5" />
        API tidak terjangkau
      </div>
    );
  }
  if (!meta) {
    return <div className="bg-white/70 rounded-full px-3 py-1.5 text-[11px] text-zinc-500 animate-pulse">Memuat status data...</div>;
  }
  const d = meta.data_as_of;
  return (
    <div
      className="bg-white rounded-full px-3 py-1.5 text-[11px] text-zinc-700 flex items-center gap-2 shadow-sm min-w-0 max-w-full overflow-hidden"
      title={`Engine v${meta.engine_version}${meta.git_commit ? ` (${meta.git_commit})` : ""} · allocator ${meta.allocator} · gerbang anomali ${meta.anomaly_gate} · jarak: ${d.road_distance}`}
    >
      <Icons.Database className="w-3.5 h-3.5 text-[#5b7245] shrink-0" />
      <span className="block min-w-0 truncate">
        <strong>Data per:</strong> harga {fmtDate(d.price_history_end)}
        {!compact && <> · BPS {d.bps_reference_year} · IPM {d.ipm_year}</>}
        {" "}· engine v{meta.engine_version}
        {!compact && meta.allocator === "lp_optimal" && <> · LP optimal</>}
      </span>
    </div>
  );
}
