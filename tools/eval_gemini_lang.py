"""Evaluate Gemini models on Indonesian and Javanese before pinning one for the bot.

Runs a fixed set of 30 user utterances (15 Indonesian, 15 Javanese in ngoko and
krama) through one or more Gemini models with the AgriFlow assistant system
prompt, and prints every reply so a Javanese speaker can grade them. It also
records a rough automatic signal: whether the reply reuses the language of the
question (checked with a tiny word list, not a real classifier).

Usage:
    set GEMINI_API_KEY=...                       (or put it in .env)
    python tools/eval_gemini_lang.py
    python tools/eval_gemini_lang.py --models gemini-3.8-flash gemini-3.5-flash-lite
    python tools/eval_gemini_lang.py --out .tmp/eval_lang.md

The script never calls the AgriFlow API; the prompt tells the model that
prices come from tools it does not have here, so it should answer the
language part and say it needs the data tool for numbers. That is the
behaviour we want on the real bot as well.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SYSTEM = (
    "Kamu adalah asisten AgriFlow, platform ketahanan pangan Jawa Timur. "
    "Jawab dalam bahasa yang dipakai pengguna: bahasa Indonesia, atau bahasa Jawa "
    "(ngoko bila pengguna memakai ngoko, krama bila pengguna memakai krama). "
    "Angka harga, prakiraan, dan surplus/defisit hanya boleh berasal dari alat data; "
    "di sesi uji ini alat itu tidak tersedia, jadi katakan bahwa kamu perlu mengambil "
    "datanya dan jangan mengarang angka. Jawab singkat, maksimal tiga kalimat."
)

UTTERANCES = [
    # Indonesian
    ("id", "Harga cabai rawit di Malang hari ini berapa?"),
    ("id", "Kabupaten mana yang surplus bawang merah?"),
    ("id", "Prakiraan harga beras medium 30 hari ke depan di Surabaya bagaimana?"),
    ("id", "Apa arti anomali harga di dashboard?"),
    ("id", "Kenapa Sampang dicocokkan dengan Bangkalan?"),
    ("id", "Kalau Semeru meletus, distribusi cabai berubah bagaimana?"),
    ("id", "Data kalian per tanggal berapa?"),
    ("id", "Saya petani telur di Blitar, mau jual ke mana?"),
    ("id", "Bedanya beras premium dan medium di data kalian apa?"),
    ("id", "Tolong ringkas kondisi bawang putih di Jawa Timur."),
    ("id", "Kuota gratis saya sisa berapa?"),
    ("id", "Bisa kirim rekomendasi distribusi daging ayam untuk Jember?"),
    ("id", "Apakah harga telur sedang naik di Kediri?"),
    ("id", "Sumber data harga kalian dari mana?"),
    ("id", "Bagaimana cara berlangganan versi PRO?"),
    # Javanese ngoko
    ("jv", "Rega lombok rawit ing Malang dina iki pira?"),
    ("jv", "Kabupaten endi sing surplus brambang?"),
    ("jv", "Piye prakiraan rega beras medium 30 dina ngarep ing Surabaya?"),
    ("jv", "Anomali rega iku apa tegese?"),
    ("jv", "Ngapa Sampang dijodhokake karo Bangkalan?"),
    ("jv", "Yen Semeru njeblug, distribusi lombok owah piye?"),
    ("jv", "Data sampeyan per tanggal pira?"),
    ("jv", "Aku petani endhog ing Blitar, arep adol menyang endi?"),
    # Javanese krama
    ("jv", "Reginipun lombok rawit ing Malang dinten punika pinten, nggih?"),
    ("jv", "Kabupaten pundi ingkang surplus brambang?"),
    ("jv", "Kadospundi prakiraan regi wos medium 30 dinten ngajeng ing Surabaya?"),
    ("jv", "Menapa tegesipun anomali regi wonten dashboard?"),
    ("jv", "Sumber data regi panjenengan saking pundi?"),
    ("jv", "Kula petani tigan ing Blitar, badhe sade dhateng pundi?"),
    ("jv", "Kadospundi caranipun langganan versi PRO?"),
]

# Crude language cue lists; enough to flag a reply that switched language.
JV_CUES = {"ing", "iki", "pira", "piye", "endi", "sampeyan", "panjenengan", "nggih",
           "kula", "kadospundi", "pundi", "menapa", "dinten", "regi", "rega", "wonten",
           "saking", "dhateng", "arep", "ora", "mboten", "lombok", "brambang"}
ID_CUES = {"yang", "di", "ini", "berapa", "bagaimana", "mana", "anda", "kamu", "saya",
           "tidak", "harga", "data", "untuk", "dengan", "adalah", "hari"}


def guess_lang(text: str) -> str:
    words = {w.strip(".,?!:;()\"'").lower() for w in text.split()}
    jv = len(words & JV_CUES)
    idn = len(words & ID_CUES)
    if jv == 0 and idn == 0:
        return "?"
    return "jv" if jv > idn else "id"


def load_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "")
    if key:
        return key
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("GEMINI_API_KEY not set (env var or .env).")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["gemini-3.8-flash", "gemini-3.5-flash-lite"])
    ap.add_argument("--out", default=None, help="write a markdown report here")
    ap.add_argument("--sleep", type=float, default=1.0, help="seconds between calls (free tier RPM)")
    args = ap.parse_args()

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=load_key())
    lines = ["# Gemini language eval", "", f"Models: {', '.join(args.models)}", ""]
    for model in args.models:
        ok = 0
        lines += [f"## {model}", "", "| # | lang | utterance | reply | reply lang |", "|---|---|---|---|---|"]
        for i, (lang, text) in enumerate(UTTERANCES, 1):
            t0 = time.time()
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=text,
                    config=types.GenerateContentConfig(system_instruction=SYSTEM, temperature=0.2),
                )
                reply = (resp.text or "").strip().replace("\n", " ")
            except Exception as exc:  # noqa: BLE001
                reply = f"ERROR: {exc}"
            dt = time.time() - t0
            got = guess_lang(reply)
            same = got == lang
            ok += int(same)
            print(f"[{model}] {i:02d} {lang}->{got} {dt:4.1f}s | {text}\n    {reply}\n")
            lines.append(f"| {i} | {lang} | {text} | {reply.replace('|', '/')} | {got}{'' if same else ' (switched)'} |")
            time.sleep(args.sleep)
        summary = f"{model}: {ok}/{len(UTTERANCES)} replies kept the user's language (crude check)."
        print(summary)
        lines += ["", summary, ""]
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(lines), encoding="utf-8")
        print("wrote", args.out)


if __name__ == "__main__":
    main()
