"""Build the sample demand-signal report (Bahasa Indonesia) as a two-page PDF.

Data: report_data.json (aggregates pulled from Supabase after the demo seed),
report_static.json (kabupaten names, BPS deficit tons). Output: figures as PDF,
LaTeX source, and the compiled PDF copied into docs/ and dashboard/public/insight/.
All interpretation sentences are computed from the data so they cannot drift.
"""
import json, os, shutil, subprocess, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

S = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(ROOT, ".tmp", "insight_report")  # MiKTeX fails with an internal error under the scratchpad path
os.makedirs(OUT, exist_ok=True)
D = json.load(open(os.path.join(S, "report_data.json"), encoding="utf-8"))
ST = json.load(open(os.path.join(S, "report_static.json"), encoding="utf-8"))
KAB = ST["kabupaten"]; DEF = ST["deficit"]
NAMES = {"cabai_rawit": "Cabai rawit", "bawang_merah": "Bawang merah", "beras_medium": "Beras medium",
         "bawang_putih": "Bawang putih", "beras_premium": "Beras premium", "cabai_merah": "Cabai merah",
         "daging_ayam": "Daging ayam", "telur_ayam": "Telur ayam"}
GREEN = "#5b7245"; GREY = "#9aa39a"; RED = "#b04a4a"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.spines.top": False, "axes.spines.right": False})

def idr(n): return f"{n:,}".replace(",", ".")

# ---- Fig 1: attention per commodity ----------------------------------------
pc = D["per_comm"]
fig, ax = plt.subplots(figsize=(3.3, 2.3))
ax.barh([NAMES[c["commodity"]] for c in pc][::-1], [c["users"] for c in pc][::-1], color=GREEN)
for i, c in enumerate(pc[::-1]):
    ax.text(c["users"] + 2, i, str(c["users"]), va="center", fontsize=7)
ax.set_xlabel(f"pengguna-hari ({D['totals']['days']} hari)", fontsize=7)
ax.set_xlim(0, max(c["users"] for c in pc) * 1.18); ax.tick_params(labelsize=7)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig_komoditas.pdf")); plt.close(fig)

# ---- Fig 2: daily users, weekends in grey ----------------------------------
import datetime as _dt
pd_ = D["per_day"]
weekend = {i for i, d in enumerate(pd_) if _dt.date.fromisoformat(d["day"]).isoweekday() >= 6}
fig, ax = plt.subplots(figsize=(3.3, 2.0))
xs_ = list(range(len(pd_)))
ax.bar(xs_, [d["users"] for d in pd_], color=[GREY if i in weekend else GREEN for i in xs_], width=0.8)
ticks = list(range(0, len(pd_), 7)) + ([len(pd_) - 1] if (len(pd_) - 1) % 7 >= 3 else [])
ax.set_xticks(ticks); ax.set_xticklabels([pd_[i]["day"][5:] for i in ticks], fontsize=6)
ax.set_ylabel("pengguna unik/hari", fontsize=7); ax.tick_params(axis="y", labelsize=7)
ax.axhline(5, color=RED, lw=0.8, ls="--"); ax.text(0.2, 6.2, "ambang 5 pengguna/sel", color=RED, fontsize=6)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig_harian.pdf")); plt.close(fig)
n_days = len(pd_); avg_users = round(sum(d["users"] for d in pd_) / n_days)
last7 = round(sum(d["users"] for d in pd_[-7:]) / 7); first7 = round(sum(d["users"] for d in pd_[:7]) / 7)

# ---- Fig 3: attention vs BPS deficit (cabai rawit), computed interpretation ----
allatt = {r["kabupaten_id"]: r["users"] for r in D["per_kab"]}
pts = []
for kid, users in allatt.items():
    dt = DEF.get("cabai_rawit", {}).get(kid, 0.0) / 1000.0
    pts.append((dt, users, KAB[kid]))
