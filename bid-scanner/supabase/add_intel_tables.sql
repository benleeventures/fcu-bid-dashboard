-- FCU Competitive Intelligence Tables
-- Run once in Supabase SQL editor

-- Normalized vendor entities (one canonical record per real company)
CREATE TABLE IF NOT EXISTS vendors (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_name text NOT NULL UNIQUE,
  aliases        text[] DEFAULT '{}',
  created_at     timestamptz DEFAULT now()
);

-- One row per awarded bid scraped from PlanetBids
CREATE TABLE IF NOT EXISTS bid_intel (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  portal_id        text NOT NULL,
  numeric_bid_id   text NOT NULL,
  agency           text,
  title            text NOT NULL,
  awarded_at       date,
  winner_vendor_id uuid REFERENCES vendors(id),
  winner_amount    numeric,
  total_bidders    int,
  last_synced_at   timestamptz DEFAULT now(),
  created_at       timestamptz DEFAULT now(),
  UNIQUE(portal_id, numeric_bid_id)
);

-- One row per vendor submission for each awarded bid
CREATE TABLE IF NOT EXISTS bid_intel_submissions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  intel_id        uuid REFERENCES bid_intel(id) ON DELETE CASCADE,
  vendor_id       uuid REFERENCES vendors(id),
  raw_vendor_name text NOT NULL,
  bid_amount      numeric,
  is_winner       boolean DEFAULT false,
  rank            int,
  created_at      timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_bid_intel_agency ON bid_intel(agency);
CREATE INDEX IF NOT EXISTS idx_bid_intel_awarded_at ON bid_intel(awarded_at);
CREATE INDEX IF NOT EXISTS idx_bid_intel_winner ON bid_intel(winner_vendor_id);
CREATE INDEX IF NOT EXISTS idx_submissions_vendor ON bid_intel_submissions(vendor_id);
CREATE INDEX IF NOT EXISTS idx_submissions_intel ON bid_intel_submissions(intel_id);
