-- FCU Bid Agent — retire the 100 junk Cal eProcure rows (Phase 2, PR 3b).
-- Run in Supabase Dashboard → SQL Editor, any time after the PR merges.
--
-- The old Cal eProcure parser gave rows positional IDs CAL-0 … CAL-99 and
-- stored the event name as the agency, so the same 100 rows (first seen
-- April 2026) were "re-seen" every day and new events were never saved.
-- The fixed parser uses real event IDs (CEP-<event id>), so these rows will
-- never match again. Expire them so they leave the dashboard and queues.

UPDATE bids
SET bid_status = 'expired', is_relevant = false
WHERE source = 'Cal eProcure' AND bid_id ~ '^CAL-[0-9]+$';
