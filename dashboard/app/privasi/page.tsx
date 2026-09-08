import Link from "next/link";
import ConsentControls from "./ConsentControls";

export const metadata = { title: "Privasi · AgriFlow" };

// Public page (allowed through proxy.ts). Plain language, the same six points
// as the consent banner, plus the withdraw control.
export default function PrivasiPage() {
  return (
    <main className="min-h-screen bg-[#f6f8f3] text-zinc-800">
      <div className="mx-auto max-w-2xl px-6 py-12">
        <Link href="/" className="text-xs font-semibold text-[#5b7245]">← AgriFlow</Link>
        <h1 className="mt-4 text-2xl font-bold">Pemberitahuan privasi</h1>
        <p className="mt-2 text-sm text-zinc-600">Berlaku sejak 8 September 2026. Versi persetujuan: 2026-09-v1.</p>

        <section className="mt-8 space-y-4 text-sm leading-relaxed">
          <h2 className="text-base font-bold">Siapa yang mengendalikan data</h2>
          <p>AgriFlow, penyelenggara dashboard ini dan bot WhatsApp AgriFlow.</p>

          <h2 className="text-base font-bold">Apa yang dicatat</h2>
          <p>
            Di dashboard web: halaman dan tab yang dibuka, tombol yang diklik (label tombolnya saja), komoditas dan
            kabupaten/kota yang dipilih, prakiraan dan anomali yang dilihat, skenario simulasi yang dijalankan, dan
            berkas yang diunduh. Untuk pencarian di halaman Bantuan hanya panjang kata kunci dan jumlah hasil yang
            dicatat, bukan kata kuncinya. Tidak ada isi pesan, nama, nomor telepon, atau alamat email.
          </p>
          <p>
            Di WhatsApp (bila Anda memakai bot): jenis pertanyaan, komoditas dan wilayah yang ditanyakan, serta
            ringkasan topik percakapan untuk menjaga konteks. Isi percakapan WhatsApp tidak pernah dijual atau
            diturunkan ke dalam laporan apa pun, sesuai WhatsApp Business Solution Terms.
          </p>

          <h2 className="text-base font-bold">Untuk apa</h2>
          <ol className="list-decimal pl-5 space-y-1">
            <li>Memperbaiki layanan: mengetahui fitur mana yang berguna dan mana yang membingungkan.</li>
            <li>
              Menyusun laporan agregat sinyal permintaan pangan untuk instansi pemerintah dan lembaga. Laporan ini
              dibangun dari interaksi dashboard web yang sudah disetujui, neraca BPS, dan keluaran mesin pencocokan
              AgriFlow. Sel dengan kurang dari 5 pengguna unik tidak pernah ditampilkan.
            </li>
          </ol>

          <h2 className="text-base font-bold">Bagaimana identitas dilindungi</h2>
          <p>
            Setiap pengguna diwakili oleh token harian yang dihitung dengan kunci acak yang berganti setiap hari dan
            dihapus setelah dua hari, sehingga aktivitas tidak dapat ditautkan lintas hari. Data mentah disimpan 90
            hari, lalu hanya angka gabungan harian yang tersisa.
          </p>

          <h2 className="text-base font-bold">Hak Anda (UU PDP No. 27/2022)</h2>
          <p>
            Anda dapat menarik persetujuan kapan saja dengan tombol di bawah; sejak saat itu tidak ada lagi yang
            dicatat dari peramban ini. Permintaan akses atau penghapusan dapat dikirim lewat tautan kontak di
            halaman utama.
          </p>
        </section>

        <ConsentControls />
      </div>
    </main>
  );
}
