# Scanner Health Dashboard (`/scanner`)

Tracks how the bid scanner is performing: funnel throughput, volume trends, and
per-source visibility. Built on branch `bid-scanner-dashboard` (2026-08).

## Setup (one time)

1. Supabase → SQL Editor → run `bid-scanner/supabase/add_scan_analytics.sql`
2. Then run `bid-scanner/supabase/backfill_scan_run.sql` (seeds history from `scan_log`)
3. Next scanner run populates the new tables automatically. Page is at `/scanner`
   (linked from the dashboard header).

## What gets recorded

Every `python main.py` run (full, `--source planetbids`, `--source opengov`)
writes a `ScanFunnel` (`bid-scanner/funnel.py`) via `db.log_scan_run()`:

| Table | Grain | Contents |
|-------|-------|----------|
| `scan_run` | one row / run | funnel counts: `raw_found → geo_in/unknown/out → after_dedup → relevant → new_bids/updated_bids`, duration, `digest_sent`, `error_summary` |
| `scan_source_stat` | one row / source / run | `raw_count`, `kept_count` (post-geo), `relevant_count`, `new_count`, `status`, PlanetBids `portals_*`, `note` |
| `scan_portal_stat` | one row / PlanetBids portal / run | per-portal `status` + `bid_count`, folded from `output/planetbids_state.json` |

The legacy `scan_log` row is still written in parallel (the homepage "last scan"
widget reads it) — remove once that widget moves to `scan_run`.

## The funnel stages

1. **Raw scraped** — rows each source scraper returns, pre-anything. Summed across sources.
2. **In-area** — after `geo.enrich()`; `geo_status='out'` bids are dropped here, `unknown` are kept + flagged.
3. **After dedup** — `_dedup()` collapses cross-source duplicate bid_ids / titles.
4. **Flooring-relevant** — `is_relevant` (keyword match + Claude Haiku second pass). Non-relevant bids are still stored.
5. **New** — first seen this run vs. already known (`last_seen_at` bumped).

## Source status values

| status | meaning |
|--------|---------|
| `ok` | returned rows normally |
| `empty` | loaded but returned 0 rows, no exception. **For every source except PlanetBids we cannot distinguish a genuine "nothing matched" from a silent block** — a source sitting at `empty` for days is the signal to investigate. |
| `blocked` | PlanetBids only — WAF / blank page, from the run manifest |
| `partial` | PlanetBids only — some portals ok, some still blocked/pending |
| `error` | the scraper raised; see `note` / `scan_run.error_summary` |

`run_scan()` now wraps each source in `funnel.guard()` — one source raising no
longer aborts the whole scan; it's recorded as `error` and the run continues.

## Dashboard sections

- **Window summary** — 7-day totals (runs, raw, relevant, new, filtered-out, raw→new %).
- **Funnel** — latest full run, step-to-step conversion %, with 7/30-day totals underneath.
- **Volume over time** — 30-day line chart (raw / relevant / new) + "bids filtered out per day" bars.
- **Source visibility** — source × last-14-days grid, cell coloured by status, number = raw rows. A source red-flagged (`Nd`) has scraped 0 for ≥2 consecutive days.
- **PlanetBids portals** — latest sweep, 38-portal grid by county, coloured by outcome.
- **Recent runs** — last 25 runs.

## Email

`send_scan_summary` (fires after every run) now leads with a **Source health**
banner when `_persistent_source_issues()` finds any source at 0 for ≥2
consecutive runs — early warning without opening the dashboard.

## Not done / future

- Homepage "last scan" widget still reads `scan_log`, not `scan_run`.
- No per-portal historical uptime % (grid shows latest sweep only).
- Charts are static SVG — no hover tooltips / zoom.
- `dashboard/` is a stale duplicate of `app/`; `/scanner` was added to `app/` only.
