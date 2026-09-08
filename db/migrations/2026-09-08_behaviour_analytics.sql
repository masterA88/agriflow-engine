-- =============================================================================
-- AgriFlow: customer-behaviour analytics + chatbot session memory
-- Apply with:  psql "$SUPABASE_DB_URL" -f db/migrations/2026-09-08_behaviour_analytics.sql
-- Or paste into the Supabase SQL editor. Idempotent (IF NOT EXISTS / OR REPLACE).
--
-- Design source: k1/research/agriflow-chatbot-architecture/drafts/
--   spec-manychat-gemini-behaviour-2026-09-08.md, sections 3 and 4.
--
-- Two data stores that must never be the same rows:
--   intent_event   behaviour telemetry, both channels, keyed by a day_token
--                  that cannot be linked across days once the salt is gone.
--   chat_session   WhatsApp conversation memory, keyed by phone_hash, carries
--                  full PDP obligations. Prepared here; filled by the bot later.
--
-- The sold artefact is the VIEW demand_signal_export, which enforces in SQL
-- that only channel = 'web' rows with at least 5 unique users ever leave.
-- WhatsApp-derived data is excluded by Meta's Business Solution Terms.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;   -- gen_random_bytes for the daily salt
CREATE EXTENSION IF NOT EXISTS pg_cron;                            -- daily rollup, purge, salt rotation

-- Applied to Supabase project `agriflow` (ref cfvecymrgjqyqhflwucf, ap-southeast-1) on 2026-09-08
-- via the Supabase MCP as migrations enable_pg_cron_and_pgcrypto,
-- behaviour_analytics_and_chat_session, revoke_definer_functions_from_api_roles.

-- -----------------------------------------------------------------------------
-- 1. intent_event: one row per user action. No message text. No phone.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS intent_event (
    event_id        BIGSERIAL   PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    channel         TEXT        NOT NULL,
    event_type      TEXT        NOT NULL,
    intent          TEXT,
    commodity       TEXT,
    kabupaten_id    TEXT,
    detail          JSONB       NOT NULL DEFAULT '{}'::jsonb,
    day_token       CHAR(64)    NOT NULL,
    session_id      UUID,
    signed_in       BOOLEAN,
    consent_version TEXT        NOT NULL,
    app_version     TEXT,
    CONSTRAINT chk_ie_channel CHECK (channel IN ('whatsapp','web')),
    CONSTRAINT chk_ie_event_type CHECK (event_type IN (
        -- web + shared
        'page_view','session_start','session_end','ui_click',
        'tab_view','commodity_pick','kabupaten_pick','forecast_view','anomaly_view',
        'explain_view','simulate_run','download','notification_click','faq_search',
        -- whatsapp (prepared, unused until the bot lands)
        'bot_query','bot_clarify','bot_out_of_coverage',
        -- consent lifecycle
        'optin','optout')),
    -- Structural guarantee: free text never lands in detail.
    CONSTRAINT chk_ie_no_text CHECK (
        NOT (detail ? 'text') AND NOT (detail ? 'message') AND
        NOT (detail ? 'phone') AND NOT (detail ? 'query') AND
        NOT (detail ? 'email') AND NOT (detail ? 'name'))
);

CREATE INDEX IF NOT EXISTS idx_ie_ts    ON intent_event (ts);
CREATE INDEX IF NOT EXISTS idx_ie_dim   ON intent_event (channel, event_type, commodity, kabupaten_id);
CREATE INDEX IF NOT EXISTS idx_ie_token ON intent_event (day_token, ts);
CREATE INDEX IF NOT EXISTS idx_ie_sess  ON intent_event (session_id, ts);

ALTER TABLE intent_event ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON intent_event FROM PUBLIC;
REVOKE ALL ON intent_event FROM anon, authenticated;
-- No policies on purpose: only the service role (backend) reads or writes.

