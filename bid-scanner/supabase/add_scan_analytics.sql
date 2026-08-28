-- FCU Bid Agent — scan analytics (funnel + per-source health)
-- Powers the /scanner dashboard. Run once in Supabase Dashboard → SQL Editor.

-- ============================================================
-- SCAN_RUN: one row per scanner run, full funnel breakdown
--   raw_found → geo_in/unknown/out → after_dedup → relevant → new
-- Supersedes scan_log (kept in parallel until the homepage widget moves over).
-- ============================================================
CREATE TABLE IF NOT EXISTS scan_run (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mode            text DEFAULT 'full',        -- full | planetbids | opengov | sam | ...
  started_at      timestamptz DEFAULT now(),
  finished_at     timestamptz,
  duration_secs   numeric,

  raw_found       int DEFAULT 0,              -- rows scraped before geo gate + dedup
  geo_in          int DEFAULT 0,
  geo_unknown     int DEFAULT 0,
  geo_out         int DEFAULT 0,              -- dropped by the geo gate
  after_dedup     int DEFAULT 0,
  dedup_removed   int DEFAULT 0,
  relevant        int DEFAULT 0,              -- is_relevant in the deduped set
  new_bids        int DEFAULT 0,              -- first seen this run
  updated_bids    int DEFAULT 0,              -- already known, last_seen bumped

  digest_sent     boolean DEFAULT false,
  error_summary   text
);

CREATE INDEX IF NOT EXISTS scan_run_started_idx ON scan_run(started_at DESC);

-- ============================================================
-- SCAN_SOURCE_STAT: per-source breakdown for one run
-- status: ok | empty | blocked | partial | error
-- portals_* are populated for PlanetBids only.
-- ============================================================
CREATE TABLE IF NOT EXISTS scan_source_stat (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scan_run_id     uuid REFERENCES scan_run(id) ON DELETE CASCADE,
  source          text NOT NULL,
  raw_count       int DEFAULT 0,
  kept_count      int DEFAULT 0,              -- survived the geo gate
  relevant_count  int DEFAULT 0,
  new_count       int DEFAULT 0,
  status          text DEFAULT 'ok',
  portals_total   int,
  portals_ok      int,
  portals_blocked int,
  note            text,
  duration_secs   numeric
);

CREATE INDEX IF NOT EXISTS scan_source_stat_run_idx    ON scan_source_stat(scan_run_id);
CREATE INDEX IF NOT EXISTS scan_source_stat_source_idx ON scan_source_stat(source);

-- ============================================================
-- SCAN_PORTAL_STAT: PlanetBids per-portal outcome for one run
-- status: ok | empty | blocked | error | pending
-- ============================================================
CREATE TABLE IF NOT EXISTS scan_portal_stat (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scan_run_id     uuid REFERENCES scan_run(id) ON DELETE CASCADE,
  portal_id       text NOT NULL,
  agency          text,
  county          text,
  status          text,
  bid_count       int DEFAULT 0,
  checked_at      timestamptz
);

CREATE INDEX IF NOT EXISTS scan_portal_stat_run_idx    ON scan_portal_stat(scan_run_id);
CREATE INDEX IF NOT EXISTS scan_portal_stat_portal_idx ON scan_portal_stat(portal_id);

-- Backfill from the legacy scan_log is in backfill_scan_run.sql — run that once
-- after this file.
