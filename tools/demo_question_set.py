"""
Run the demo question set through the real orchestrator and print a table of
what the bot actually answered, so the expected answers in
docs/DEMO_TEST_SCRIPT.md are transcribed from live output rather than guessed.

    MOCK_MODE=false python tools/demo_question_set.py

Paced at PACE_SECONDS between questions because the Gemini free tier is about
15 requests per minute and each question costs one call per tool round trip
plus one for the final answer.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from whatsapp_bot.config import settings            # noqa: E402
from whatsapp_bot.manychat import ManyChatWebhookRequest  # noqa: E402
from whatsapp_bot.orchestrator import Orchestrator   # noqa: E402

PACE_SECONDS = 4.0

# (id, subscriber, language, question, which tool we expect, what to check)
QUESTIONS = [
    ("Q1", "demo-a", "id", "Berapa harga cabai rawit di Kabupaten Kediri?",
     "get_price", "Rp30.750/kg, labelled as BPS 2022, Kediri named as surplus"),
    ("Q2", "demo-a", "id", "Kalau di Malang bagaimana?",
     "get_price", "carries 'cabai rawit' over from Q1 without being told again"),
    ("Q3", "demo-b", "id", "Kabupaten mana saja yang surplus bawang merah?",
     "get_surplus_deficit", "Nganjuk first at about 190.610 ton, then Probolinggo"),
    ("Q4", "demo-b", "id", "Saya punya 20 ton cabai rawit di Kediri, siapa yang beli?",
     "find_buyers", "names real matched buyers with volume and distance"),
    ("Q5", "demo-c", "id", "Saya butuh 50 ton bawang merah untuk Surabaya, siapa pemasoknya?",
     "find_suppliers", "ranked suppliers, says which were actually chosen"),
    ("Q6", "demo-c", "id", "Prediksi harga cabai rawit di Surabaya bulan depan berapa?",
     "get_forecast", "a forecast with a range, and says the model that produced it"),
    ("Q7", "demo-d", "id", "Ada anomali harga akhir-akhir ini?",
     "get_anomalies", "lists detected spikes or drops with commodity and city"),
    ("Q8", "demo-d", "id", "Apa dampaknya kalau Gunung Semeru erupsi?",
     "run_whatif", "a real scenario result, Lumajang isolated"),
    ("Q9", "demo-e", "id", "Data AgriFlow ini per tanggal berapa?",
     "get_data_freshness", "BPS 2022, price history to 2026-09-02"),
    ("Q10", "demo-f", "jv", "Regane bawang abang ing Nganjuk pinten?",
     "get_price", "answers IN JAVANESE, Rp24.375 saben kg"),
    ("Q11", "demo-f", "jv", "Lombok ing Suroboyo regane piro saiki?",
     "get_price or get_price_history", "answers IN JAVANESE about cabai in Surabaya"),
]


async def main() -> None:
    print("primary=%s  model=%s  deadline=%ss\n" % (
        settings.llm_primary, settings.gemini_model, settings.manychat_deadline_seconds))
    orch = Orchestrator()
    rows = []
    for qid, sub, lang, question, expect_tool, expect_answer in QUESTIONS:
        t0 = time.time()
        try:
            resp = await orch.handle(ManyChatWebhookRequest(
                subscriber_id=sub, phone="", first_name="Demo", last_input_text=question))
            dt = time.time() - t0
            row = {"id": qid, "lang_asked": lang, "question": question,
                   "expect_tool": expect_tool, "expect_answer": expect_answer,
                   "seconds": round(dt, 1), "status": resp.agriflow_status,
                   "lang_got": resp.agriflow_lang, "tools": resp.agriflow_intent,
                   "reply": resp.agriflow_reply}
        except Exception as exc:  # a failed question is data too, keep going
            row = {"id": qid, "lang_asked": lang, "question": question,
                   "expect_tool": expect_tool, "expect_answer": expect_answer,
                   "seconds": round(time.time() - t0, 1), "status": "EXCEPTION",
                   "lang_got": "", "tools": "", "reply": "%s: %s" % (type(exc).__name__, exc)}
        rows.append(row)
        print("%-4s %5.1fs %-8s lang=%-3s tools=%-34s" % (
            row["id"], row["seconds"], row["status"], row["lang_got"], row["tools"]))
        print("     Q: %s" % row["question"])
        print("     A: %s\n" % row["reply"][:400].replace("\n", " "))
        time.sleep(PACE_SECONDS)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".tmp")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "demo_questions_run.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)

    within = sum(1 for r in rows if r["status"] == "ok")
    print("=" * 70)
    print("%d/%d returned inside the %ss deadline" % (within, len(rows), settings.manychat_deadline_seconds))
    print("wrote %s" % os.path.normpath(path))


if __name__ == "__main__":
    asyncio.run(main())
