-- FCU Bid Agent — details read off a source's listing / detail page at scan
-- time (Phase 2). BidNet detail pages first; other sources fill these as
-- they're wired up. Run in Supabase Dashboard → SQL Editor BEFORE deploying
-- the scanner change (the scanner writes these columns on every insert).
--
--   description     listing description / scope text
--   location_raw    location exactly as the source states it ("San Diego County")
--   contact_email   buyer contact
--   walk_date       earliest pre-bid conference / job walk
--   walk_mandatory  true = mandatory, false = optional, NULL = not stated

ALTER TABLE bids ADD COLUMN IF NOT EXISTS description    text;
ALTER TABLE bids ADD COLUMN IF NOT EXISTS location_raw   text;
ALTER TABLE bids ADD COLUMN IF NOT EXISTS contact_email  text;
ALTER TABLE bids ADD COLUMN IF NOT EXISTS walk_date      date;
ALTER TABLE bids ADD COLUMN IF NOT EXISTS walk_mandatory boolean;