-- -----------------------------------------------------------------------------
-- 2. analytics_salt: daily-rotating HMAC salt for day_token. Two rows, ever.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics_salt (
    salt_date   DATE        PRIMARY KEY,
    salt        BYTEA       NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE analytics_salt ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON analytics_salt FROM PUBLIC;
REVOKE ALL ON analytics_salt FROM anon, authenticated;

-- Returns today's salt (Asia/Jakarta calendar day), creating it if missing,
-- and forgets anything older than two days so cross-day linkage stops being
-- computable. The backend calls this once per day per process.
CREATE OR REPLACE FUNCTION analytics_salt_today()
RETURNS BYTEA
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions
AS $$
DECLARE
    d DATE := (now() AT TIME ZONE 'Asia/Jakarta')::date;
    s BYTEA;
BEGIN
    INSERT INTO analytics_salt (salt_date, salt)
    VALUES (d, extensions.gen_random_bytes(32))
    ON CONFLICT (salt_date) DO NOTHING;
    DELETE FROM analytics_salt WHERE salt_date < d - 1;
    SELECT salt INTO s FROM analytics_salt WHERE salt_date = d;
    RETURN s;
END;
$$;
REVOKE ALL ON FUNCTION analytics_salt_today() FROM PUBLIC;
-- Supabase grants EXECUTE on public functions to the API roles by default;
-- SECURITY DEFINER maintenance functions must not be callable over /rest/v1/rpc.
REVOKE EXECUTE ON FUNCTION analytics_salt_today() FROM anon, authenticated;

-- -----------------------------------------------------------------------------
-- 3. intent_daily_agg: the non-personal rollup. Sentinel '' instead of NULL so
--    the primary key actually deduplicates.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS intent_daily_agg (
    day           DATE   NOT NULL,
    channel       TEXT   NOT NULL,
    event_type    TEXT   NOT NULL,
    intent        TEXT   NOT NULL DEFAULT '',
    commodity     TEXT   NOT NULL DEFAULT '',
    kabupaten_id  TEXT   NOT NULL DEFAULT '',
    event_count   INT    NOT NULL,
    unique_users  INT    NOT NULL,        -- COUNT(DISTINCT day_token)
    PRIMARY KEY (day, channel, event_type, intent, commodity, kabupaten_id)
);
ALTER TABLE intent_daily_agg ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON intent_daily_agg FROM PUBLIC;
REVOKE ALL ON intent_daily_agg FROM anon, authenticated;

-- Idempotent rollup over the last N days (default 2, so a late batch can
-- correct yesterday). Schedule daily at 02:15 WIB (pg_cron below, or the
-- backend's scripts/aggregate_intents.py once it exists).
CREATE OR REPLACE FUNCTION rollup_intent_daily(p_days INT DEFAULT 2)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE n INT;
BEGIN
    INSERT INTO intent_daily_agg (day, channel, event_type, intent, commodity, kabupaten_id,
                                  event_count, unique_users)
    SELECT (ts AT TIME ZONE 'Asia/Jakarta')::date,
           channel,
           event_type,
           COALESCE(intent, ''),
           COALESCE(commodity, ''),
           COALESCE(kabupaten_id, ''),
           COUNT(*),
           COUNT(DISTINCT day_token)
    FROM   intent_event
    WHERE  ts >= now() - make_interval(days => p_days)
    GROUP  BY 1,2,3,4,5,6
    ON CONFLICT (day, channel, event_type, intent, commodity, kabupaten_id)
    DO UPDATE SET event_count  = EXCLUDED.event_count,
                  unique_users = EXCLUDED.unique_users;
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END;
$$;
REVOKE ALL ON FUNCTION rollup_intent_daily(INT) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION rollup_intent_daily(INT) FROM anon, authenticated;

-- Retention: raw events live 90 days, then only the rollup remains.
CREATE OR REPLACE FUNCTION purge_intent_events(p_keep_days INT DEFAULT 90)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE n INT;
BEGIN
    DELETE FROM intent_event WHERE ts < now() - make_interval(days => p_keep_days);
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END;
$$;
REVOKE ALL ON FUNCTION purge_intent_events(INT) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION purge_intent_events(INT) FROM anon, authenticated;

-- -----------------------------------------------------------------------------
-- 4. demand_signal_export: the ONLY thing a B2G buyer ever reads.
--    Both conditions live here, in SQL, not in application code.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW demand_signal_export WITH (security_invoker = true) AS
SELECT day,
       channel,
       event_type,
       NULLIF(intent, '')       AS intent,
       NULLIF(commodity, '')    AS commodity,
       NULLIF(kabupaten_id, '') AS kabupaten_id,
       event_count,
       unique_users
FROM   intent_daily_agg
WHERE  unique_users >= 5          -- k-anonymity floor
  AND  channel = 'web';           -- WhatsApp excluded (Meta Business Solution Terms)

REVOKE ALL ON demand_signal_export FROM PUBLIC;
REVOKE ALL ON demand_signal_export FROM anon, authenticated;
-- When a reporting role exists: GRANT SELECT ON demand_signal_export TO agriflow_reporting;

-- Internal-only companion (both channels) for product analytics. Never exported.
CREATE OR REPLACE VIEW intent_daily_internal WITH (security_invoker = true) AS
SELECT day, channel, event_type,
       NULLIF(intent, '') AS intent, NULLIF(commodity, '') AS commodity,
       NULLIF(kabupaten_id, '') AS kabupaten_id, event_count, unique_users
FROM   intent_daily_agg;
REVOKE ALL ON intent_daily_internal FROM PUBLIC;
REVOKE ALL ON intent_daily_internal FROM anon, authenticated;

-- -----------------------------------------------------------------------------
-- 5. chat_session: WhatsApp conversation memory. Prepared now, written by the
--    ManyChat + Gemini orchestrator later. Keyed by phone_hash so the existing
--    subscription/quota tables join without change.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_session (
    phone_hash              CHAR(64)     PRIMARY KEY,
    manychat_subscriber_id  TEXT         NOT NULL UNIQUE,
    lang                    CHAR(2)      NOT NULL DEFAULT 'id',
    turns                   JSONB        NOT NULL DEFAULT '[]'::jsonb,   -- last 10, 24h clock
    rolling_summary         TEXT         NOT NULL DEFAULT '',            -- topic only, no prices
    slots                   JSONB        NOT NULL DEFAULT '{}'::jsonb,   -- commodity, kabupaten, ...
    quota_snapshot          JSONB        NOT NULL DEFAULT '{}'::jsonb,
    session_token           CHAR(43),
    session_token_prev      CHAR(43),
    consent_version         TEXT         NOT NULL DEFAULT 'none',
    opted_out_at            TIMESTAMPTZ,
    turns_updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    slots_updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_seen_at            TIMESTAMPTZ  NOT NULL DEFAULT now(),
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT chk_cs_lang CHECK (lang IN ('id','jv'))
);
CREATE INDEX IF NOT EXISTS idx_cs_subscriber ON chat_session (manychat_subscriber_id);
CREATE INDEX IF NOT EXISTS idx_cs_last_seen  ON chat_session (last_seen_at);
CREATE INDEX IF NOT EXISTS idx_cs_turns_ttl  ON chat_session (turns_updated_at);
ALTER TABLE chat_session ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON chat_session FROM PUBLIC;
REVOKE ALL ON chat_session FROM anon, authenticated;

-- Three clocks for chat_session, run daily with the rollup.
CREATE OR REPLACE FUNCTION expire_chat_sessions()
RETURNS TABLE (turns_cleared INT, slots_cleared INT, rows_deleted INT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE a INT; b INT; c INT;
BEGIN
    UPDATE chat_session SET turns = '[]'::jsonb, updated_at = now()
    WHERE turns <> '[]'::jsonb AND turns_updated_at < now() - interval '24 hours';
    GET DIAGNOSTICS a = ROW_COUNT;
    UPDATE chat_session SET slots = '{}'::jsonb, rolling_summary = '', updated_at = now()
    WHERE (slots <> '{}'::jsonb OR rolling_summary <> '') AND slots_updated_at < now() - interval '90 days';
    GET DIAGNOSTICS b = ROW_COUNT;
    DELETE FROM chat_session WHERE last_seen_at < now() - interval '180 days';
    GET DIAGNOSTICS c = ROW_COUNT;
    RETURN QUERY SELECT a, b, c;
END;
$$;
REVOKE ALL ON FUNCTION expire_chat_sessions() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION expire_chat_sessions() FROM anon, authenticated;

-- -----------------------------------------------------------------------------
-- 6. Optional scheduling with pg_cron (enable the extension in Supabase:
--    Database > Extensions > pg_cron). Times are UTC: 19:15 UTC = 02:15 WIB.
--    Safe to run this block even if pg_cron is absent: it is guarded.
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
        PERFORM cron.schedule('agriflow_rollup_intents',  '15 19 * * *', $c$SELECT rollup_intent_daily(2);$c$);
        PERFORM cron.schedule('agriflow_purge_events',    '30 19 * * *', $c$SELECT purge_intent_events(90);$c$);
        PERFORM cron.schedule('agriflow_expire_sessions', '45 19 * * *', $c$SELECT expire_chat_sessions();$c$);
        PERFORM cron.schedule('agriflow_salt_rotate',     '0 17 * * *',  $c$SELECT analytics_salt_today();$c$);
    END IF;
END $$;
