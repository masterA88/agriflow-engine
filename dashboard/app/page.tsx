// Public landing page. Server-rendered and static except the GuestCta islands,
// so a cold visit costs no auth round-trip (proxy.ts lets "/" through before
// touching Supabase). Copy and structure follow the DRA landing brief:
// hero with the real product as the visual, problem framing, feature tiles,
// data provenance as a first-class trust element, then one repeated CTA.
import Image from "next/image";
import Link from "next/link";
import GuestCta from "./components/GuestCta";

// Jumlah uji otomatis yang lulus. Angka ini dipajang sebagai sinyal kepercayaan,
// jadi ia harus benar. Sebelumnya tertulis 597 di dua tempat terpisah dan sudah
// melenceng jauh tanpa ada yang menyadarinya.
//
// Verifikasi:  python -m pytest tests/ -q
// Diperiksa 2026-09-12: 693 lulus, 1 dilewati, 694 terkumpul.
const UJI_LULUS = 693;

const primaryCta =
  "inline-block rounded-lg bg-emerald-700 px-6 py-3 text-sm font-semibold text-white " +
  "hover:bg-emerald-800 transition-colors";
const secondaryCtaOnDark =
  "inline-block rounded-lg border border-white/40 px-6 py-3 text-sm font-semibold " +
  "text-white hover:bg-white/10 transition-colors";

const features = [
  {
    title: "Alokasi optimal dengan bobot keadilan",
    body:
      "Allocator LP-optimal mengarahkan pasokan dari daerah surplus ke defisit dengan " +
      "biaya distribusi terendah. Bobot ekuitas mendahulukan daerah tertinggal, bukan " +
      "sekadar yang terdekat.",
  },
  {
    title: "Prakiraan harga dengan pita ketidakpastian",
    body:
      "Prakiraan harga disertai conformal band, jadi Anda melihat rentang yang jujur, " +
      "bukan satu angka yang seolah pasti.",
  },
  {
    title: "Deteksi anomali yang tahan pencilan",
    body:
      "Lonjakan harga dan pasokan ditandai lewat gerbang Hampel/MAD, sehingga satu data " +
      "ekstrem tidak menutupi sinyal yang sebenarnya.",
  },
  {
    title: "Kartu match yang bisa dijelaskan",
    body:
      "Setiap rekomendasi punya kartu “Mengapa match ini”: asal, tujuan, jarak, dan " +
      "alasannya. Tidak ada kotak hitam.",
  },
  {
    title: "Bot WhatsApp, Indonesia dan Jawa",
    body:
      "Tanya lewat WhatsApp dalam bahasa Indonesia atau Jawa. Data yang sama, tanpa " +
      "membuka dashboard.",
  },
];

