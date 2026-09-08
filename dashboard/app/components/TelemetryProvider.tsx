"use client";

// Mounts once in the root layout. Installs the global click/session capture,
// records a page_view on every route change, and keeps the signed-in flag in
// sync with the auth layer. Renders the consent banner.

import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "../lib/auth";
import { installGlobalTracking, setSignedIn, track } from "../lib/telemetry";
import ConsentBanner from "./ConsentBanner";

export default function TelemetryProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user } = useAuth();

  useEffect(() => { setSignedIn(Boolean(user)); }, [user]);

  useEffect(() => installGlobalTracking(), []);

  useEffect(() => {
    if (pathname) track("page_view", { detail: { path: pathname.slice(0, 80) } });
  }, [pathname]);

  return (
    <>
      {children}
      <ConsentBanner />
    </>
  );
}
