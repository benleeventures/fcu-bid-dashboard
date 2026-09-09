-- FCU Bid Agent — bid_documents table + bids doc-status columns
-- Run in Supabase Dashboard → SQL Editor.
--
-- ALSO (one-time, manual, in Supabase Dashboard → Storage):
--   Create a bucket named  bid-docs  with "Public bucket" ENABLED.
--   Public-read is intentional — bid solicitations are already public records,
--   and permanent non-expiring URLs are what the dashboard + Airtable need.
--
-- Mirrors documents the bid-scanner already downloaded to output/specs/ into
-- Supabase Storage so they can be linked from the dashboard bid page and pushed
-- into the Airtable "Opportunities" tracker. One row per file.

CREATE TABLE IF NOT EXISTS bid_documents (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_id        text REFERENCES bids(bid_id) ON DELETE CASCADE,
  filename      text NOT NULL,
  storage_path  text NOT NULL,            -- bid-docs/<safe_id>/<filename>
  public_url    text NOT NULL,
  source_url    text,                     -- agency URL the file came from, when known
  content_type  text,
  bytes         bigint,
  sha256        text,
  kind          text,                     -- 'primary' | 'attachment' | 'page_image'
  downloaded_at timestamptz DEFAULT now(),
  UNIQUE (bid_id, filename)
);

CREATE INDEX IF NOT EXISTS bid_documents_bid_id_idx ON bid_documents(bid_id);

-- Per-bid rollup so the dashboard can show an honest "N documents" /
-- "primary only" / "none" status without counting rows every render.
ALTER TABLE bids
  ADD COLUMN IF NOT EXISTS docs_captured  integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS docs_expected  integer,          -- NULL = source can't tell us the full count
  ADD COLUMN IF NOT EXISTS docs_synced_at timestamptz,
  ADD COLUMN IF NOT EXISTS docs_source    text;             -- download handler that ran
