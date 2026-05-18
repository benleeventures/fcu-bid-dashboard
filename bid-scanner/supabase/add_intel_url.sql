-- Add url column to bid_intel for direct link to PlanetBids detail page
ALTER TABLE bid_intel ADD COLUMN IF NOT EXISTS url text;
