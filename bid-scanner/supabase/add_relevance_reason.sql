-- FCU Bid Agent — record WHY the relevance filter rejected a bid
-- Run in Supabase Dashboard → SQL Editor
--
-- `is_relevant = false` today lumps genuine noise (roofing, janitorial) in with
-- real false-negatives (an ambiguous "modernization" Claude guessed wrong on).
-- This column splits them so the dashboard's /filtered audit view can show the
-- team only the bids worth a second look. Values (see scanner.RELEVANCE_REASONS):
--   NULL                 — bid is relevant (is_relevant = true), or scanned before this migration
--   'non_flooring_service'— janitorial / pest / landscaping / glass, no floor scope
--   'other_trade'         — roofing / HVAC / paving / … , no flooring keyword in title
--   'claude_rejected'     — construction-adjacent title, Claude second pass said NO
--   'no_keyword'          — nothing flooring-related in the title at all

ALTER TABLE bids ADD COLUMN IF NOT EXISTS relevance_reason text;

-- Partial index — the audit view only ever queries the rejected rows.
CREATE INDEX IF NOT EXISTS bids_relevance_reason_idx
  ON bids(relevance_reason)
  WHERE is_relevant = false;

-- No backfill: existing rejected rows stay NULL and re-populate naturally the
-- next time the scanner sees them still open. Old past-due rejects aren't worth
-- a backfill crawl.
