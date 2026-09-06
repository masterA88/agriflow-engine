import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import { Geist, Geist_Mono, Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "./lib/auth";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Body face. Self-hosted through next/font instead of a Google Fonts CSS
// import: the stylesheet request was the one third-party fetch the CSP would
// otherwise have to allow, and next/font serves the files from this origin.
const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700", "800"],
  display: "swap",
});

export const metadata: Metadata = {
  // Base for resolving the OG image to an absolute URL when the page is
  // shared; Vercel previews override the host at runtime, production matches.
  metadataBase: new URL("https://agriflow-engine.vercel.app"),
  // "/" is the public landing now, so the default title/description speak to
  // a first-time visitor; sharing the link should read as a product, not an
  // internal dashboard. The OG image is the same live-dashboard shot the
  // landing hero uses.
  title: "AgriFlow · Platform Ketahanan Pangan Jawa Timur",
  description:
    "Pencocokan pasokan pangan surplus-defisit untuk 38 kabupaten/kota Jawa Timur, dihitung optimal dari data BPS dan PIHPS.",
  applicationName: "AgriFlow",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, title: "AgriFlow", statusBarStyle: "default" },
  openGraph: {
    title: "AgriFlow · Platform Ketahanan Pangan Jawa Timur",
    description:
      "Surplus di satu daerah, defisit di daerah lain. AgriFlow memasangkannya dari data resmi BPS dan PIHPS.",
    images: ["/landing-hero.jpg"],
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#5b7245",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Reading the request headers opts every route into per-request rendering.
  // That is deliberate: proxy.ts mints a fresh CSP nonce per request and
  // Next.js stamps it on its inline scripts only when the page is rendered at
  // request time. A statically prerendered page would ship yesterday's nonce
  // and the browser would refuse to run the app.
  await headers();
  return (
    <html
      lang="id"
      className={`${geistSans.variable} ${geistMono.variable} ${inter.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
