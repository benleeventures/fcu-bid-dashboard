-- FCU Bid Agent — North / South region routing (Phase 2, Ben 2026-10-21)
-- Run in Supabase Dashboard → SQL Editor BEFORE deploying the scanner change
-- (the scanner writes `region` on every insert).
--
--   North (Melvin): Los Angeles, Ventura, Kern
--   South (Robert): Orange, Riverside, San Bernardino, San Diego
--   NULL: county not confirmed (geo_status = 'unknown') or out of area

ALTER TABLE bids ADD COLUMN IF NOT EXISTS region text
  CHECK (region IS NULL OR region IN ('North', 'South'));

UPDATE bids SET region = CASE
    WHEN county IN ('Los Angeles', 'Ventura', 'Kern') THEN 'North'
    WHEN county IN ('Orange', 'Riverside', 'San Bernardino', 'San Diego') THEN 'South'
  END
WHERE geo_status = 'in' AND region IS NULL;

CREATE INDEX IF NOT EXISTS bids_region_idx ON bids(region);
