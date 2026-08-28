-- FCU Bid Agent — parse lifecycle tracking on bids
-- Run in Supabase Dashboard → SQL Editor
--
-- Gives every relevant bid a terminal state so the parse queue can't grow
-- unbounded. Values:
--   NULL / 'pending'  — still needs work (default)
--   'parsed'          — bid_specs row written
--   'no_docs'         — no spec document could be downloaded after MAX_PARSE_ATTEMPTS
--   'unparseable'     — document downloaded but extraction failed MAX_PARSE_ATTEMPTS times
--   'skipped'         — deliberately written off (past due at download, or backlog write-off)

ALTER TABLE bids ADD COLUMN IF NOT EXISTS parse_status     text;
ALTER TABLE bids ADD COLUMN IF NOT EXISTS parse_attempts   integer NOT NULL DEFAULT 0;
ALTER TABLE bids ADD COLUMN IF NOT EXISTS parse_checked_at timestamptz;
ALTER TABLE bids ADD COLUMN IF NOT EXISTS parse_note       text;

CREATE INDEX IF NOT EXISTS bids_parse_status_idx ON bids(parse_status);

-- Backfill: bids that already have a spec are 'parsed'.
UPDATE bids b
SET    parse_status = 'parsed'
WHERE  b.parse_status IS NULL
  AND  EXISTS (SELECT 1 FROM bid_specs s WHERE s.bid_id = b.bid_id);

-- One-time backlog write-off is NOT done here — run it explicitly after this
-- migration so it can't fire again on a later re-run:
--   python parser.py --writeoff-backlog