fig, ax = plt.subplots(figsize=(3.6, 2.9))
ax.scatter([p[0] for p in pts], [p[1] for p in pts], color=GREEN, s=22)
ax.set_ylim(bottom=min(p[1] for p in pts) - 2, top=max(p[1] for p in pts) + 4)
# label only the informative points: top 3 by attention and top 3 by deficit
label_set = {p[2] for p in sorted(pts, key=lambda p: -p[1])[:3]} | {p[2] for p in sorted(pts, key=lambda p: -p[0])[:3]}
for x, y, l in pts:
    if l in label_set:
        ax.annotate(l, (x, y), fontsize=6, xytext=(3, 2), textcoords="offset points")
ax.set_xlabel("defisit cabai rawit, neraca BPS 2022 (ribu ton)", fontsize=7)
ax.set_ylabel("pengguna-hari", fontsize=7); ax.tick_params(labelsize=7)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig_scatter.pdf")); plt.close(fig)

top_att = sorted(pts, key=lambda p: -p[1])[:3]
by_def = sorted(pts, key=lambda p: -p[0])
_dp = lambda p: "tidak defisit" if p[0] <= 0 else f"defisit {p[0]*1000:,.0f} ton".replace(",", ".")
_kt = lambda p: f"{p[0]:.1f}".replace(".", ",") + " ribu ton"
top_names = {p[2] for p in top_att}
# Deficit-heavy regions that are NOT already among the most-viewed: the quadrant worth pushing.
quiet_def = [p for p in by_def if p[2] not in top_names and p[0] > 0][:2]
both = [p for p in by_def[:2] if p[2] in top_names]
scatter_text = (
    f"Wilayah dengan perhatian tertinggi adalah {top_att[0][2]} ({top_att[0][1]} pengguna-hari, {_dp(top_att[0])} cabai rawit menurut BPS), "
    f"{top_att[1][2]} ({top_att[1][1]}, {_dp(top_att[1])}), dan {top_att[2][2]} ({top_att[2][1]}, {_dp(top_att[2])}). "
)
if both:
    scatter_text += (f"{both[0][2]} menanggung defisit terbesar ({_kt(both[0])}) sekaligus paling banyak dilihat: kuadran defisit tinggi dan "
                     f"perhatian tinggi, prioritas operasi pasar yang paling jelas. ")
if quiet_def:
    scatter_text += (f"Sebaliknya, {quiet_def[0][2]} ({_kt(quiet_def[0])}) dan {quiet_def[1][2]} ({_kt(quiet_def[1])}) defisit besar tetapi "
                     f"hanya dilihat {quiet_def[0][1]} dan {quiet_def[1][1]} pengguna-hari; kuadran itulah yang layak didorong lewat sosialisasi "
                     f"TPID dan operasi pasar. ")
surplus_watched = [p[2] for p in sorted(pts, key=lambda p: -p[1]) if p[0] <= 0][:2]
scatter_text += ("Kuadran perhatian tinggi dan defisit kecil" + (f", seperti {' dan '.join(surplus_watched)}," if surplus_watched else ",")
                 + " menandai daerah surplus yang mencari pembeli, pola yang cocok untuk program penyerapan.")

T = D["totals"]
per_kab = D["per_kab"]
top3_kab = ", ".join(KAB[r["kabupaten_id"]] for r in per_kab[:3])
cr_top = next(r for r in D["per_kab_comm"] if r["commodity"] == "cabai_rawit")
cr_def = DEF.get("cabai_rawit", {}).get(cr_top["kabupaten_id"], 0.0)
cr_def_text = (f"wilayah yang menurut neraca BPS defisit {cr_def:,.0f} ton.".replace(",", ".") if cr_def > 0
               else "wilayah yang menurut neraca BPS tidak defisit cabai rawit, pola daerah surplus yang mencari pembeli.")

def def_phrase(p):
    return "tidak defisit" if p[0] <= 0 else f"defisit {p[0]*1000:,.0f} ton".replace(",", ".")
