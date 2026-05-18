-- Migration: add digested_at column to bids table
-- Run once in Supabase Dashboard → SQL Editor
--
-- Purpose: queue system for PlanetBids manual runs.
-- NULL  = queued (not yet included in a scheduled digest email)
-- value = timestamp when it was included in a digest

ALTER TABLE bids ADD COLUMN IF NOT EXISTS digested_at timestamptz DEFAULT NULL;

CREATE INDEX IF NOT EXISTS bids_digested_at_idx ON bids(digested_at);
