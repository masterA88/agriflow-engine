// First-party behaviour telemetry for the dashboard.
//
// Rules this module enforces on the client (the server enforces them again):
//  * No-op without consent. The agriflow_consent cookie must carry the current
//    CONSENT_VERSION; it is read on every call so withdrawal is immediate.
//  * No free text, ever. Callers pass codes, ids, counts and short labels.
//  * Fail silently. A telemetry error never reaches the user or blocks render.
//  * Batch: flush at 10 events, every 5 seconds, and on tab hide (keepalive fetch).
//
// The server derives the per-day user token from session_id; the browser never
// sees or sends a hash of anything personal.

import { useSyncExternalStore } from "react";
import { API_BASE } from "./api";
import { isGuest } from "./guest";

export const CONSENT_VERSION = "2026-09-v1";
export const CONSENT_COOKIE = "agriflow_consent";
const APP_VERSION = "dashboard-1.2";
const ENDPOINT = `${API_BASE}/api/v1/events`;
const FLUSH_AT = 10;
const FLUSH_MS = 5000;

export type EventType =
  | "page_view" | "session_start" | "session_end" | "ui_click"
  | "tab_view" | "commodity_pick" | "kabupaten_pick" | "forecast_view"
  | "anomaly_view" | "explain_view" | "simulate_run" | "download"
  | "notification_click" | "faq_search" | "optin";

export type Detail = Record<string, string | number | boolean>;

type Ev = {
  type: EventType;
  ts: number;
  commodity?: string;
  kabupaten_id?: string;
  detail?: Detail;
};

const queue: Ev[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;
let signedIn = false;

/** The auth layer tells us whether a real account is signed in. */
export function setSignedIn(v: boolean): void { signedIn = v; }

export type ConsentState = "accepted" | "declined" | "none";
const consentListeners = new Set<() => void>();
function subscribeConsent(cb: () => void): () => void { consentListeners.add(cb); return () => { consentListeners.delete(cb); }; }
function serverConsent(): ConsentState | "unknown" { return "unknown"; }

/** Consent as a React subscription. "unknown" only during server render and hydration. */
export function useConsent(): ConsentState | "unknown" {
  return useSyncExternalStore(subscribeConsent, readConsent, serverConsent);
}

export function readConsent(): ConsentState {
  if (typeof document === "undefined") return "none";
  const m = document.cookie.split("; ").find((c) => c.startsWith(`${CONSENT_COOKIE}=`));
  if (!m) return "none";
  const v = m.slice(CONSENT_COOKIE.length + 1);
  if (v === CONSENT_VERSION) return "accepted";
  if (v === `declined-${CONSENT_VERSION}`) return "declined";
  return "none"; // stale version: ask again
}

export function writeConsent(decision: "accepted" | "declined"): void {
  const v = decision === "accepted" ? CONSENT_VERSION : `declined-${CONSENT_VERSION}`;
  const secure = typeof location !== "undefined" && location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${CONSENT_COOKIE}=${v}; path=/; max-age=${365 * 24 * 3600}; SameSite=Lax${secure}`;
  consentListeners.forEach((cb) => cb());
}

export function sessionId(): string {
  try {
    let id = sessionStorage.getItem("agriflow_sid");
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem("agriflow_sid", id);
    }
    return id;
  } catch {
    return "00000000-0000-4000-8000-000000000000";
  }
}

function sanitizeDetail(d?: Detail): Detail | undefined {
  if (!d) return undefined;
  const out: Detail = {};
  for (const [k, v] of Object.entries(d)) {
    if (["text", "message", "phone", "email", "name", "query"].includes(k)) continue;
    if (typeof v === "string") out[k] = v.replace(/\s+/g, " ").trim().slice(0, 80);
    else if (typeof v === "number" || typeof v === "boolean") out[k] = v;
  }
  return out;
}

/** Record one event. Silently does nothing without consent. */
export function track(type: EventType, props?: { commodity?: string; kabupaten_id?: string; detail?: Detail }): void {
  try {
    if (readConsent() !== "accepted") return;
    queue.push({ type, ts: Date.now(), commodity: props?.commodity, kabupaten_id: props?.kabupaten_id, detail: sanitizeDetail(props?.detail) });
    if (queue.length >= FLUSH_AT) flush(false);
    else if (!timer) timer = setTimeout(() => flush(false), FLUSH_MS);
  } catch {
    /* never surface */
  }
}

function payload(events: Ev[]): string {
  return JSON.stringify({
    events,
    session_id: sessionId(),
    signed_in: signedIn ? true : isGuest() ? false : null,
    consent_version: CONSENT_VERSION,
    app_version: APP_VERSION,
  });
}

/** Send whatever is queued. `beacon` is used when the page is going away. */
export function flush(beacon: boolean): void {
  if (timer) { clearTimeout(timer); timer = null; }
  if (queue.length === 0) return;
  const batch = queue.splice(0, FLUSH_AT);
  if (queue.length) timer = setTimeout(() => flush(false), 0);
  try {
    const body = payload(batch);
    // keepalive lets the request outlive a page unload, which is what
    // sendBeacon would give us, without sendBeacon's credentialed CORS mode
    // (the API answers cross-origin without Access-Control-Allow-Credentials).
    void fetch(ENDPOINT, {
      method: "POST", headers: { "Content-Type": "application/json" }, body,
      keepalive: true, credentials: "omit", mode: "cors",
    }).catch(() => {});
    void beacon;
  } catch {
    /* never surface */
  }
}

/**
 * Global capture: page views, session start/end, and every click on a
 * button or link (label only, never input contents). Installed once by
 * TelemetryProvider. Returns an uninstall function.
 */
export function installGlobalTracking(): () => void {
  if (typeof window === "undefined") return () => {};
  const startedAt = Date.now();
  track("session_start", { detail: { path: location.pathname, viewport_w: window.innerWidth, viewport_h: window.innerHeight } });

  const onClick = (e: MouseEvent) => {
    const el = (e.target as HTMLElement | null)?.closest("button, a, [data-track]") as HTMLElement | null;
    if (!el) return;
    const label = (el.getAttribute("data-track") || el.getAttribute("aria-label") || el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 40);
    const detail: Detail = { tag: el.tagName.toLowerCase(), label, path: location.pathname };
    const href = (el as HTMLAnchorElement).getAttribute?.("href");
    if (href) { try { detail.target = new URL(href, location.href).pathname.slice(0, 80); } catch { /* ignore */ } }
    track("ui_click", { detail });
  };
  const onVis = () => {
    if (document.visibilityState === "hidden") {
      track("session_end", { detail: { duration_ms: Date.now() - startedAt, path: location.pathname } });
      flush(true);
    }
  };
  document.addEventListener("click", onClick, true);
  document.addEventListener("visibilitychange", onVis);
  window.addEventListener("pagehide", onVis);
  return () => {
    document.removeEventListener("click", onClick, true);
    document.removeEventListener("visibilitychange", onVis);
    window.removeEventListener("pagehide", onVis);
  };
}
