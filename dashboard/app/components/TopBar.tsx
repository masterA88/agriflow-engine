"use client";

import { useEffect, useRef, useState } from "react";
import type { Commodity, Meta } from "../lib/api";
import type { NotificationItem } from "../lib/notifications";
import AccountMenu from "./AccountMenu";
import DataStatus from "./DataStatus";
import { Icons } from "./Icons";

export default function TopBar({
  meta, apiError, commodities, commodity, onCommodity, notifications, unread,
  onOpenNotifications, onOpenMenu, onTour, onNotificationAction,
}: {
  meta: Meta | null;
  apiError: string | null;
  commodities: Commodity[];
  commodity: string;
  onCommodity: (code: string) => void;
  notifications: NotificationItem[];
  unread: number;
  onOpenNotifications: () => void;
  onOpenMenu: () => void;
  onTour: () => void;
  onNotificationAction: (n: NotificationItem) => void;
}) {
  const [showCommodity, setShowCommodity] = useState(false);
  const [showNotif, setShowNotif] = useState(false);
  const commodityRef = useRef<HTMLDivElement>(null);
  const bellRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (commodityRef.current && !commodityRef.current.contains(e.target as Node)) setShowCommodity(false);
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) setShowNotif(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const current = commodities.find((c) => c.code === commodity);

  return (
    <div className="flex items-center justify-between gap-2 lg:gap-4 shrink-0 select-none flex-wrap">
      <div className="flex items-center gap-2 min-w-0 flex-1 overflow-hidden">
        <button
          onClick={onOpenMenu}
          className="lg:hidden w-9 h-9 bg-white rounded-full flex items-center justify-center shadow-sm text-zinc-700 shrink-0 relative z-10"
          aria-label="Buka menu"
        >
          <Icons.Menu className="w-4.5 h-4.5" />
        </button>
        <DataStatus meta={meta} error={apiError} compact />
      </div>

      <div className="flex items-center gap-2 lg:gap-3">
        <AccountMenu />
        <button
          onClick={onTour}
          className="hidden sm:flex bg-white hover:bg-zinc-50 px-3 py-2 rounded-full text-xs font-semibold text-zinc-700 items-center gap-1.5 shadow-sm"
        >
          <Icons.HelpCircle className="w-3.5 h-3.5 text-zinc-500" />
          Panduan
        </button>

        <div className="relative" ref={bellRef}>
          <button
            onClick={() => setShowNotif((v) => !v)}
            className="relative w-9 h-9 bg-white rounded-full flex items-center justify-center hover:bg-zinc-50 shadow-sm"
            aria-label="Notifikasi"
          >
            <Icons.Bell className="w-4 h-4 text-zinc-500" />
            {unread > 0 && (
              <span className="absolute -top-1 -right-1 bg-rose-600 text-white text-[9px] font-bold min-w-[18px] h-[18px] px-1 rounded-full flex items-center justify-center">
                {unread}
              </span>
            )}
          </button>
          {showNotif && (
            <div className="absolute right-0 mt-2 w-[min(20rem,90vw)] bg-white border border-zinc-100 rounded-2xl shadow-xl py-2 z-[1100]">
              <div className="px-4 py-2 border-b border-zinc-100 text-xs font-bold text-zinc-800">Terbaru dari data</div>
              <ul className="max-h-72 overflow-y-auto divide-y divide-zinc-100">
                {notifications.length === 0 && <li className="px-4 py-6 text-xs text-zinc-400 text-center">Belum ada.</li>}
                {notifications.slice(0, 6).map((n) => (
                  <li key={n.id}>
                    <button
                      onClick={() => { onNotificationAction(n); setShowNotif(false); }}
                      className="w-full text-left p-3 text-xs hover:bg-zinc-50 flex items-start gap-2.5"
                    >
                      <NotifIcon type={n.type} />
                      <span className="flex-1 min-w-0">
                        <strong className="text-zinc-800 block leading-snug">{n.title}</strong>
                        <span className="text-zinc-600 block mt-0.5 line-clamp-2">{n.text}</span>
                        <span className="text-[10px] text-zinc-400 block mt-1">{n.when}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              <div className="px-4 py-2 border-t border-zinc-100 text-center">
                <button onClick={() => { onOpenNotifications(); setShowNotif(false); }} className="text-[11px] text-zinc-500 font-semibold hover:text-zinc-800">
                  Lihat semua
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="relative" ref={commodityRef}>
          <button
            onClick={() => setShowCommodity((v) => !v)}
            className="flex items-center gap-2 px-3 sm:px-4 py-2 bg-white rounded-full hover:bg-zinc-50 shadow-sm"
            data-tour="komoditas"
          >
            <span className="text-xs font-bold text-zinc-800 hidden sm:inline">Komoditas</span>
            <span className="text-xs font-semibold text-[#5b7245]">{current?.nama ?? commodity}</span>
            <Icons.ChevronDown className="w-3.5 h-3.5 text-zinc-400" />
          </button>
          {showCommodity && (
            <div className="absolute right-0 mt-2 w-52 bg-white border border-zinc-100 rounded-2xl shadow-xl py-1.5 z-[1100]">
              <div className="px-3.5 py-2 text-[9px] font-bold text-zinc-400 border-b border-zinc-100 uppercase tracking-wider">
                Komoditas dengan data BPS
              </div>
              {commodities.map((c) => (
                <button
                  key={c.code}
                  onClick={() => { onCommodity(c.code); setShowCommodity(false); }}
                  className={`w-full text-left px-4 py-2.5 text-xs hover:bg-zinc-50 ${commodity === c.code ? "bg-emerald-50 text-[#5b7245] font-bold" : "text-zinc-700"}`}
                >
                  {c.nama}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function NotifIcon({ type, className = "w-4 h-4" }: { type: NotificationItem["type"]; className?: string }) {
  switch (type) {
    case "warning": return <Icons.AlertTriangle className={`${className} text-amber-500 shrink-0 mt-0.5`} />;
    case "success": return <Icons.CheckCircle className={`${className} text-emerald-500 shrink-0 mt-0.5`} />;
    case "ai": return <Icons.Scale className={`${className} text-[#5b7245] shrink-0 mt-0.5`} />;
    case "data": return <Icons.Database className={`${className} text-indigo-500 shrink-0 mt-0.5`} />;
    default: return <Icons.Info className={`${className} text-blue-500 shrink-0 mt-0.5`} />;
  }
}