const sources = [
  {
    name: "BPS 2022",
    body: "Produksi dan konsumsi pangan, 38 kabupaten/kota, enam komoditas.",
  },
  {
    name: "Siskaperbapo + PIHPS",
    body:
      "Harga pangan harian untuk 38 kabupaten/kota (Siskaperbapo Jatim, PIHPS " +
      "sebagai cadangan) sebagai dasar prakiraan dan deteksi anomali.",
  },
  {
    name: "IPM 2024",
    body: "Indeks Pembangunan Manusia sebagai dasar bobot keadilan antar daerah.",
  },
];

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-[#5b7245] text-white">
      {/* Hero */}
      <section className="px-6 pt-16 pb-12 md:pt-24">
        <div className="mx-auto max-w-5xl text-center">
          <p className="text-sm font-semibold uppercase tracking-widest text-white/70">
            Platform Ketahanan Pangan Jawa Timur
          </p>
          <h1 className="mt-4 text-4xl md:text-5xl font-semibold leading-tight">
            Surplus di satu daerah, defisit di daerah lain.
            <br className="hidden md:block" /> AgriFlow memasangkannya.
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-white/80">
            Pencocokan pasokan pangan untuk 38 kabupaten/kota dan enam komoditas,
            dihitung optimal dari data resmi BPS, Siskaperbapo, dan PIHPS. Bukan kira-kira, dan
            setiap rekomendasi bisa ditelusuri.
          </p>
          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3">
            <GuestCta className={primaryCta}>Lihat Dashboard sebagai Tamu</GuestCta>
            <Link href="/login" className={secondaryCtaOnDark}>
              Masuk untuk dinas &amp; mitra
            </Link>
          </div>
          <p className="mt-5 text-xs text-white/60">
            Data BPS 2022 · Siskaperbapo + PIHPS harga harian 38 kabupaten/kota · IPM 2024 &nbsp;·&nbsp; Engine v1.1.0 ·
            {UJI_LULUS} uji otomatis lulus
          </p>
        </div>
        <div className="mx-auto mt-10 max-w-5xl overflow-hidden rounded-xl border border-white/20 shadow-2xl">
          <Image
            src="/landing-hero.jpg"
            alt="Dashboard AgriFlow: peta surplus-defisit Jawa Timur dengan rekomendasi match"
            width={1568}
            height={716}
            priority
            className="w-full h-auto"
          />
        </div>
      </section>

      {/* Problem framing */}
      <section className="bg-white px-6 py-16 text-slate-900">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="text-2xl md:text-3xl font-semibold">
            Masalahnya bukan jumlah pangan, tapi arah distribusinya.
          </h2>
          <p className="mt-4 text-slate-600">
            Di satu kabupaten hasil panen melimpah dan harga jatuh. Di kabupaten
            sebelah pasokan tipis dan harga naik. Mencocokkan keduanya selama ini
            manual dan lambat. AgriFlow mengubahnya menjadi keputusan berbasis data
            yang bisa dipertanggungjawabkan.
          </p>
        </div>
      </section>

      {/* Feature tiles */}
      <section className="bg-white px-6 pb-16 text-slate-900">
        <div className="mx-auto grid max-w-5xl gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map((f) => (
            <div
              key={f.title}
              className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <h3 className="font-semibold">{f.title}</h3>
              <p className="mt-2 text-sm text-slate-600">{f.body}</p>
            </div>
          ))}
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-5">
            <h3 className="font-semibold text-emerald-900">
              Coba tanpa membuat akun
            </h3>
            <p className="mt-2 text-sm text-emerald-800">
              Mode Tamu membuka peta, rekomendasi, prakiraan, dan simulasi what-if
              untuk peninjauan.
            </p>
            <GuestCta className="mt-4 inline-block rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800">
              Buka sebagai Tamu
            </GuestCta>
          </div>
        </div>
      </section>

      {/* Data provenance */}
      <section className="bg-[#eef2e6] px-6 py-16 text-slate-900">
        <div className="mx-auto max-w-5xl">
          <h2 className="text-center text-2xl md:text-3xl font-semibold">
            Angka yang bisa Anda pertanggungjawabkan.
          </h2>
          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            {sources.map((s) => (
              <div
                key={s.name}
                className="rounded-xl border border-slate-200 bg-white p-5 text-center"
              >
                <p className="text-lg font-semibold text-emerald-800">{s.name}</p>
                <p className="mt-2 text-sm text-slate-600">{s.body}</p>
              </div>
            ))}
          </div>
          <p className="mx-auto mt-8 max-w-2xl text-center text-sm text-slate-600">
            Tidak ada data karangan. Bila sumber tidak memuat angkanya, dashboard
            menampilkan kosong, bukan tebakan.
          </p>
          <p className="mx-auto mt-2 max-w-2xl text-center text-xs text-slate-500">
            Engine v1.1.0. {UJI_LULUS} uji otomatis lulus. Dibangun untuk konteks PIDI
            DIGDAYA Bank Indonesia.
          </p>
        </div>
      </section>

      {/* Final CTA */}
      <section className="px-6 py-16">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="text-2xl md:text-3xl font-semibold">
            Coba sekarang, tanpa membuat akun.
          </h2>
          <div className="mt-6 flex flex-col sm:flex-row items-center justify-center gap-3">
            <GuestCta className={primaryCta}>Buka Dashboard sebagai Tamu</GuestCta>
            <Link href="/login" className={secondaryCtaOnDark}>
              Punya akun dinas? Masuk di sini.
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-white/20 px-6 py-6 text-center text-xs text-white/60">
        AgriFlow · Neraca pangan Jawa Timur · Data BPS, PIHPS, IPM
      </footer>
    </main>
  );
}
