"use client";

import { MapContainer, TileLayer, CircleMarker, Tooltip, Polyline } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { Kabupaten, SurplusDeficitRow, Match } from "../lib/api";
import { fmtTon } from "../lib/format";

const CENTER: [number, number] = [-7.7, 112.5]; // Jawa Timur centroid-ish
const ZOOM = 8;

type Props = {
  kabupaten: Kabupaten[];
  surplusDeficit: SurplusDeficitRow[];
  matches: Match[];
  onSelectKab: (kabId: string) => void;
  selectedKabId: string | null;
  unreachable?: string[];
  flowLimit?: number;
  highlightMatch?: Match | null;
};

// Radius proportional to sqrt(volume) so visual area ~ volume.
function bubbleRadius(tons: number): number {
  if (tons <= 0) return 4;
  return Math.max(6, Math.min(28, Math.sqrt(tons) * 0.35));
}

export default function MapView({
  kabupaten, surplusDeficit, matches, onSelectKab, selectedKabId,
  unreachable = [], flowLimit = 12, highlightMatch = null,
}: Props) {
  const rowByKab = new Map<string, SurplusDeficitRow>();
  for (const r of surplusDeficit) rowByKab.set(r.kab_id, r);
  const down = new Set(unreachable);

  return (
    <MapContainer center={CENTER} zoom={ZOOM} scrollWheelZoom style={{ height: "100%", width: "100%" }}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />

      {matches.slice(0, flowLimit).map((m, idx) => {
        const hot = highlightMatch
          && m.surplus.kab_id === highlightMatch.surplus.kab_id
          && m.deficit.kab_id === highlightMatch.deficit.kab_id;
        return (
          <Polyline
            key={`flow-${idx}`}
            positions={[[m.surplus.lat, m.surplus.lng], [m.deficit.lat, m.deficit.lng]]}
            pathOptions={{
              color: hot ? "#eab308" : "#4e643c",
              weight: hot ? 4 : Math.max(1.5, Math.min(4, m.matched_volume_tons / 20000)),
              opacity: hot ? 1 : 0.7,
              dashArray: hot ? undefined : "5 5",
            }}
          />
        );
      })}

      {kabupaten.map((k) => {
        const row = rowByKab.get(k.id);
        const role = row?.role;
        const tons = row?.volume_tons ?? 0;
        const isDown = down.has(k.id);
        const color = isDown ? "#52525b" : role === "surplus" ? "#16a34a" : role === "deficit" ? "#dc2626" : "#94a3b8";
        const radius = row ? bubbleRadius(tons) : 4;
        const isSelected = selectedKabId === k.id;
        return (
          <CircleMarker
            key={k.id}
            center={[k.lat, k.lng]}
            radius={radius}
            pathOptions={{
              color: isSelected ? "#facc15" : color,
              weight: isSelected ? 3 : 1.5,
              fillColor: color,
              fillOpacity: row ? (isDown ? 0.35 : 0.55) : 0.25,
              dashArray: isDown ? "4 3" : undefined,
            }}
            eventHandlers={{ click: () => onSelectKab(k.id) }}
          >
            <Tooltip direction="top" offset={[0, -4]}>
              <div className="space-y-1 text-[11px] text-zinc-700 leading-normal">
                <strong className="text-sm text-zinc-900 block border-b border-zinc-100 pb-0.5">{k.nama}</strong>
                <div>Tier: <span className="font-semibold text-zinc-800">{k.tier === "TIER_1_HIGH" ? "1 (kota IHK)" : "2"} · harga harian Siskaperbapo</span></div>
                <div>IPM {k.ipm.toFixed(1)} · {k.population.toLocaleString("id-ID")} jiwa</div>
                {row && (
                  <div className="mt-1 pt-1 border-t border-dashed border-zinc-200 font-semibold" style={{ color }}>
                    {role === "surplus" ? "Surplus" : "Defisit"}: {fmtTon(tons)}
                  </div>
                )}
                {isDown && <div className="text-zinc-700 font-semibold">Skenario: tidak terjangkau</div>}
              </div>
            </Tooltip>
          </CircleMarker>
        );
      })}
    </MapContainer>
  );
}
