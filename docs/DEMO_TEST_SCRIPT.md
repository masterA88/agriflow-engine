# Demo test script: 10 questions, expected answers, and how to run them

Author: Hilmi (https://master-hilmi.vercel.app/)
Date: 2026-09-11

Every expected answer below was transcribed from a live run against real Gemini and real engine data on 2026-09-11, not written from intuition. The runner that produced them is `tools/demo_question_set.py`, so the set can be re-run after any change.

Configuration under test: `LLM_PRIMARY=gemini`, `GEMINI_MODEL=gemini-3.5-flash-lite`, OpenAI second tier on `gpt-5.6-luna`, keyword mock third. All 11 turns came back inside the 7.5 second deadline with `agriflow_status: ok`, so none needed the holding-message path.

**Confirmed against production on 2026-09-11.** Nine of these questions were re-run against the live Hugging Face Space after deployment, and all nine returned `ok` with the correct tool and the numbers below. Measured from an external client the turns took 4.8 to 7.9 seconds, against 1.9 to 3.2 locally. The extra is the Space's cpu-basic hardware plus network round trip, and it eats most of the margin under ManyChat's 10 second ceiling, so expect the occasional `pending` in real use even though none occurred in this run.

## How to run them, three ways

Do these in order. Each one rules out a different failure, and only the last needs ManyChat.

### A. Local, no WhatsApp, no ManyChat (do this first)

The fastest way to prove the brain works before touching any vendor setup.

PowerShell (this repo lives on Windows, so this is the one you want):

```powershell
$env:MOCK_MODE="false"; python tools/demo_question_set.py
```

Bash or Git Bash:

```bash
MOCK_MODE=false python tools/demo_question_set.py
```

Note that `VAR=value command` is bash syntax and is a parse error in PowerShell, which reports `The term 'MOCK_MODE=false' is not recognized`. PowerShell sets an environment variable with `$env:NAME="value"` as its own statement first.

It prints one block per question with the elapsed time, the tools called, and the answer, then writes `.tmp/demo_questions_run.json`. Compare against the table below. This needs nothing but `whatsapp_bot/.env`.

### B. Local, over real HTTP, exactly the request ManyChat will send

This proves the webhook, the shared-secret header, and the JSON contract, which part A skips.

Start the server in one PowerShell window:

```powershell
$env:MOCK_MODE="false"; $env:RATE_LIMIT_ENABLED="false"
python -m uvicorn whatsapp_bot.server:app --host 127.0.0.1 --port 8098
```

In a second window, read the secret straight out of the env file rather than retyping it, then post a question. Note that `curl` in Windows PowerShell is an alias for `Invoke-WebRequest` and does not accept curl's flags, so use `Invoke-RestMethod`:

```powershell
$secret = (Select-String -Path whatsapp_bot\.env -Pattern '^MANYCHAT_WEBHOOK_SECRET=').Line -replace '^MANYCHAT_WEBHOOK_SECRET=', ''

$body = @{
  subscriber_id   = 'wa-test-1'
  phone           = ''
  first_name      = 'Budi'
  last_input_text = 'Berapa harga cabai rawit di Kabupaten Kediri?'
} | ConvertTo-Json

Invoke-RestMethod -Uri http://127.0.0.1:8098/manychat/webhook -Method Post `
  -ContentType 'application/json' `
  -Headers @{ 'X-AgriFlow-Key' = $secret } `
  -Body $body -TimeoutSec 60
```

The same thing in Git Bash:

```bash
SECRET=$(grep '^MANYCHAT_WEBHOOK_SECRET=' whatsapp_bot/.env | cut -d= -f2-)

curl -s -X POST http://127.0.0.1:8098/manychat/webhook \
  -H "Content-Type: application/json" \
  -H "X-AgriFlow-Key: $SECRET" \
  -d '{"subscriber_id":"wa-test-1","phone":"","first_name":"Budi","last_input_text":"Berapa harga cabai rawit di Kabupaten Kediri?"}'
```

A correct response looks like this, verified on 2026-09-11:

```json
{
  "agriflow_reply": "Harga cabai rawit di Kabupaten Kediri berdasarkan neraca pangan BPS adalah Rp30.750 per kg (merupakan wilayah surplus dengan harga produsen). Data ini mengacu pada neraca BPS.",
  "agriflow_status": "ok",
  "agriflow_lang": "id",
  "agriflow_intent": "get_price",
  "agriflow_token": ""
}
```

Send the same request without the `X-AgriFlow-Key` header and it must return **401**. In PowerShell that surfaces as a thrown exception rather than a return value, so catch it:

```powershell
try   { Invoke-RestMethod -Uri http://127.0.0.1:8098/manychat/webhook -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 20 | Out-Null
        Write-Output "got 200 with no header, THIS IS WRONG" }
catch { Write-Output "rejected with $($_.Exception.Response.StatusCode.value__), which is correct" }
```

If it returns 200 without the header, stop and fix that before deploying anything. Both of these were verified working on 2026-09-11.

### C. Real WhatsApp

Only possible once all of these are true, and none of them are today:

1. ManyChat Pro is purchased and a WhatsApp number is connected (`docs/SETUP_MANYCHAT_LLM.md` section 4).
2. The HF Space is redeployed with this code and these secrets: `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-3.5-flash-lite`, `OPENAI_API_KEY`, `LLM_PRIMARY=gemini`, `MANYCHAT_API_TOKEN`, `MANYCHAT_WEBHOOK_SECRET`, `MOCK_MODE=false`.
3. The ManyChat flow is built (section 5), pointing its External Request at `https://masteraaa123-agriflow-api.hf.space/manychat/webhook` with the `X-AgriFlow-Key` header.

Then, from a real phone, not ManyChat's Test mode, because response mapping does not run in preview:

1. Message the connected number once to open the conversation.
2. Send Q1 through Q10 below, one at a time, waiting for each reply before sending the next. Sending them in a burst can trip the Gemini free tier's per-minute limit and you will get apology replies that look like bugs.
3. For each, check the three pass criteria in the table: the right tool ran, the number matches, and the language came back correct.
4. Keep the HF Space logs open in a browser tab while you do it. Every turn logs one line. A 401 means the header secret does not match the Space secret.

Watch for two specific things during the run:

- **A holding message followed by a second message.** That is the `pending` path and is correct behaviour, not a failure, but it should be rare now. If most turns do it, latency has regressed.
- **The fixed apology line** ("Maaf, saya sedang tidak bisa mengambil data"). That means both providers failed. Check the Space logs for `llm.gemini_tools_failed` and `llm.openai_tools_failed`.

## The 10 questions

Prices below come from the BPS balance, which holds one producer price and one consumer price per commodity for the whole province. Two kabupaten on the same side of the balance therefore show the same number. That is the data, not a bug, but avoid asking about two surplus kabupaten back to back in front of an audience, because identical figures look invented. Use Q5 for anything that needs to vary by city.

### Q1. Harga, Indonesian

**Ask:** Berapa harga cabai rawit di Kabupaten Kediri?
**Tool:** `get_price`
**Expect:** Rp30.750 per kg, described as producer price because Kediri is a surplus area, and explicitly attributed to the BPS 2022 balance.
**Fails if:** it dates the price to September 2026. That was a real bug, fixed on 2026-09-11 by making `get_price` carry its own reference year. Its return would mean the fix regressed.

### Q1b. Follow-up, tests conversation memory

**Ask, immediately after Q1:** Kalau di Malang bagaimana?
**Tool:** `get_price`
**Expect:** Rp30.750 per kg for Kabupaten Malang, having carried "cabai rawit" over from Q1 without being told again.
**Fails if:** it asks which commodity you mean. That means session memory is not persisting.

### Q2. Surplus by commodity, Indonesian

**Ask:** Kabupaten mana saja yang surplus bawang merah?
**Tool:** `get_surplus_deficit`
**Expect:** Nganjuk named first or largest at roughly 190.610 ton, followed by Probolinggo, Malang, Sampang, Bojonegoro. Seventeen areas in total.

### Q3. Selling side, Indonesian

**Ask:** Saya punya 20 ton cabai rawit di Kediri, siapa yang beli?
**Tool:** `find_buyers`
**Expect:** Kota Kediri named as the matched buyer. A fuller answer also gives the requirement volume, distance around 22 km, and a price gap around Rp10.250/kg.

### Q4. Buying side, Indonesian

**Ask:** Saya butuh 50 ton bawang merah untuk Surabaya, siapa pemasoknya?
**Tool:** `find_suppliers`
**Expect:** Sampang named as the main supplier, distance about 80,8 km.

### Q5. Forecast, Indonesian

**Ask:** Prediksi harga cabai rawit di Surabaya bulan depan berapa?
**Tool:** `get_forecast`
**Expect:** A point forecast around Rp52.153 per kg with a wide P10 to P90 band starting near Rp34.925, and a note that the forecast came from TimesFM 2.0 generated 3 September 2026.
**Acceptable variance:** the upper bound moves depending on which horizon day the model quotes, seen as both Rp71.686 and Rp74.238. Judge this one on the point estimate and the presence of a band, not on the exact ceiling.
**Note:** this tool uses the real daily price series, so it genuinely differs by city. Use it, not Q1, if you want to show variation between places.

### Q6. Anomalies, Indonesian

**Ask:** Anomali harga apa saja yang terjadi tahun ini?
**Tool:** `get_anomalies` with a `since` date
**Expect:** 2026 anomalies, such as a bawang putih spike of about 57% in Lumajang (Rp33.000/kg, July 2026) and a beras medium spike of about 5% in Sidoarjo (Rp13.650/kg, August 2026).
**Ask it this way on purpose.** Phrased vaguely as "akhir-akhir ini" the model picks a wide window and can answer with something from 2024, because without a date filter the tool ranks by anomaly score across history back to 2020. Saying "tahun ini" gets a current answer.

### Q7. Scenario simulation, Indonesian

**Ask:** Apa dampaknya kalau Gunung Semeru erupsi?
**Tools:** `list_presets` then `run_whatif`, two calls chained
**Expect:** Lumajang becomes unreachable for food logistics, provincial coverage falls from about 78,6% to 78%, and roughly 3.127,6 tons go undelivered.
**Note:** the impact is deliberately modest. If a judge calls it small, that is the honest answer for a single-kabupaten disruption, and the interesting part is that the engine re-solves and quantifies it at all.

### Q8. Data provenance, Indonesian

**Ask:** Data AgriFlow ini per tanggal berapa?
**Tool:** `get_data_freshness`
**Expect:** BPS balance 2022, IPM 2024, price history to 2 September 2026, anomaly scan and forecasts refreshed September 2026.
**This is the question to have ready for a sceptical judge.** It is also the cheapest one to run.

### Q9. Harga, Javanese

**Ask:** Regane bawang abang ing Nganjuk pinten?
**Tools:** `list_commodities` then `get_price`
**Expect:** An answer **in Javanese**, Rp24.375 per kg, Nganjuk described as a surplus area, plus a caveat that this is balance data rather than today's market price.
**Fails if:** the reply comes back in Indonesian. The two tool calls are expected and correct: the model looks up the commodity list to map "bawang abang" onto `bawang_merah`.

### Q10. Harga, Javanese, different city

**Ask:** Lombok ing Suroboyo regane piro saiki?
**Tools:** `list_commodities` then `get_price`
**Expect:** An answer **in Javanese**, Rp41.000 per kg for Kota Surabaya. The higher figure is correct: Surabaya is a deficit area, so it gets the consumer price rather than the producer price.
**Fails if:** it quotes Rp30.750. That would mean it applied the surplus-side price to a deficit city.

## Pass criteria before pushing

Treat the set as passing when all of these hold on a real phone:

| Check | Threshold |
|---|---|
| Right tool called | 10 of 10 |
| Number matches this sheet | 10 of 10 |
| Javanese questions answered in Javanese | 2 of 2 |
| Follow-up keeps context (Q1b) | passes |
| Answers inside the deadline, `status: ok` | 8 of 10 or better |
| Fixed apology line | never |

A `pending` holding message on one or two turns is acceptable. The apology line is not, on any turn.
