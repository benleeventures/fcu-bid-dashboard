-- FCU Bid Agent — geographic + agency-type columns (spec §1 / §2)
-- Run once in Supabase Dashboard → SQL Editor.

ALTER TABLE bids ADD COLUMN IF NOT EXISTS county       text;
ALTER TABLE bids ADD COLUMN IF NOT EXISTS geo_status   text;   -- 'in' | 'unknown'  ('out' bids are never stored)
ALTER TABLE bids ADD COLUMN IF NOT EXISTS agency_type  text;   -- city | county | state | ccd | k12 | transit | housing | airport | port | special_district | unknown
ALTER TABLE bids ADD COLUMN IF NOT EXISTS is_k12       boolean DEFAULT false;

CREATE INDEX IF NOT EXISTS bids_county_idx      ON bids(county);
CREATE INDEX IF NOT EXISTS bids_agency_type_idx ON bids(agency_type);