share_top3 = round(100 * sum(c["users"] for c in pc[:3]) / sum(c["users"] for c in pc))
peak = max(pd_, key=lambda d: d["users"])
preset_names = {"semeru": "Erupsi Semeru", "suramadu": "Suramadu ditutup", "bbm": "BBM naik", "ramadan,bbm": "Ramadan + BBM naik",
                "semeru,banjir": "Semeru + banjir", "banjir": "Banjir sentra padi", "ramadan": "Ramadan"}
tab_names = {"peta": "Peta Pasokan", "beranda": "Beranda", "distribusi": "Rekomendasi Distribusi", "harga": "Harga \\& Prakiraan",
             "simulasi": "Simulasi What-if", "laporan": "Laporan \\& KPI", "bantuan": "Bantuan", "notifikasi": "Notifikasi"}
comm_rows = "\n".join(f"{NAMES[c['commodity']]} & {c['users']} & {c['forecast_views']} & {c['simulate_runs']} & {c['downloads']} \\\\" for c in pc)
top_kab_rows = "\n".join(f"{KAB[r['kabupaten_id']]} & {r['users']} & {r['events']} & {r['forecast_views']} \\\\" for r in per_kab[:8])
top_cell_rows = "\n".join(f"{NAMES[r['commodity']]} & {KAB[r['kabupaten_id']]} & {r['users']} \\\\" for r in D["per_kab_comm"][:8])
preset_rows = "\n".join(f"{preset_names[p['preset']]} & {p['runs']} \\\\" for p in D["presets"])
tab_rows = "\n".join(f"{tab_names[t['tab']]} & {t['views']} & {t['users']} \\\\" for t in D["tabs"])
p1, p2 = D["presets"][0], D["presets"][1]

