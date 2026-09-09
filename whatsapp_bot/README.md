# AgriFlow WhatsApp Bot — M2 Milestone

Twilio WhatsApp webhook + Gemini RAG wrapper around the AgriFlow matching engine.

Implements the **M2 milestone** from `docs/AgriFlow_v10.md` Section 11 (Week 5-6): "WhatsApp + Phone IVR demo Bahasa Indonesia". This package covers the WhatsApp half. Phone IVR is a separate scaffold.

## What it does

Three intents over the existing matching engine:

| Intent | Example message | What happens |
|---|---|---|
| `harga_lookup` | "Harga cabai di Malang?" | Looks up surplus/deficit price from `sample_data` for that kab + commodity |
| `cari_pembeli` | "Cari pembeli 50 ton cabai Kediri" | Runs `run_matching()`, filters to surplus from user's kab, returns top 3 buyers |
| `cari_penjual` | "Butuh 100 ton beras untuk Surabaya" | Runs `run_matching()`, filters to demand at user's kab, returns top 3 suppliers |
| `fallback` | Anything else | Gemini answers in Bahasa Indonesia with engine context as RAG |

## Quick start (mock mode — no API keys needed)

```bash
# From project root
pip install -r requirements.txt

# Sanity check via CLI
python -m whatsapp_bot.server "Harga cabai di Malang"
python -m whatsapp_bot.server "Cari pembeli cabai Kediri"
python -m whatsapp_bot.server "Halo apa kabar"

# Run the FastAPI server
uvicorn whatsapp_bot.server:app --reload --port 8000

# In another terminal — debug endpoint (no Twilio needed)
curl -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "Harga cabai di Malang"}'

# Check health
curl http://localhost:8000/health
```

In mock mode (`MOCK_MODE=true`, the default), Gemini is replaced by keyword heuristics and Twilio signature validation is skipped. The full pipeline runs end-to-end against the real matching engine — only the LLM is faked.

## Production setup (Twilio sandbox + Gemini)

### 1. Get credentials

- **Twilio**: sign up at [twilio.com](https://www.twilio.com), activate the WhatsApp Sandbox (Console → Messaging → Try it out → WhatsApp). You'll get an `Account SID`, `Auth Token`, and a sandbox `whatsapp:+1415...` number.
- **Gemini**: get a free API key at [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) (1500 req/day free tier).

### 2. Configure

```bash
cp whatsapp_bot/.env.example whatsapp_bot/.env
# Edit whatsapp_bot/.env — fill in TWILIO_* and GEMINI_API_KEY
# Set MOCK_MODE=false
```

### 3. Expose the webhook

Twilio needs a public URL to send messages to. Easiest for dev: [ngrok](https://ngrok.com).

```bash
# Terminal 1 — start the server
uvicorn whatsapp_bot.server:app --port 8000

# Terminal 2 — expose it
ngrok http 8000
# Copy the https://xxxx.ngrok-free.app URL
```

### 4. Wire up Twilio

In Twilio Console → Messaging → Try it out → WhatsApp Sandbox Settings:

- **WHEN A MESSAGE COMES IN** → `https://xxxx.ngrok-free.app/whatsapp` (POST)
- Save

### 5. Test

From your phone, join the sandbox by sending the join code shown in the Twilio console (e.g., `join red-elephant`) to the sandbox number. Then send:

```
Harga cabai di Malang
```

The bot should reply with current prices from sample data within 1-3 seconds.

## Architecture

```
┌──────────────┐    POST /whatsapp     ┌──────────────────────┐
│  WhatsApp    │ ────────────────────→ │  server.py (FastAPI) │
│  user        │ ←──── TwiML XML ───── │                      │
└──────────────┘                       └─────────┬────────────┘
                                                 │
                                                 ▼
                                       ┌──────────────────────┐
                                       │  intent.classify()   │
                                       │  (Gemini or mock)    │
                                       └─────────┬────────────┘
                                                 │
                                                 ▼
                                       ┌──────────────────────┐
                                       │  handlers.dispatch() │
                                       └─────────┬────────────┘
                                                 │
                          ┌──────────────────────┼──────────────────────┐
                          ▼                      ▼                      ▼
                   harga_lookup          cari_pembeli/penjual       fallback
                   (sample_data)         (run_matching engine)      (Gemini RAG)
```

## File map

| File | Responsibility |
|---|---|
| `server.py` | FastAPI app, webhook + debug endpoints, lifespan-loaded engine data |
| `intent.py` | Slot extraction + normalization (kab name → id, commodity name → code) |
| `handlers.py` | One function per intent, formats reply text |
| `gemini_client.py` | Gemini wrapper, falls back to `openai_client.py` on error, then a mock-mode keyword heuristic |
| `openai_client.py` | OpenAI wrapper, same contract as `gemini_client.py`; the fallback tier, unused unless `OPENAI_API_KEY` is set |
| `twilio_client.py` | TwiML response builder + signature validation |
| `config.py` | `Settings` dataclass loaded from env / .env |

## Testing

```bash
pytest tests/test_whatsapp_bot.py -v
```

All tests run in mock mode — no API keys needed, no network calls. Cover:
- Intent classification (4 intents)
- Handler dispatch (returns valid text for each intent)
- TwiML response shape + XML escaping
- FastAPI routes via `TestClient`

## What's NOT included (out of scope for M2 WhatsApp piece)

- **Voice notes** (STT/TTS) — that's M2's phone IVR piece, separate scaffold
- **Forecast queries** ("Prediksi harga minggu depan") — needs XGBoost/Prophet, not built yet
- **Bahasa Jawa** via Sahabat-AI — M4 milestone
- **Conversation memory** — current bot is stateless; follow-ups like "Bagaimana dengan Kediri?" don't carry context yet
- **Rate limiting / user auth** — fine for sandbox demo, needed before public launch

## Backend v1.1 additions

Two env knobs read by `server.py`, both with safe defaults so nothing needs to change to keep
current behaviour:

| Var | Default | What it controls |
|---|---|---|
| `ALLOCATOR` | `lp` | Layer 3 strategy. `lp` solves the exact capacitated LP transportation optimum (scipy HiGHS); `greedy` restores the v1.0 behaviour. |
| `ANOMALY_GATE_WINDOW_DAYS` | `14` | How recent a batch-detected anomaly must be to exclude a node from matching, via the unified Hampel/MAD gate in `analysis/anomaly_gate.py`. |

New endpoints served alongside the existing `/whatsapp`, `/chat`, and `/health`:
`/api/v1/meta` (data-as-of + engine/allocator version), `/api/v1/summary` (computed KPIs),
`/api/v1/report.csv`, `/api/v1/matches/explain` (per-match score breakdown), and
`POST /api/v1/simulate` (what-if scenario presets: semeru, banjir_sentra_padi, banjir_madura,
ramadan, bbm_20, impor, suramadu_tutup). See `tests/test_backend_v11.py` for the contract each
one is tested against.

## Cost guardrails

Per the v10 proposal Section 7:

- Twilio WhatsApp Business: ~Rp 200K/bln at sandbox, scales with conversation count
- Gemini 1.5 Flash: free up to 1500 req/day (well above pilot demand)
- Server: deploys on a single small instance (Rp 50-100K/bln on most VPS)

Total bot operating cost at pilot scale: **< Rp 500K/bulan** until volume justifies a paid tier.
