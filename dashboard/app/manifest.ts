import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "AgriFlow: Deteksi, Prediksi, Distribusi Pangan Jawa Timur",
    short_name: "AgriFlow",
    description: "Neraca surplus-defisit pangan per kabupaten, rekomendasi distribusi, prakiraan dan anomali harga.",
    start_url: "/",
    display: "standalone",
    background_color: "#5b7245",
    theme_color: "#5b7245",
    lang: "id",
    icons: [
      { src: "/agriflow-icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/agriflow-icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
