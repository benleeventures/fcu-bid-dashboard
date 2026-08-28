# Bid Scanner Performance Dashboard — Plan

> **Status (2026-08-28): built, pending DB migration.** Phases 1–4 implemented on
> branch `bid-scanner-dashboard`. Apply `supabase/add_scan_analytics.sql` +
> `backfill_scan_run.sql`, then the next scanner run fills the dashboard.
> Operating notes live in `docs/scanner-dashboard.md`.

**Branch:** `bid-scanner-dashboard`
**Goal:** See how the scanner is performing — raw volume scraped, conversion through
each funnel step, trends over time, and per-source health so we can spot a broken
scraper before it silently costs us bids.

---

## 1. What the scanner funnel actually is

One `python main.py` run moves bids through these stages (today only stages 3–5 are
persisted; 1, 2 and dedup are printed to stdout and lost):

| # | Stage | Where in code | Persisted today? |
|---|-------|---------------|------------------|
| 1 | **Raw scraped** — rows each source scraper returns | `run_scan()` per-source calls, `scanner.py` | ❌ printed only |
| 2 | **Geo gate** — `enrich()` tags `in` / `unknown` / `out`; `out` dropped | `scanner.py:1432-1440` | ❌ printed only |
| 3 | **Dedup** — cross-source duplicate collapse | `_dedup()` `scanner.py:1442` | ⚠ only the final count (`scan_log.total_found`) |
| 4 | **Relevance** — `is_relevant` flooring keyword match (non-relevant still stored) | `_is_relevant()` | ✅ `scan_log.relevant_found` |
| 5 | **New vs known** — first seen today vs `last_seen_at` bump | `db.upsert_bids()` | ✅ `scan_log.new_bids` |
| 6 | **Digest + Airtable** — new & relevant emailed / synced | `main.py:216-232` | ❌ |

Downstream state (per-bid, not per-run — lives in `bids` + related tables):

- `bid_status`: active → submitted → won / lost / no_bid
- parsed (`bid_specs` row exists), estimated (`estimates` row), go/no-go score

### Per-source health signal we're missing

`scan_log.sources` (jsonb) stores *post-processing* counts per source, with **no status**.
We can't currently answer "has Cal eProcure returned 0 for 5 straight runs?" or
"how many PlanetBids portals were WAF-blocked this week?"

PlanetBids already tracks per-portal `ok / empty / blocked / error / pending` in
`output/planetbids_state.json` (`pb_state.py`) — but only the latest run, not in the DB.

---

## 2. Instrumentation (Python) — Phase 1

Thread a `ScanFunnel` accumulator through `run_scan()`.

- Each source scraper reports: `source, raw_count, status (ok|empty|blocked|error|partial), note, duration_secs`.
  - `blocked`/`error` come from existing exception handling + `pb_state` for PlanetBids.
- The pipeline stage records: `raw_found, geo_in, geo_unknown, geo_out, after_dedup,
  dedup_removed, relevant, not_relevant, new_bids, updated_bids, digest_sent`.

Wire into all three entry paths that call `log_scan` today:
`main.py` full run, `--source planetbids`, `--source opengov`.

### New Supabase tables (`supabase/add_scan_analytics.sql`)

```
scan_run
  id, started_at, finished_at, mode, duration_secs,
  raw_found, geo_in, geo_unknown, geo_out,
  after_dedup, dedup_removed, relevant, new_bids, updated_bids,
  digest_sent bool, error_summary text

scan_source_stat
  id, scan_run_id fk, source,
  raw_count, kept_count, relevant_count, new_count,
  status,                     -- ok | empty | blocked | error | partial
  portals_total, portals_ok, portals_blocked,   -- PlanetBids only, else null
  note, duration_secs

scan_portal_stat            -- PlanetBids granularity (optional, from pb_state manifest)
  id, scan_run_id fk, portal_id, agency, county, status, bid_count, checked_at
```

`db.log_scan_run(funnel)` writes all three in one call. Keep writing the old
`scan_log` row too until the dashboard's homepage widget (`app/page.tsx:73`) is
moved onto `scan_run` — then drop `scan_log` or leave it as a view.

### Backfill

- Existing `scan_log` rows → seed `scan_run` with `after_dedup = total_found`,
  raw/geo fields null (honest: granular history starts now).
- Try mining `bid-scanner/logs/scraper.log` / `supervisor.log` for older per-run
  "Geo filter: dropped N" / "Total: N unique" lines — best effort, not blocking.

---

## 3. Dashboard page — Phase 2 (the bulk of the work)

New route **`/scanner`** in the live Next.js app (`app/`, the one with `vercel.json`
at repo root — `dashboard/` is a stale duplicate). Server component, reads Supabase
directly, same pattern as `app/page.tsx`. Dark brand theme (charcoal `#1C1C1E`,
gold `#C8922A`, cream), matching the scan-summary email.

### Sections

1. **Funnel** — horizontal stepped bar: Raw → In-area → After dedup → Relevant → New.
   Count + step-to-step conversion %. Toggle: latest run / 7-day / 30-day totals.

2. **Volume over time** — line chart, one series per stage (raw, relevant, new) by day.
   Plus a companion bar: "bids filtered out per day" = geo_out + not_relevant + dedup_removed,
   segmented by reason. This is the "volume of bids filtered per day" ask.

3. **Source visibility matrix** — rows = sources, columns = last ~14 runs/days.
   Cell = status color (green ok / grey empty / red blocked / amber error) + raw count.
   Instantly shows "Cal eProcure broken since Tuesday". Per-source raw-volume sparkline.

4. **PlanetBids portal drill-down** — 41-portal grid: latest status + 14-day success rate.
   Flags portals blocked/empty for N consecutive runs (candidates to fix or drop).

5. **Run log** — recent `scan_run` rows: time, mode, duration, raw→new, status badge.

### Charts

Hand-rolled SVG / CSS — the app currently has **zero chart dependencies** and this
data (a funnel, a few lines, a heatmap grid) doesn't justify adding Recharts to the
Vercel bundle. Use the `dataviz` skill for palette/axis discipline.
*(Alternative if we want richer interactivity later: add Recharts — ~1 line in
`package.json`, well-supported in Next 14.)*

---

## 4. Alerting — Phase 3 (small, high value)

Extend `send_scan_summary` (`notify.py:106`): add a **source-health line** that flags
any source with 0 raw for ≥2 consecutive runs (one query against `scan_source_stat`).
Early warning that doesn't depend on anyone opening the dashboard.

---

## 5. Docs — Phase 4

- ROADMAP.md — add "Scanner Analytics Dashboard" row + `/scanner` to portal notes.
- `docs/scanner-dashboard.md` — what each metric means, how statuses are derived.

---

## Sequencing & effort

| Phase | Scope | Est. |
|-------|-------|------|
| 1 | `ScanFunnel` + 3 tables + migration + `db.log_scan_run` | ~0.5 day |
| 2 | `/scanner` page, 5 sections, SVG charts | ~1–1.5 days |
| 3 | source-health email line | ~1 hr |
| 4 | docs | ~1 hr |

Phase 1 is independently testable with one `python main.py` run before any UI exists.

## Decisions (locked 2026-08-28)

1. **Location:** `/scanner` route in the existing app (`app/`).
2. **Backfill:** start granular history now — seed `scan_run` from `scan_log`, no log mining.
3. **Charts:** hand-rolled SVG / CSS, no new dependency.
4. Target `app/` (root, has `vercel.json` + the `intel` routes `dashboard/` lacks);
   `dashboard/` is a stale duplicate — leave it or delete in a later cleanup.
