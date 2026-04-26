-- FCU Bid Agent — Database Schema
-- Run this once in Supabase Dashboard → SQL Editor

-- ============================================================
-- BIDS: everything the scanner finds daily
-- ============================================================
CREATE TABLE IF NOT EXISTS bids (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_id          text UNIQUE NOT NULL,       -- source-prefixed: "SAM-xxx", "PB-39493-xxx"
  title           text NOT NULL,
  agency          text,
  state           text DEFAULT 'California',
  source          text,                        -- "SAM.gov", "PlanetBids", etc.
  published_date  date,
  due_date        date,
  due_date_raw    text,
  published_raw   text,
  url             text,
  is_relevant     boolean DEFAULT false,
  search_keyword  text,
  first_seen_at   timestamptz DEFAULT now(),
  last_seen_at    timestamptz DEFAULT now()    -- updated on each scan
);

-- Index for fast filtering by due date and relevance
CREATE INDEX IF NOT EXISTS bids_due_date_idx ON bids(due_date);
CREATE INDEX IF NOT EXISTS bids_is_relevant_idx ON bids(is_relevant);
CREATE INDEX IF NOT EXISTS bids_source_idx ON bids(source);

-- ============================================================
-- JOB PIPELINE: bids being actively pursued
-- status: discovered → reviewing → bidding → submitted → won/lost/passed
-- ============================================================
CREATE TABLE IF NOT EXISTS job_pipeline (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_id                text REFERENCES bids(bid_id) ON DELETE CASCADE,
  status                text DEFAULT 'discovered',
  go_no_go              text DEFAULT 'pending',   -- pending, bid, no_bid
  go_no_go_reason       text,
  job_walk_date         date,
  job_walk_confirmed    boolean DEFAULT false,
  notes                 text,
  created_at            timestamptz DEFAULT now(),
  updated_at            timestamptz DEFAULT now()
);

-- ============================================================
-- REP QUOTES: material quotes per job from sales reps
-- ============================================================
CREATE TABLE IF NOT EXISTS rep_quotes (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_id            text REFERENCES bids(bid_id) ON DELETE CASCADE,
  rep_name          text,
  rep_email         text,
  material_category text,    -- flooring, carpet, window_coverings
  product_spec      text,
  quantity          numeric,
  unit              text,    -- SF, LY, units
  unit_price        numeric,
  total_price       numeric,
  lead_time_days    int,
  valid_through     date,
  quoted_at         timestamptz DEFAULT now(),
  is_stale          boolean DEFAULT false   -- auto-flagged after 30 days
);

-- ============================================================
-- ESTIMATES: assembled labor + materials + markup
-- ============================================================
CREATE TABLE IF NOT EXISTS estimates (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_id            text REFERENCES bids(bid_id) ON DELETE CASCADE,
  labor_hours       numeric,
  labor_rate        numeric DEFAULT 100,   -- 100 standard, 108 prevailing wage
  labor_total       numeric,
  materials_total   numeric,
  subtotal          numeric,
  markup_30         numeric,               -- subtotal × 1.30
  markup_25         numeric,               -- subtotal × 1.25
  selected_markup   numeric,               -- what Joanne chose
  final_bid_amount  numeric,
  approved_by       text,
  approved_at       timestamptz,
  created_at        timestamptz DEFAULT now()
);

-- ============================================================
-- SUBMISSIONS: submitted bids + win/loss tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS submissions (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_id                text REFERENCES bids(bid_id) ON DELETE CASCADE,
  submitted_at          timestamptz,
  bid_amount            numeric,
  markup_pct            numeric,
  portal_confirmation   text,
  result                text DEFAULT 'pending',   -- pending, won, lost
  winning_amount        numeric,
  our_rank              int,
  total_bidders         int,
  notes                 text,
  created_at            timestamptz DEFAULT now()
);

-- ============================================================
-- SCAN LOG: record of each scanner run
-- ============================================================
CREATE TABLE IF NOT EXISTS scan_log (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scanned_at      timestamptz DEFAULT now(),
  total_found     int,
  relevant_found  int,
  new_bids        int,         -- bids not seen before
  sources         jsonb,       -- per-source counts
  duration_secs   numeric
);
