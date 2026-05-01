-- FCU — add go_score + go_verdict to bid_specs
-- Run in Supabase Dashboard → SQL Editor

ALTER TABLE bid_specs
  ADD COLUMN IF NOT EXISTS go_score   integer,
  ADD COLUMN IF NOT EXISTS go_verdict text CHECK (go_verdict IN ('go', 'maybe', 'no_go'));

CREATE INDEX IF NOT EXISTS bid_specs_go_verdict_idx ON bid_specs(go_verdict);
