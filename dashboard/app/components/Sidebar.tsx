"use client";

import { Icons } from "./Icons";

export type TabKey = "beranda" | "peta" | "distribusi" | "harga" | "simulasi" | "notifikasi" | "laporan" | "bantuan";

export const TABS: { key: TabKey; label: string; icon: React.ReactNode }[] = [
  { key: "beranda", label: "Beranda", icon: <Icons.Home /> },
  { key: "peta", label: "Peta Pasokan", icon: <Icons.Map /> },
  { key: "distribusi", label: "Rekomendasi Distribusi", icon: <Icons.Truck /> },
  { key: "simulasi", label: "Simulasi What-if", icon: <Icons.Sliders /> },
  { key: "harga", label: "Harga & Prakiraan", icon: <Icons.TrendingUp /> },
  { key: "notifikasi", label: "Notifikasi", icon: <Icons.Bell /> },
  { key: "laporan", label: "Laporan & KPI", icon: <Icons.FileText /> },
  { key: "bantuan", label: "Bantuan", icon: <Icons.HelpCircle /> },
];

function SidebarButton({ active, icon, label, badge, onClick }: {
  active: boolean; icon: React.ReactNode; label: string; badge?: number; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs transition-all cursor-pointer group ${
        active ? "bg-[#5b7245] text-white font-semibold shadow-sm" : "text-zinc-500 hover:bg-zinc-50 hover:text-zinc-800 font-medium"
      }`}
    >
      <span className="flex items-center gap-2.5">
        <span className={active ? "text-white" : "text-zinc-400 group-hover:text-zinc-600"}>{icon}</span>
        <span>{label}</span>
      </span>
      {badge !== undefined && badge > 0 && (
        <span className={`text-[9px] font-extrabold min-w-[18px] h-[18px] px-1 rounded-full flex items-center justify-center ${active ? "bg-white text-[#5b7245]" : "bg-rose-600 text-white"}`}>
          {badge}
        </span>
      )}
    </button>
  );
}

export default function Sidebar({
  active, onSelect, badge, open, onClose,
}: {
  active: TabKey;
  onSelect: (t: TabKey) => void;
  badge: number;
  open: boolean;
  onClose: () => void;
}) {
  const body = (
    <div className="flex flex-col gap-4">
      <div className="bg-white rounded-2xl p-5 shadow-md flex flex-col gap-4">
        <div className="pb-3 border-b border-zinc-100 flex items-center justify-between">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/logo.png" alt="AgriFlow" className="h-14 w-auto object-contain" />
          <button onClick={onClose} className="lg:hidden text-zinc-400 hover:text-zinc-700" aria-label="Tutup menu">
            <Icons.X className="w-5 h-5" />
          </button>
        </div>
        <nav className="space-y-1" aria-label="Navigasi utama">
          {TABS.map((tab) => (
            <SidebarButton
              key={tab.key}
              active={active === tab.key}
              icon={tab.icon}
              label={tab.label}
              badge={tab.key === "notifikasi" ? badge : undefined}
              onClick={() => { onSelect(tab.key); onClose(); }}
            />
          ))}
        </nav>
      </div>

      <div className="bg-[#dbe6d3] text-[#4e643c] rounded-2xl p-4 text-xs font-medium leading-relaxed shadow-sm flex items-start gap-2.5">
        <Icons.Info className="w-4 h-4 shrink-0 mt-0.5" />
        <span>
          Setiap angka di dashboard ini dihitung engine dari data BPS, Siskaperbapo, dan PIHPS. Klik kartu rekomendasi untuk melihat mengapa engine memilihnya.
        </span>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop */}
      <aside className="hidden lg:flex w-64 flex-col shrink-0 h-[calc(100vh-3rem)] overflow-y-auto">
        {body}
      </aside>
      {/* Mobile drawer */}
      {open && (
        <div className="lg:hidden fixed inset-0 z-[10000] flex">
          <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />
          <aside className="relative w-[85vw] max-w-xs h-full overflow-y-auto p-3 bg-[#5b7245]">
            {body}
          </aside>
        </div>
      )}
    </>
  );
}
