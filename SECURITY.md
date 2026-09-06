# Security Policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Send a report through
the contact form at https://master-hilmi.vercel.app/ with:

- the affected component (dashboard, API, WhatsApp bot, data pipeline),
- steps to reproduce, and
- the impact you believe it has.

You will get an acknowledgement within 3 working days and a fix or mitigation
plan within 14 days for anything rated high or critical. Please give us that
window before disclosing publicly.

## Scope

| Surface | Where it runs | Notes |
|---|---|---|
| Dashboard (Next.js) | Vercel, `agriflow-engine.vercel.app` | Login via Supabase Auth; guest mode shows public reference data only |
| API (FastAPI) | Hugging Face Spaces | `/api/v1/*`, `/chat`, `/whatsapp`, `/billing/*` |
| Database | Supabase Postgres | Row Level Security on every table, no PostgREST grants |

Out of scope: the public BPS and PIHPS datasets the engine reads, and rate
limits on the free demo deployment (they are deliberately generous for judging).

## Hardening reference

The production posture, the environment variables that control it, and the
audit that led to them are documented in `docs/SECURITY_AUDIT_2026-09.md`.
The short version for operators:

- Set `APP_ENV=production` on the API. The server refuses to start while any
  demo default (mock mode, unsigned Twilio webhooks, mock billing, unsalted
  phone hashes) is still active.
- Never set `NEXT_PUBLIC_DEV_LOGIN` outside a local `.env.local`.
- Keep `pip-audit` and `npm audit` green; both run in CI on every push.
