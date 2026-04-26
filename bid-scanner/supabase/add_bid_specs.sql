-- FCU Bid Agent — bid_specs table
-- Run in Supabase Dashboard → SQL Editor

CREATE TABLE IF NOT EXISTS bid_specs (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_id          text REFERENCES bids(bid_id) ON DELETE CASCADE UNIQUE,
  flooring_types  text[],            -- ['carpet', 'LVT', 'VCT', 'tile', 'hardwood', 'window_coverings']
  total_sqft      numeric,
  rooms           text,              -- "Classrooms, hallways, admin offices"
  prevailing_wage boolean,
  bid_bond        boolean,
  bid_bond_pct    numeric,           -- e.g. 10 (for 10%)
  walk_required   boolean,
  walk_date       date,
  walk_date_raw   text,
  summary         text,              -- Claude 2-sentence summary
  raw_extract     jsonb,             -- full structured Claude response
  pdf_url         text,
  pdf_filename    text,
  parsed_at       timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS bid_specs_bid_id_idx ON bid_specs(bid_id);
