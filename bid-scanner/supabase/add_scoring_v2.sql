-- FCU — scoring v2: winnability score inputs + 'review' verdict
-- Run once in Supabase Dashboard → SQL Editor.

ALTER TABLE bid_specs
  ADD COLUMN IF NOT EXISTS award_method        text,
  ADD COLUMN IF NOT EXISTS flooring_is_primary boolean,
  ADD COLUMN IF NOT EXISTS project_city        text,
  ADD COLUMN IF NOT EXISTS bid_type            text;

-- go_verdict gains 'review' — bids that are parsed but still missing a scoring
-- input (location / due date / scope read). go_score is NULL for those rows.
ALTER TABLE bid_specs DROP CONSTRAINT IF EXISTS bid_specs_go_verdict_check;
ALTER TABLE bid_specs ADD  CONSTRAINT bid_specs_go_verdict_check
  CHECK (go_verdict IN ('go', 'maybe', 'no_go', 'review'));
