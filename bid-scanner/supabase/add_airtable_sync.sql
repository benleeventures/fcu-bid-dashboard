-- FCU — track which bids have been pushed to the Airtable "FCU Bid Tracker"
-- Run in Supabase Dashboard → SQL Editor
--
-- Set by the dashboard's "Add to Airtable" button (app/actions/airtable.ts) after
-- it creates the Opportunities record. NULL = not pushed from the dashboard.
-- (The scanner's own airtable_sync.py still pushes new relevant bids on each run
-- and does not touch this column — it dedupes on the Airtable "Bid ID" field.)

ALTER TABLE bids ADD COLUMN IF NOT EXISTS airtable_synced_at timestamptz;
