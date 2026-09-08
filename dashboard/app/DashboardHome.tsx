"use client";

// Dashboard shell. State lives here; every tab is a component under
// components/tabs/. No mock data anywhere: the hooks in
// hooks/useDashboardData.ts surface errors instead of inventing numbers.

import { useCallback, useMemo, useState } from "react";
import { useCoreData, useDistribution, useRecentAnomalies } from "./hooks/useDashboardData";
import type { Match } from "./lib/api";
import { deriveNotifications, type NotificationItem } from "./lib/notifications";
import { track } from "./lib/telemetry";
import ExplainDrawer from "./components/ExplainDrawer";
import Sidebar, { type TabKey } from "./components/Sidebar";
import TopBar from "./components/TopBar";
import Tour from "./components/Tour";
import Bantuan from "./components/tabs/Bantuan";
import Beranda from "./components/tabs/Beranda";
import Distribusi from "./components/tabs/Distribusi";
import HargaTren from "./components/tabs/HargaTren";
import InsightPermintaan from "./components/tabs/InsightPermintaan";
import Laporan from "./components/tabs/Laporan";
import Notifikasi from "./components/tabs/Notifikasi";
import PetaPasokan from "./components/tabs/PetaPasokan";
import Simulasi from "./components/tabs/Simulasi";

export default function Home() {
  const [tab, setTab] = useState<TabKey>("beranda");
  const [pickedCommodity, setCommodity] = useState("bawang_merah");
  const [selectedKabId, setSelectedKabId] = useState<string | null>(null);
  const [analysisCity, setAnalysisCity] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [tourStep, setTourStep] = useState<number | null>(null);
  const [explain, setExplain] = useState<Match | null>(null);
  const [read, setRead] = useState<Set<string>>(new Set());

  const core = useCoreData();
  // First commodity from the API wins if the picked one is not served.
  const commodity = core.commodities.length && !core.commodities.some((c) => c.code === pickedCommodity)
    ? core.commodities[0].code
    : pickedCommodity;
  const dist = useDistribution(commodity, selectedKabId, 100);
  const recent = useRecentAnomalies(6);

  const notifications = useMemo(
    () => deriveNotifications({ anomalies: recent.items, matches: dist.matches, summary: core.summary, meta: core.meta, commodities: core.commodities }),
    [recent.items, dist.matches, core.summary, core.meta, core.commodities],
  );
  const unread = notifications.filter((n) => !read.has(n.id)).length;

  const go = useCallback((t: TabKey) => { setTab(t); window.scrollTo({ top: 0 }); track("tab_view", { detail: { tab: t } }); }, []);
  const pickKab = useCallback((id: string | null, surface: string) => {
    setSelectedKabId(id);
    if (id) track("kabupaten_pick", { kabupaten_id: id, commodity, detail: { surface } });
  }, [commodity]);
  const onNotificationAction = useCallback((n: NotificationItem) => {
    setRead((r) => new Set(r).add(n.id));
    track("notification_click", { commodity: n.action?.commodity, kabupaten_id: n.action?.kabId, detail: { category: n.category, kind: n.type, target_tab: n.action?.tab ?? "" } });
    if (!n.action) return;
    if (n.action.commodity) setCommodity(n.action.commodity);
    if (n.action.tab === "harga" && n.action.kabId) setAnalysisCity(n.action.kabId);
    else if (n.action.kabId) setSelectedKabId(n.action.kabId);
    go(n.action.tab as TabKey);
  }, [go]);

  const name = core.commodities.find((c) => c.code === commodity)?.nama ?? commodity;
  const apiError = core.error;

  return (
    <div className="min-h-screen flex flex-col lg:flex-row bg-[#5b7245] text-zinc-900 font-sans antialiased p-3 lg:p-6 gap-4 lg:gap-6 relative">
      <Sidebar
        active={tab}
        onSelect={go}
        badge={unread}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
      />

      <main className="flex-1 flex flex-col min-w-0 gap-4 lg:gap-6 lg:overflow-y-auto lg:h-[calc(100vh-3rem)]">
        <TopBar
          meta={core.meta}
          apiError={apiError}
          commodities={core.commodities}
          commodity={commodity}
          onCommodity={(c) => { setCommodity(c); setSelectedKabId(null); track("commodity_pick", { commodity: c, detail: { tab } }); }}
          notifications={notifications}
          unread={unread}
          onOpenNotifications={() => go("notifikasi")}
          onOpenMenu={() => setMenuOpen(true)}
          onTour={() => setTourStep(0)}
          onNotificationAction={onNotificationAction}
        />

        {tab === "beranda" && (
          <Beranda
            commodity={commodity} commodities={core.commodities} sd={dist.sd} matches={dist.matches}
            summary={core.summary} meta={core.meta} apiError={apiError} kabupaten={core.kabupaten}
            selectedKabId={selectedKabId} onSelectKab={(id) => pickKab(id, "beranda")} onGo={go} onExplain={setExplain}
            loading={dist.loading || core.loading}
          />
        )}
        {tab === "peta" && (
          <PetaPasokan name={name} sd={dist.sd} matches={dist.matches} kabupaten={core.kabupaten} selectedKabId={selectedKabId} onSelectKab={(id) => pickKab(id, "peta")} />
        )}
        {tab === "distribusi" && (
          <Distribusi
            commodity={commodity} name={name} sd={dist.sd} matches={dist.matches} meta={core.meta} kabupaten={core.kabupaten}
            selectedKabId={selectedKabId} onSelectKab={(id) => pickKab(id, "distribusi")} onExplain={setExplain} loading={dist.loading} error={dist.error}
          />
        )}
        {tab === "simulasi" && (
          <Simulasi commodity={commodity} name={name} sd={dist.sd} baselineMatches={dist.matches} kabupaten={core.kabupaten} onExplain={setExplain} />
        )}
        {tab === "harga" && (
          <HargaTren commodity={commodity} commodities={core.commodities} kabupaten={core.kabupaten} meta={core.meta} initialCity={analysisCity} />
        )}
        {tab === "notifikasi" && (
          <Notifikasi items={notifications} read={read} onRead={(id) => setRead((r) => new Set(r).add(id))} onAction={onNotificationAction} />
        )}
        {tab === "laporan" && <Laporan summary={core.summary} meta={core.meta} commodities={core.commodities} />}
        {tab === "insight" && <InsightPermintaan commodities={core.commodities} kabupaten={core.kabupaten} />}
        {tab === "bantuan" && <Bantuan />}
      </main>

      <ExplainDrawer match={explain} onClose={() => setExplain(null)} />
      <Tour step={tourStep} onStep={setTourStep} onClose={() => setTourStep(null)} />
    </div>
  );
}
