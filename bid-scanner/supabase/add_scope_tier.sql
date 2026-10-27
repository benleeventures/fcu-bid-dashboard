-- FCU Bid Agent — scope tier on relevant bids (Phase 2, PR 4).
-- Run in Supabase Dashboard → SQL Editor BEFORE deploying the scanner change
-- (the scanner writes scope_tier on every insert).
--
--   prime    flooring / floor covering is the whole job (install, supply or care)
--   package  a separate flooring trade package of a larger project
--   mixed    flooring named alongside other scopes ("Paint & Flooring")
--   NULL     not relevant
-- Filled for bids already in the table the next time the scanner sees them.

ALTER TABLE bids ADD COLUMN IF NOT EXISTS scope_tier text
  CHECK (scope_tier IS NULL OR scope_tier IN ('prime', 'package', 'mixed'));