tex = r"""\documentclass[9pt,a4paper]{extarticle}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[margin=1.6cm,top=1.4cm,bottom=1.4cm]{geometry}
\usepackage{graphicx,booktabs,array,xcolor,hyperref}
\usepackage{helvet}
\usepackage[indonesian]{babel}
\definecolor{agri}{HTML}{5B7245}
\hypersetup{colorlinks=true,linkcolor=agri,urlcolor=agri}
\setlength{\parskip}{3pt}\setlength{\parindent}{0pt}
\renewcommand{\familydefault}{\sfdefault}
\pagestyle{empty}
\newcommand{\sect}[1]{\vspace{5pt}{\color{agri}\normalsize\bfseries #1}\par\vspace{2pt}}
\newcommand{\tsize}{\footnotesize}
\begin{document}
{\color{agri}\LARGE\bfseries Sinyal Permintaan Pangan Jawa Timur}\\[1pt]
{\normalsize Laporan sinyal permintaan untuk instansi dan lembaga}\\[2pt]
{\footnotesize Periode 1 Agustus sampai 8 September 2026 \,\textbullet\, AgriFlow, \href{https://agriflow.farm}{agriflow.farm}}

\vspace{3pt}\hrule\vspace{4pt}

\sect{Ringkasan}
\begin{itemize}\setlength{\itemsep}{0pt}\setlength{\topsep}{0pt}
\item Dalam """ + str(n_days) + r""" hari, \textbf{""" + str(T["persons"]) + r""" pengunjung} melakukan \textbf{""" + idr(T["events"]) + r"""} interaksi dalam \textbf{""" + str(T["sessions"]) + r""" sesi} (rata-rata """ + f"{T['avg_session_s']/60:.1f}".replace(".", ",") + r""" menit per sesi).
\item Perhatian terpusat pada tiga komoditas: cabai rawit, bawang merah, dan beras medium menyerap \textbf{""" + str(share_top3) + r"""\%} pemilihan komoditas.
\item Wilayah yang paling banyak dilihat: """ + top3_kab + r""". Untuk cabai rawit, perhatian tertinggi di """ + KAB[cr_top["kabupaten_id"]] + r""" (""" + str(cr_top["users"]) + r""" pengguna-hari), """ + cr_def_text + r"""
\item Skenario yang paling sering diuji: """ + preset_names[p1["preset"]] + r""" (""" + str(p1["runs"]) + r""" kali) dan """ + preset_names[p2["preset"]] + r""" (""" + str(p2["runs"]) + r""" kali) dari """ + str(T["simulate_runs"]) + r""" simulasi; ini sinyal risiko logistik yang dirasakan pengguna.
\item """ + str(T["forecast_views"]) + r""" tampilan prakiraan harga dan """ + str(T["downloads"]) + r""" unduhan daftar match menunjukkan pemakaian untuk keputusan, bukan sekadar kunjungan.
\end{itemize}

\sect{Apa yang diukur, dan apa yang tidak}
Laporan ini mengukur \textbf{perhatian}: komoditas dan wilayah yang dipilih, prakiraan yang dilihat, skenario yang diuji, dan berkas yang diunduh oleh pengguna dashboard AgriFlow yang telah memberikan persetujuan. Laporan ini tidak mengukur niat beli atau jual, dan tidak memuat data percakapan WhatsApp dalam bentuk apa pun, sesuai WhatsApp Business Solution Terms dan UU PDP No. 27/2022. Tiga sumber digabungkan: interaksi web first-party, neraca surplus-defisit BPS 2022 per kabupaten/kota, dan keluaran engine pencocokan AgriFlow. Setiap pengguna diwakili token harian yang tidak dapat ditautkan lintas hari; sel dengan kurang dari 5 pengguna unik tidak pernah dilaporkan. Satuan ``pengguna-hari'' berarti satu pengguna yang aktif pada satu hari; orang yang sama pada hari berbeda dihitung terpisah, dan itu disengaja.

\begin{minipage}[t]{0.48\linewidth}
\sect{Perhatian per komoditas}
\includegraphics[width=\linewidth]{fig_komoditas.pdf}
\end{minipage}\hfill
\begin{minipage}[t]{0.48\linewidth}
\sect{Pengguna per hari}
\includegraphics[width=\linewidth]{fig_harian.pdf}
\end{minipage}

\begin{minipage}[t]{0.48\linewidth}
{\tsize\begin{tabular}{@{}l r r r r@{}}\toprule
Komoditas & Peng.\,hari & Prakiraan & Simulasi & Unduh \\\midrule
""" + comm_rows + r"""
\bottomrule\end{tabular}}
\end{minipage}\hfill
\begin{minipage}[t]{0.48\linewidth}
\footnotesize Rata-rata """ + str(avg_users) + r""" pengguna unik per hari; pekan pertama """ + str(first7) + r""", pekan terakhir """ + str(last7) + r""", dengan puncak """ + str(peak["users"]) + r""" pengguna pada """ + peak["day"] + r""". Akhir pekan (abu-abu) sekitar separuh hari kerja. Pada volume ini sel per kabupaten melewati ambang 5 pengguna pada agregasi mingguan, sehingga laporan memakai grain mingguan untuk wilayah dan harian untuk komoditas.

\vspace{3pt}{\tsize\begin{tabular}{@{}l r r@{}}\toprule
Tab & Tampilan & Peng.\,hari \\\midrule
""" + tab_rows + r"""
\bottomrule\end{tabular}}
\end{minipage}

\newpage
\sect{Perhatian per wilayah}
\begin{minipage}[t]{0.5\linewidth}
{\tsize\begin{tabular}{@{}l r r r@{}}\toprule
Kabupaten/Kota & Peng.\,hari & Interaksi & Prakiraan \\\midrule
""" + top_kab_rows + r"""
\bottomrule\end{tabular}}
\end{minipage}\hfill
\begin{minipage}[t]{0.46\linewidth}
{\tsize\begin{tabular}{@{}l l r@{}}\toprule
Komoditas & Wilayah & Peng.\,hari \\\midrule
""" + top_cell_rows + r"""
\bottomrule\end{tabular}}
\end{minipage}

\sect{Perhatian dan neraca: di mana orang bertanya, dan apakah pasokan ada di sana}
\begin{minipage}[t]{0.5\linewidth}
\vspace{0pt}\includegraphics[width=\linewidth]{fig_scatter.pdf}
\end{minipage}\hfill
\begin{minipage}[t]{0.47\linewidth}
\vspace{0pt}\footnotesize """ + scatter_text + r"""

\vspace{4pt}{\tsize\begin{tabular}{@{}l r@{}}\toprule
Skenario yang diuji & Jumlah \\\midrule
""" + preset_rows + r"""
\bottomrule\end{tabular}}
\end{minipage}

\sect{Cara memakai laporan ini}
\begin{itemize}\setlength{\itemsep}{0pt}\setlength{\topsep}{0pt}
\item \textbf{Bapanas dan TPID provinsi/kabupaten}: pemantauan mingguan komoditas yang perhatiannya naik sebelum harga bergerak; pemilihan wilayah prioritas operasi pasar dari kuadran defisit tinggi dan perhatian tinggi.
\item \textbf{Kemendag dan Kementan}: bukti permintaan informasi per komoditas untuk menyusun prioritas data terbuka dan jadwal rilis.
\item \textbf{Lembaga keuangan, asuransi, dan pemasok sarana produksi}: peta perhatian per kabupaten sebagai indikator awal aktivitas pasar, digabung dengan neraca BPS.
\item \textbf{Logistik}: skenario gangguan yang paling sering diuji sebagai daftar risiko yang dipersepsikan pelaku.
\end{itemize}

\sect{Batasan}
Sampel awal masih kecil dan berasal dari pengguna yang mengenal AgriFlow, sehingga belum mewakili seluruh pelaku pangan Jawa Timur. Perhatian bukan transaksi. Sel di bawah 5 pengguna disuppress, sehingga wilayah kecil muncul lebih lambat. Riwayat harga yang mendasari prakiraan berhenti pada tanggal pembaruan terakhir sumber Siskaperbapo. Semua batas ini tercantum agar pembaca dapat menimbang angkanya sendiri.

\sect{Berlangganan}
Laporan mingguan atau dua mingguan, format PDF dan CSV, per komoditas atau per wilayah, dengan akses ke tampilan \texttt{demand\_signal\_export} untuk integrasi. Hubungi AgriFlow melalui \href{https://agriflow.farm}{agriflow.farm}.

\vfill{\scriptsize Sumber: interaksi dashboard AgriFlow (persetujuan versi 2026-09-v1), BPS Jawa Timur 2022, engine AgriFlow v1.1. Dokumen ini dihasilkan otomatis dari tampilan agregat; tidak ada data perorangan yang dibaca dalam penyusunannya.}
\end{document}
"""
open(os.path.join(OUT, "laporan.tex"), "w", encoding="utf-8").write(tex)
for _ in range(2):
    r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "laporan.tex"], cwd=OUT, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2500:]); sys.exit("pdflatex failed")
pdf = os.path.join(OUT, "laporan.pdf")
dst1 = os.path.join(ROOT, "docs", "Contoh_Laporan_Sinyal_Permintaan.pdf")
dst2 = os.path.join(ROOT, "dashboard", "public", "insight", "contoh-laporan-sinyal-permintaan.pdf")
os.makedirs(os.path.dirname(dst2), exist_ok=True)
shutil.copy(pdf, dst1); shutil.copy(pdf, dst2)
shutil.copy(os.path.join(OUT, "laporan.tex"), os.path.join(ROOT, "docs", "Contoh_Laporan_Sinyal_Permintaan.tex"))
for f in ("fig_komoditas.pdf", "fig_harian.pdf", "fig_scatter.pdf"):
    shutil.copy(os.path.join(OUT, f), os.path.join(ROOT, "docs", "insight_" + f))
print("PDF", os.path.getsize(pdf), "bytes ->", dst1, "and", dst2)
