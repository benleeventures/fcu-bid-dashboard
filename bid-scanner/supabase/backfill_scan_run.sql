-- FCU Bid Agent — one-time backfill of scan_run from the legacy scan_log.
-- Run once, after add_scan_analytics.sql.
--
-- Legacy rows only carry the post-dedup total, relevant, and new counts —
-- raw_found / geo_* / dedup_removed are unknowable for historical runs, so
-- raw_found is set equal to after_dedup and the geo split is left at 0.
-- mode='legacy' both labels these rows and guards against a double run.

INSERT INTO scan_run (mode, started_at, finished_at, duration_secs,
                      raw_found, after_dedup, relevant, new_bids)
SELECT 'legacy',
       sl.scanned_at,
       sl.scanned_at,
       sl.duration_secs,
       COALESCE(sl.total_found, 0),
       COALESCE(sl.total_found, 0),
       COALESCE(sl.relevant_found, 0),
       COALESCE(sl.new_bids, 0)
FROM scan_log sl
WHERE NOT EXISTS (SELECT 1 FROM scan_run WHERE mode = 'legacy');
