// Server-side route protection (login-first) and the per-request CSP nonce.
//
// In Next.js 16 this file is `proxy.ts` (renamed from `middleware.ts` in 16)
// and the exported function must be named `proxy`.
//
// GATE MODEL
// ----------
// Every page requires a signed-in user OR a guest cookie. Unauthenticated
// visitors are funneled to /login. The auth pages themselves (/login,
// /forgot-password, /reset-password) stay reachable while signed out, otherwise
// you could never get in.
//
// The guest cookie is the judge bypass (see app/lib/guest.ts). It is a UX
// funnel, not security: this proxy decides which PAGE renders, while the data
// itself is authorized separately by JWT verification in the FastAPI backend
// (whatsapp_bot/auth.py). A forged cookie gets someone to the map, which shows
// public government data anyway, and no further.
//
// Per the Next.js docs, proxy is for optimistic checks, not authorization —
// which is exactly this split: routing funnel here, real enforcement at the
// data layer.
//
// CONTENT SECURITY POLICY
// -----------------------
// Every response carries a nonce-based CSP. The nonce is minted here, handed
// to Next.js through the `Content-Security-Policy` *request* header (which is
// how the framework learns what to stamp on its own inline bootstrap scripts),
// and echoed on the response. `'strict-dynamic'` lets those nonced scripts
// load the chunks they import without listing every hash. Anything not
// minted by this render (an injected <script>, an inline handler smuggled
// through a data field) is refused by the browser.
//
// Pages have to render per request for a per-request nonce to be meaningful;
// app/layout.tsx reads headers() for exactly that reason.

import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const GUEST_COOKIE = "agriflow_guest"; // keep in sync with app/lib/guest.ts
const DEV_COOKIE = "agriflow_dev"; // keep in sync with app/lib/devauth.ts

// Pages that must stay reachable while signed out.
const PUBLIC_PREFIXES = ["/login", "/forgot-password", "/reset-password"];

const IS_DEV = process.env.NODE_ENV === "development";

function stripSlash(url: string | undefined): string | undefined {
  return url?.replace(/\/$/, "") || undefined;
}

function buildCsp(nonce: string): string {
  const api = stripSlash(process.env.NEXT_PUBLIC_API_URL) ?? "http://localhost:8000";
  const supabase = stripSlash(process.env.NEXT_PUBLIC_SUPABASE_URL);

  // Where the browser may open fetch/XHR/WebSocket connections: the FastAPI
  // backend, Supabase Auth (plus its realtime socket), and in dev the HMR
  // socket that next dev opens on whatever port it was started on.
  const connect = ["'self'", api];
  if (supabase) connect.push(supabase, supabase.replace(/^http/, "ws"));
  if (IS_DEV) connect.push("ws://localhost:*", "http://localhost:*");

  const directives = [
    "default-src 'self'",
    // next dev evaluates source maps and React refresh through eval.
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${IS_DEV ? " 'unsafe-eval'" : ""}`,
    // next/font, Leaflet, and React all set style attributes inline.
    "style-src 'self' 'unsafe-inline'",
    // Map tiles come from OpenStreetMap; Leaflet builds marker icons as data
    // URIs; blob: covers the CSV download link the report page builds.
    "img-src 'self' data: blob: https://*.tile.openstreetmap.org",
    "font-src 'self' data:",
    `connect-src ${connect.join(" ")}`,
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "media-src 'none'",
    "object-src 'none'",
    "frame-src 'none'",
    "frame-ancestors 'none'",
    "form-action 'self'",
    "base-uri 'self'",
  ];
  // Rewrites http:// subresources to https:// in production. Left out in
  // dev, where the API lives on plain http://localhost.
  if (!IS_DEV) directives.push("upgrade-insecure-requests");
  return directives.join("; ");
}

function newNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return btoa(String.fromCharCode(...bytes));
}

export async function proxy(request: NextRequest) {
  const path = request.nextUrl.pathname;
  const nonce = newNonce();
  const csp = buildCsp(nonce);

  // Builds the pass-through response, re-reading request.headers each time so
  // cookies written by Supabase below travel with the forwarded request.
  const passThrough = () => {
    const requestHeaders = new Headers(request.headers);
    requestHeaders.set("x-nonce", nonce);
    requestHeaders.set("content-security-policy", csp);
    const res = NextResponse.next({ request: { headers: requestHeaders } });
    res.headers.set("Content-Security-Policy", csp);
    return res;
  };
  const withCsp = (res: NextResponse) => {
    res.headers.set("Content-Security-Policy", csp);
    return res;
  };

  // The public landing. Exact match only: "/" cannot go into PUBLIC_PREFIXES
  // because every path startsWith "/", which would un-gate the whole site.
  // Short-circuited before the Supabase call so the landing costs no auth
  // round-trip.
  if (path === "/") return passThrough();

  const isPublic = PUBLIC_PREFIXES.some((p) => path.startsWith(p));
  const hasGuest = request.cookies.get(GUEST_COOKIE)?.value === "1";
  // Dev-login cookie (see app/lib/devauth.ts). Only honoured when dev login is
  // explicitly enabled, so production ignores it even if someone sets it by
  // hand — the guest cookie is the only intended bypass there. Like guest, it
  // is a page-routing bypass only and never satisfies the backend's JWT check.
  const hasDev =
    process.env.NEXT_PUBLIC_DEV_LOGIN === "true" &&
    Boolean(request.cookies.get(DEV_COOKIE)?.value);

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  let response = passThrough();
  let user = null;

  // Resolve the real session when Supabase is configured. Wrapped in try/catch
  // because a misconfigured or unreachable Supabase URL (e.g. placeholder creds
  // in local preview) would otherwise throw and 500 every page. On any failure
  // we treat the visitor as signed out and let the guest cookie be the way in.
  if (url && anonKey) {
    try {
      const supabase = createServerClient(url, anonKey, {
        cookies: {
          getAll() {
            return request.cookies.getAll();
          },
          setAll(cookiesToSet) {
            // Write refreshed tokens onto both the request (so any later read
            // this pass sees them) and the response (so the browser stores
            // them). Skipping the request copy logs the user out one navigation
            // after a token refresh.
            cookiesToSet.forEach(({ name, value }) =>
              request.cookies.set(name, value),
            );
            response = passThrough();
            cookiesToSet.forEach(({ name, value, options }) =>
              response.cookies.set(name, value, options),
            );
          },
        },
      });
      // getUser() revalidates the token with Supabase rather than trusting the
      // cookie contents, and refreshes it near expiry.
      user = (await supabase.auth.getUser()).data.user;
    } catch {
      user = null;
    }
  }

  const authed = Boolean(user) || hasGuest || hasDev;

  // A genuinely signed-in user has no reason to see the login page.
  // Guests are NOT redirected away from /login, so they can upgrade to a real
  // account whenever they want.
  if (path.startsWith("/login") && user) {
    return withCsp(NextResponse.redirect(new URL("/dashboard", request.url)));
  }

  // Auth pages are always reachable.
  if (isPublic) return response;

  // Everything else is gated.
  if (!authed) {
    const redirect = request.nextUrl.clone();
    redirect.pathname = "/login";
    // Preserve the destination so login can return them there. LoginForm only
    // honours relative paths, so this cannot become an open redirect.
    redirect.searchParams.set("next", path);
    return withCsp(NextResponse.redirect(redirect));
  }

  return response;
}

export const config = {
  // Skip static assets and image optimization — gating a .svg on a Supabase
  // round trip would add one to every asset request.
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|webmanifest)$).*)",
  ],
};
