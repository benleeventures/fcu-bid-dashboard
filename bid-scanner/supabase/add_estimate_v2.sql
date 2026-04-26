-- FCU Phase 2: Settings table + estimate extensions
-- Run this once in Supabase Dashboard → SQL Editor

-- ============================================================
-- SETTINGS: labor rates and other config (editable from dashboard)
-- ============================================================
CREATE TABLE IF NOT EXISTS settings (
  key        text PRIMARY KEY,
  value      text NOT NULL,
  updated_at timestamptz DEFAULT now()
);

INSERT INTO settings (key, value) VALUES
  ('rate_journeyman_standard',   '100'),
  ('rate_journeyman_prevailing', '108'),
  ('rate_apprentice',            '58')
ON CONFLICT (key) DO NOTHING;

-- ============================================================
-- ESTIMATES: add line items + stale rate tracking
-- ============================================================
ALTER TABLE estimates
  ADD COLUMN IF NOT EXISTS line_items     jsonb DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS rates_snapshot jsonb,
  ADD COLUMN IF NOT EXISTS rates_version  timestamptz,
  ADD COLUMN IF NOT EXISTS is_stale       boolean DEFAULT false,
  ADD COLUMN IF NOT EXISTS status         text DEFAULT 'draft';

-- line_items element shape:
-- {
--   "id": "uuid",
--   "type": "labor" | "material",
--   "description": "Journeyman Standard",
--   "qty": 120,
--   "unit": "hrs",
--   "rate": 100.00,
--   "total": 12000.00,
--   "rate_key": "standard"   -- null for materials
-- }
