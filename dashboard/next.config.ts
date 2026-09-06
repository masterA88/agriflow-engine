import type { NextConfig } from "next";

// Static security headers on every response. The Content-Security-Policy is
// NOT here: it carries a per-request nonce and is set in proxy.ts, which is
// the only place a fresh nonce can be minted and handed to the renderer.
const securityHeaders = [
  {
    // Redundant on *.vercel.app (already HSTS-preloaded) but correct to set
    // now for when a custom domain is attached.
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Neither the login page nor the dashboard should ever render in a frame
  // (anti-clickjacking). CSP frame-ancestors is the modern equivalent; this
  // stays for browsers that predate it.
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), browsing-topics=(), payment=(), usb=()",
  },
  // Isolate the browsing context from cross-origin windows (Spectre class).
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  // Legacy IE download handling; harmless elsewhere.
  { key: "X-DNS-Prefetch-Control", value: "off" },
];

const nextConfig: NextConfig = {
  // No "X-Powered-By: Next.js" fingerprint on responses.
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
