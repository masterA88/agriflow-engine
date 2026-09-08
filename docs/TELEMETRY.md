# Behaviour telemetry: what is recorded, where it goes, how to turn it on

Author: Hilmi (https://master-hilmi.vercel.app/)
Date: 2026-09-08

Design source: `k1/research/agriflow-chatbot-architecture/drafts/spec-manychat-gemini-behaviour-2026-09-08.md`, sections 3 and 4. This file is the operator view.

## 1. What exists in the code

| Piece | Path | Role |
|---|---|---|
| Schema | `db/migrations/2026-09-08_behaviour_analytics.sql` | `intent_event`, `analytics_salt`, `intent_daily_agg`, view `demand_signal_export`, `chat_session` (WhatsApp memory, prepared, unused), rollup and retention functions, optional pg_cron schedule |
| Ingest | `whatsapp_bot/telemetry.py`, `POST /api/v1/events` in `server.py` | Validates batches (max 20), strips anything personal, computes the per-day token server side, writes to Postgres. Without `SUPABASE_DB_URL` it appends to a local JSONL spool and warns once |
| Insight | `GET /api/v1/insight/demand` | Reads only the SQL view `demand_signal_export` (web channel, cells with 5 or more unique users). 503 until the database is configured |
| Client SDK | `dashboard/app/lib/telemetry.ts` | `track()`, batching (10 events or 5 seconds), keepalive flush on tab hide, consent check on every call |
| Consent | `dashboard/app/components/ConsentBanner.tsx`, `/privasi` | Banner on first visit (Setuju / Tolak), privacy notice, withdrawal that takes effect immediately |
| Global capture | `dashboard/app/components/TelemetryProvider.tsx` | `page_view` on every route, `session_start` / `session_end`, `ui_click` on every button or link (label only) |
| Tests | `tests/test_telemetry.py` | 17 cases: validation, forbidden keys, day token, spool mode, endpoint contract |

## 2. What is recorded on the web

Typed events with codes, ids and counts, never free text:

- `page_view` (path), `session_start` (path, viewport), `session_end` (duration)
- `ui_click` (tag, button label truncated to 40 characters, path, link target path)
- `tab_view` (tab), `commodity_pick` (commodity, tab), `kabupaten_pick` (kabupaten_id, commodity, surface: beranda, peta, distribusi)
- `forecast_view`, `anomaly_view` (commodity, kabupaten_id, method, counts)
- `explain_view` (commodity, deficit kabupaten), `simulate_run` (presets, bbm_pct, match count)
- `download` (commodity or all, kind), `notification_click` (category, target tab), `faq_search` (query length and result count only)
- `optin` when consent is given

Every batch carries `session_id` (a per-tab UUID), `signed_in`, `consent_version` and `app_version`. The server turns the session id (or the signed-in user id) into `day_token = HMAC-SHA256(subject, salt_of_today)`; the salt rotates daily and the database deletes salts older than two days, so activity cannot be linked across days.

The same table takes `channel = 'whatsapp'` rows later; those never enter `demand_signal_export`.

## 3. Turning on durable storage (Supabase)

Until this is done the API spools events to `data/telemetry_spool.jsonl` on the host. On the Hugging Face Space that disk is ephemeral, so spooled events are lost on restart. Do this on the day the code goes live:

1. The Supabase project exists: `agriflow`, ref `cfvecymrgjqyqhflwucf`, region ap-southeast-1 (Singapore), free tier, created 2026-09-08.
2. The migration is already applied there (three migrations via the Supabase MCP; pg_cron and pgcrypto enabled; the four daily jobs are scheduled). For a fresh project, run it once: Either paste `db/migrations/2026-09-08_behaviour_analytics.sql` into the SQL editor, or:

   ```
   psql "$SUPABASE_DB_URL" -f db/migrations/2026-09-08_behaviour_analytics.sql
   ```

   The file is idempotent. It enables `pgcrypto`, and schedules the daily rollup, purge and salt rotation if `pg_cron` is enabled (Database, Extensions, pg_cron). Without pg_cron, call `SELECT rollup_intent_daily(2);` and `SELECT purge_intent_events(90);` from any daily job.
3. Set the database password (Project Settings, Database, Reset database password; the MCP-created project never showed one). Then open Connect at the top of the dashboard, pick **Session pooler** (IPv4; the direct `db.<ref>.supabase.co` host is IPv6-only on the free tier and the Hugging Face Space cannot reach it), copy the URI, which looks like `postgresql://postgres.cfvecymrgjqyqhflwucf:[PASSWORD]@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres`, and set it as `SUPABASE_DB_URL` on the Hugging Face Space (Settings, Variables and secrets, secret). The tables have RLS enabled with no policies, so `anon` and `authenticated` cannot read them, by design; only this connection can.
4. Restart the Space. The first `POST /api/v1/events` after that writes to Postgres; the log line `telemetry.recorded ... spool=False` confirms it.
5. Check: `SELECT event_type, count(*) FROM intent_event GROUP BY 1;` after clicking around the dashboard with consent accepted.

Local development: put the same `SUPABASE_DB_URL` in the repo root `.env`, or leave it empty to keep using the spool.

## 4. Consent and the legal boundary

- Nothing is sent before the visitor presses "Setuju". "Tolak" is equally easy, and the dashboard works either way. The cookie `agriflow_consent` stores the notice version (`2026-09-v1`) for 12 months; a new version shows the banner again.
- The notice names both purposes: improving the service, and aggregated demand-signal reports for government and institutions. Collecting for one purpose and selling under another is the failure the legal brief warns about.
- Withdrawal on `/privasi` takes effect immediately in the browser. Raw rows are deleted after 90 days; only the daily aggregate remains.
- WhatsApp-derived rows (even aggregated) may not be sold under Meta's Business Solution Terms. The view `demand_signal_export` enforces `channel = 'web'` and `unique_users >= 5` in SQL, and the insight endpoint reads nothing else.

## 5. Reading the data

Internal product analytics (both channels): `SELECT * FROM intent_daily_internal ORDER BY day DESC;`

Sellable signal (web only, k-anonymised): `SELECT * FROM demand_signal_export ORDER BY day DESC;` or `GET /api/v1/insight/demand?commodity=cabai_rawit&days=30` with a signed-in dashboard token.

The "Insight Permintaan" dashboard tab described in the spec (section 4.8) is not built yet; the endpoint it needs is.
