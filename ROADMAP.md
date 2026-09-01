# FCU — AI Bid Agent Roadmap
**Last updated:** 2026-08-28

> Always read this before any bid agent work. Contains current build status, pricing rates, phase checklist, and portal coverage.

---

## Current Status

| System | Status | Notes |
|--------|--------|-------|
| Bid Scanner (14 sources) | ✅ Running | 4-county geo gate + agency-type tagging live (spec §1/§2, 2026-08). UCLA + Long Beach BuySpeed + LAUSD Facilities + SecureBids + RAMP added 2026-09 |
| Dashboard (Next.js + Supabase) | ✅ Live on Vercel | Showing bid results |
| Scanner Health Dashboard (`/scanner`) | ✅ Built (2026-08) | Funnel + volume-over-time + per-source visibility matrix + PlanetBids portal grid. **Fully data-driven** — every source wrapped in `funnel.guard()` auto-appears in the matrix (ok / empty / error + broken-streak) on the next full `python main.py` run; no source list to maintain. The 2026-09 additions (UCLA, Long Beach, LAUSD Facilities, SecureBids) show up automatically. Needs `supabase/add_scan_analytics.sql` + `backfill_scan_run.sql` applied. See `docs/scanner-dashboard.md` |
| Estimate Worksheet | ✅ Done | In dashboard — labor rates, 25/30% markup, approve flow |
| Document Download | ✅ Done | Playwright-based, all sources |
| AI Parsing → bid_specs | ✅ Done (manual mode) | `--parse-all` prints prompts for Claude Code; `--ollama` for auto |
| New-Bid Email Digest | ✅ Done | Fires via Resend after each scanner run with new relevant bids. "View ↗" links point to the dashboard bid page (`DASHBOARD_URL/bids/<id>`), which links out to the source portal in turn |
| Job Walk Alert Email | ✅ Done | Fires via Resend when `walk_required=True` after parsing |
| Compliance Alert Email | ✅ Done | Fires via Resend on `--save` when bid_bond/prevailing_wage/dvbe/dbe flags set |
| RFQ Email Generator | ✅ Done | `--rfq <bid_id>` CLI + "Send RFQ →" button in dashboard; sends draft to Joanne |
| Scheduler | ⬜ Skipped for now | Test manually first; add cron after validation |
| BidNet Direct (public listing page) | ⚠ Partial | Headless browser blocked on listing page; doc download works via login |
| LAUSD Facilities (FSD) | ✅ Discovery live | `--source lausd` parses the public "Updated Bid Information Report (Sorted by Bid Date)" PDF from procurement.lausd.org. TOPO renewal 2027. Discovery only — no per-bid doc download (the report is one combined PDF); C-15 licence requirement forces relevance |
| LAUSD Supplier Portal / ARRIBA | ⬜ Not connected | vendors.lausd.net SAP portal (Firefox-only) — the PO/supplier side, separate from FSD bids. Needs working creds |
| AI RFQ Generator | ⬜ Phase 3 | |
| Compliance Auto-Checker | ⬜ Phase 3 | Compliance fields exist in bid_specs, no alert yet |
| Bid Package Assembler | ✅ Done | `/api/bids/[id]/package` — PDF download from dashboard |
| Bid Results Tracking | ✅ Done | Status badges, win/loss tracker, amount fields in bid detail + table filter |
| Competitive Intelligence | ⬜ Phase 4 | |

---

## Immediate Next Steps

### 1. Test AI Parsing + Notifications
Env vars needed in `bid-scanner/.env`:
```
RESEND_API_KEY=your_resend_api_key_here
ADMIN_EMAIL=your_email_here          # role vars: see bid-scanner/.env.example
```

Parse existing downloaded PDFs using Claude Code:
```bash
cd projects/FCU/bid-scanner
python parser.py --pending          # see what's ready
python parser.py --parse-all        # prints prompts — Claude Code reads each PDF and calls --save
python parser.py --save <bid_id> '<json>'   # after Claude Code extracts JSON
```

### 2. Test Full Scanner Run
```bash
python main.py
```
Should send a new-bid digest email if any new relevant bids are found.

### 3. Connect LAUSD Portal (Phase 1 expansion)
LAUSD is the highest-priority portal — TOPO contract renewal in 2027.

### 4. Quantity Takeoff (Phase 2)
Extend `bid_specs` with room-by-room breakdown for estimate pre-filling.

---

## The 9-Step Bid Pipeline

| # | Step | Owner | Status |
|---|------|--------|--------|
| 1 | Job Discovery & Portal Monitoring | Agent | ✅ Running (SAM + PlanetBids + BidNet) |
| 2 | Document Download & Parsing | Agent | ✅ Download / ✅ Manual parsing with Claude Code |
| 3 | Job Walk Assessment | Lenny | ✅ Agent sends job walk alert email when walk_required |
| 4 | Scope Extraction & Quantity Takeoff | Agent | ⬜ Phase 2 |
| 5 | Material Quote Requests (RFQs) | Agent drafts / Joanne approves | ⬜ Phase 3 |
| 6 | AI-Powered Estimate Worksheet | Agent + Joanne | ✅ Done (dashboard) |
| 7 | Compliance & Requirements Check | Agent | ⚠ Fields captured in bid_specs, no alert email yet |
| 8 | Bid Package Preparation | Agent + Joanne signs | ⬜ Phase 3 |
| 9 | Submission, Tracking & Learning | Joanne submits / Agent logs | ⬜ Phase 4 |

---

## Build Phases

### Phase 1: Foundation — COMPLETE
- [x] Job tracking database (Supabase)
- [x] Portal monitoring — SAM.gov + PlanetBids + BidNet Direct
- [x] Document download + local storage
- [x] Basic bid dashboard (Next.js + Vercel)
- [x] AI Parsing (manual mode via Claude Code + `--save`)
- [x] New-bid email digest (Resend)
- [x] Job walk alert email (Resend)
- [ ] BidNet Direct public listing page (headless blocked — workaround: manual or cookies)
- [ ] LAUSD, City of LA, County of LA, Long Beach Unified portals
- [ ] Scheduler (skipped for now — test manually first)

### Phase 2: Estimating Core
- [x] AI-powered Estimate Worksheet (replaces Joanne's Excel)
- [x] Labor rates hardcoded with settings UI:
  - Journeyman Standard: **$100.00/hr**
  - Journeyman Prevailing Wage: **$108.00/hr**
  - Apprentice: **$58.00/hr**
- [x] Markup calculator — always show 25% and 30% side-by-side
- [ ] Room-by-room Quantity Takeoff → Estimate Worksheet pipeline
- [ ] Test with 3–5 real past jobs

### Phase 3: Automation
- [x] Compliance alert emails — fires on `--save` for bid_bond, prevailing_wage, dvbe, dbe flags
- [x] RFQ email generator — `python parser.py --rfq <bid_id>` + "Send RFQ →" dashboard button
- [x] Bid package assembly module (PDF generation) — `/api/bids/[id]/package` route, PDF download in dashboard
- [x] Auto-parsing via Claude (`--parse-all --claude`) — replaces the llama3.2:3b path

### Parse pipeline hardening (Phase 1 branch) — 2026-08

The parse queue used to grow forever: any bid whose docs failed to download, or
whose scanned PDF the vision fallback couldn't read, stayed "pending" indefinitely.

- **`bids.parse_status`** (migration `supabase/add_parse_status.sql`): `parsed` /
  `no_docs` / `unparseable` / `skipped` / NULL(pending). `parse_attempts` caps
  retries at `MAX_PARSE_ATTEMPTS` (3), then the bid leaves the queue.
- **Claude extraction** — `_parse_with_claude_text` (text layer) → `_parse_with_claude`
  (vision) for scanned. Model = `PARSER_CLAUDE_MODEL` env (default `claude-sonnet-5`).
- **poppler PATH** fixed for launchd (a8b7e4b) so the vision fallback actually runs.
- **Digest** now separates actionable "pending" from "gave up" (no_docs/unparseable).
- **One-time**: after running the migration, `python parser.py --writeoff-backlog`
  clears the pre-existing backlog to `skipped`.
- ⚠ Deploy: `setup/launchd/com.fcu.parser.plist` switched `--ollama` → `--claude`;
  reload it on the Mac mini after merge (`launchctl unload/load`).

### Phase 4: Intelligence
- [ ] Bid results tracking and logging
- [ ] Competitive intelligence dashboard (win/loss by agency, job type)
- [ ] Go/no-go scoring model
- [ ] Markup recommendation engine

### GC Watchlist (spec §7) — ✅ Session 4 (2026-08)

Airtable table **GC Watchlist** (`tbl0Dt9pkq3p23AkB`) — GC name, counties, plan room,
registered?, prequal?, ITB arriving?, contact, last invitation. Seeded with 20 GCs
(`gc_watchlist.SEED_GCS`, Tutor Perini first).

- `python main.py --gc-watchlist` — seed + harvest GC winners from `bid_intel` (no browser)
- `python main.py --intel` now also runs `run_gc_award_scan` on the live session — scans
  PlanetBids **general-construction** award winners in the four counties and adds them
- Registration on GC plan rooms (iSqFt/BuildingConnected/Procore/SmartBid) and outreach
  stay manual — this only tracks whether invitations arrive. **Free channels only.**

---

## Pricing Framework (Always Current — Update Here First)

### Labor Rates
| Classification | Rate | When to Apply |
|----------------|------|---------------|
| Journeyman (Prevailing Wage) | **$108.00/hr** | Certified payroll jobs, complex installs |
| Journeyman (Standard) | **$100.00/hr** | Default for all public works estimates |
| Apprentice | **$58.00/hr** | Lower-skill tasks (rate already marked up) |

### Markup Policy
| Scenario | Markup | Notes |
|----------|--------|-------|
| Standard bid | **30%** | Always try this first — auto-applied |
| Must-win / competitive | **25%** | Owner must approve before applying |
| Below 25% | ❌ Block | Never without owner sign-off |

**Formula:** `(Labor + Materials) × 1.30` → 30% bid  
**Formula:** `(Labor + Materials) × 1.25` → 25% bid  
Always show both numbers. Human picks which to submit.

### Material Pricing
**Policy:** Never hardcode. All material costs come from rep quotes per job.  
Rep quotes older than **30 days** are flagged stale and must be refreshed.

---

## Compliance Flags (Agent Checks Every Job)

| Requirement | Agent Action | Human Action |
|-------------|-------------|--------------|
| Bid Bond | Detects % required → alerts insurance agent | Insurance agent confirms + attaches certificate |
| Certified Payroll / Prevailing Wage | Switches labor to $108/hr → flags in dashboard | Ensure payroll system set up pre-award |
| DVBE Certification (Long Beach) | Flags in dashboard | Confirm cert is current, attach to package |
| DBE Goals | Reads stated % goal, flags if sub needed | Identify + quote a qualified DBE sub |
| Insurance Certificates | Compares spec requirements to current certs | Contact agent if certs don't meet spec |
| License Requirements | Verifies required classification | Confirm license is current |
| Addenda | Tracks all issued addenda | Joanne signs acknowledgment forms |
| Mandatory Job Walk | Sends job walk alert email to Lenny with checklist | Lenny attends, calls Joanne with BID/NO BID |

---

## Tech Stack

| Component | Tool | Purpose |
|-----------|------|---------|
| AI Brain | Claude (via Code session) → Ollama (production) | PDF parsing, scope extraction |
| Portal Monitoring | Playwright + requests | SAM.gov, PlanetBids, BidNet |
| Document Storage | Local `output/specs/` | All job PDFs |
| Estimating UI | Next.js dashboard (Vercel) | Joanne's review + approve interface |
| Email | Resend API | New-bid digest, job walk alerts, RFQs |
| Database | Supabase | Job tracking, specs, estimates |
| Dashboard | Next.js + Vercel | Live bid viewing |
| Hosting | Local (manual runs) → cron/Cloud Run (later) | Scanner runs |

---

## Portal Coverage

| Portal | Status | Notes |
|--------|--------|-------|
| SAM.gov | ✅ Active | Federal; NAICS 238330 + CA place-of-performance. Now runs through the 4-county geo gate — out-of-area federal work is dropped |
| PlanetBids | ✅ Active | Manual run (`--source planetbids`), user solves one CAPTCHA. ~37 portals scanned, each county-tagged (see `PLANETBIDS_PORTALS`; `PLANETBIDS_SKIP` excludes chronically-broken ones). Per-portal outcome tracked in `output/planetbids_state.json`; if the WAF blocks mid-run, re-run `--source planetbids --resume` to retry only the missed portals (auto-loops via `rerun_planetbids.sh`), or add `--give-up` to accept a partial run |
| BidNet Direct | ⚠ Partial | Doc download works; public listing page blocked by bot detection |
| Cal eProcure | ✅ Active | Statewide — most rows land as `geo_status=unknown` and get flagged for county check |
| OpenGov | ⚠ Manual | 5 SoCal portals (NorCal portals removed 2026-08). Run `--source opengov` on demand |
| Caltrans CCOP | ✅ Active | SoCal districts only (D7 / D11 / D12) |
| Quality Bidders (Colbi) | ✅ Active | School-district bids. Public `bids.json` API — **no login** |
| SecureBids (Colbi) | ✅ Active | `--source securebids` — Colbi's other product (colbisecurebids.com redirects here). Public JSON API at api.securebids.com, **no login**. Auto-discovers all CA agencies (stateId 5) each run, geo gate narrows to the 4 counties. Live 2026-09 (8 open CA opps). Out-of-4-county agencies with `regionId=0` (e.g. Victor Valley CCD, Sonoma Valley Hospital) leak through as `geo_status=unknown` / "needs county check", same as Cal eProcure |
| UCLA Capital Programs | ✅ Active | `--source ucla` (pure HTTP, no browser, no login — the UCLA Online Planroom needs creds but the public bidding index does not). Every bid stamped LA County. No due date on the index page — parser pulls it from the direct Ad-for-Bids PDF (`parser.py` now handles direct-`.pdf` URLs). Live 2026-09 |
| Crisp / SoCal plan rooms | ✅ Active | CyberCopy platform. `PLAN_ROOMS` now also includes **CyberCopy Plan Room** (cybercopyplanroom.com, login-sheet row 30) — verified 2026-09 the scraper contract works (0 open public projects at time of check) |
| LAUSD Facilities (FSD) | ✅ Active | `--source lausd` — parses the public "Updated Bid Information Report (Sorted by Bid Date)" PDF (URL resolved each run from procurement.lausd.org — needs full browser headers or it serves a stub). The report is LAUSD FCC's own authoritative list, human-regenerated ~daily on business days; scraper warns if the "Printed:" date is >10 days stale. Every project LA County / K-12. **Thin per-entry info** → relevance leans on the required licence (C-15 = flooring) + keywords. **Depth comes from Crisp:** LAUSD distributes bidding docs through the Crisp plan room, which we already scrape *with* full spec download — same 7-digit project number, so `_dedup` collapses the FSD row into the Crisp one (Crisp runs first). Login-sheet rows 13–18 |
| LAUSD Supplier Portal / ARRIBA | ⬜ Not connected | vendors.lausd.net SAP portal (Firefox-only) — PO/supplier side, separate from FSD bids. Needs working creds. Login-sheet rows 14/15/18 |
| Long Beach BuySpeed | ✅ Active | `--source longbeach` — public BuySpeed advanced search, no login. Filters Status="Sent" and drops past-opening-date leftovers; paginates PrimeFaces results. Every bid stamped LA County. Retires the PlanetBids Long Beach portal (15810, still in `PLANETBIDS_SKIP`). Live 2026-09 (18 advertised bids, 0 flooring at check time). **Doc download = follow-up:** bidDetail.sda is public but attachments are `javascript:downloadFile(id)` — the generic parser can't pull them yet |
| RAMP LA County | ✅ Active | `--source ramp` — rampla.org's DNS is US-geo-restricted, but LA City publishes the same open opportunities as a Socrata dataset (`data.lacity.org/resource/hf3r-utnq.json`), no login, refreshed daily, reachable anywhere. One feed = LA County + LADWP + LA Public Works + Port of LA + LAWA + HACLA (+ a few LAUSD). All LA County. Live 2026-09 (415 open opps). **No FCU login needed after all.** |
| City of LA BAVN | ⬜ Blocked (geo + creds) | labavn.org (the sheet's `angeleno.lacity.org` is wrong — real host is **labavn.org**). DNS won't resolve outside the US → build/test on the Mac mini. No open-data feed found. Cred also marked "not valid 8/26" |
| LACDA | ⬜ Blocked (geo + creds) | lacda.org/vendors (login-sheet row 2) — LA County Development Authority (housing). Returns Azure 403 outside the US → build/test on the Mac mini. No open-data feed found. Lower volume. Cred present, never verified |
| Public Purchase | ⬜ Blocked on registration | **On Ben's list but no FCU account exists** — Joanne must register FCU on publicpurchase.com first |
| Bonfire / Euna | ⬜ Investigate | account.bonfirehub.com (login-sheet row 31) — identify which CA agencies FCU follows before building |
| PQ Bids / Hardesty Associates | ⬜ Verify platform | pqbids.com (row 28), hardestyassociatesplans.com (row 20) — confirm whether either runs the CyberCopy `/projects/public` contract before adding to `PLAN_ROOMS` |
| El Segundo | ⬜ Check | elsegundo.org (login-sheet row 10) — determine if it's just a PlanetBids portal ID to add vs. its own system |

### Client login-sheet triage — 2026-09

Ben asked to fold FCU's manual login sheet (38 rows) into scanner coverage. Full mapping
lives in the session notes; summary:

- **Already covered:** Cal eProcure, Quality Bidders, PlanetBids (incl. Torrance), BidNet
  Direct, Crisp, OpenGov.
- **Added 2026-09 (all no-login):** CyberCopy Plan Room (row 30); **UCLA Capital Programs**
  (row 11 — public index, planroom creds on the sheet not needed); **Long Beach BuySpeed**
  (row 37 — public bid search); **LAUSD Facilities** (rows 13–18 — public bid-date report
  PDF, discovery only); **SecureBids/Colbi** (row 21 — public JSON API, colbisecurebids.com
  just redirects; the sheet's login is unnecessary); **RAMP LA County** (rows 1/7/8 — LA City
  Socrata open-data feed, no login despite the sheet listing creds).
- **No-login confirmed:** Quality Bidders, SecureBids, UCLA, LAUSD FSD, Long Beach, OpenGov,
  Cal eProcure, Caltrans CCOP, Crisp/CyberCopy, SAM.gov all scrape without any FCU account.
  Only PlanetBids (CAPTCHA, not creds), BidNet (doc download), and the not-yet-built RAMP/
  BAVN/LACDA/ARRIBA actually need a login.
- **Excluded (not solicitation sources):** FCU website/email logins; DIR/DLSE PWCR + LAUSD
  CPRs (certified payroll); Surety2000 (bid-bond tool); Autodesk BuildingConnected (GC
  invite-only — handled by GC Watchlist); HigherGov (paid federal aggregator, redundant with
  SAM.gov); Quality Bidders LAUSD prequal (registration admin).
- **Out-of-area:** none — the client added no out-of-state portals.
- **To add (remaining):** City of LA BAVN + LACDA (both **US-geo-blocked** — labavn.org DNS
  won't resolve outside the US, lacda.org returns Azure 403; build/test on the Mac mini) →
  Bonfire → LAUSD Supplier/ARRIBA. Public Purchase needs an FCU account that doesn't exist yet.
- **Dev-environment note:** this session runs from a non-US IP. Confirmed blocked from here:
  laschools.org, labavn.org (no DNS), lacda.org (Azure 403). Reachable: rampla.org itself,
  data.lacity.org, procurement.lausd.org (edlio CDN), publicpurchase.com, securebids.com.
- **LAUSD FSD doc download (follow-up):** the bid-date report is one combined PDF, so the
  parser has no per-bid spec to fetch. Getting actual plans/specs needs the FCC vendor
  number + the request-for-plans flow, or the JOC/Best-Value RFQ pages on laschools.org
  (datacenter-IP-blocked — do it on the Mac mini).
- **Ben's 5:** RAMP / LACDA / BAVN / LAUSD all have creds in the sheet; **Public Purchase is
  the gap — no FCU account.**

### Materials-only / service-only filter — ✅ 2026-09

FCU installs flooring. It does not bid product-only supply contracts, and it does not
hold recurring cleaning / maintenance / pest / janitorial service contracts. Two layers:

- **Scanner:** `_is_materials_only()` matches `MATERIALS_ONLY_PATTERNS` ("furnish/supply only",
  "furnish and deliver", "no installation", "installation by others", "material purchase", …);
  `_is_service_only()` matches `SERVICE_ONLY_PATTERNS` ("carpet cleaning", "janitorial",
  "pest control", "strip and wax", "carpet extraction", …). Both back off when the text also
  names real install / replacement work (`_INSTALL_OVERRIDE` / `_SERVICE_OVERRIDE`). Folded into
  `_is_relevant()`, so a hit gets `is_relevant=False` and never reaches the digest or Airtable.
  Row is still stored in Supabase for the record.
- **Parser:** `_EXTRACTION_PROMPT` extracts `materials_only` and `service_only`. On `--save`,
  either flag flips the bid to `is_relevant=False`. `score_go_no_go` (both `.py` and
  `app/lib/scoring.ts`) returns a hard **NO-GO / 0**. Dashboard bid page shows a
  "Materials only" / "Service contract" flag.
- No migration — both flags live inside `bid_specs.raw_extract`.

### Geographic + agency-type gate (spec §1 / §2) — ✅ Session 1 (2026-08)

- `geo.py` classifies every bid: `geo_status` = `in` (LA / Orange / Ventura / San Diego),
  `out` (dropped before dedup), or `unknown` (kept + flagged "Needs county check" in Airtable).
- Also tags `agency_type` (city / county / state / ccd / k12 / transit / housing / airport /
  port / special_district) and `is_k12`.
- ✅ Migration `supabase/add_geo_agency.sql` run (adds `county`, `geo_status`, `agency_type`,
  `is_k12` to `bids`). Scanner writes these on every run.
- ✅ Airtable "Opportunities" has **County** (singleSelect: LA/Orange/Ventura/San Diego) and
  **Agency or GC** (text) fields. Sync now uses `typecast=True` so new Source Platform options
  auto-create, and degrades to core fields if a column is missing.

**Out-of-state drop — 2026-09.** `geo._is_out_of_state()` catches a US state / territory
other than California named in the agency, place-of-performance, or title (full name, `City, XX`
USPS code, or "State of X"), plus a short list of unambiguous non-CA places (Honolulu / Pearl
Harbor / Hawaii bases, Las Vegas, Reno, Anchorage). These now return `geo_status="out"` and are
dropped before dedup instead of landing as "unknown" and reaching the digest. Runs after the
in-scope positives (LAUSD etc.) so an in-district school named "Washington" isn't caught.
Tests: `test_geo_out_of_state.py`.

### Airtable tracker to spec §5 — ✅ Session 3 (2026-08)

All spec §5 columns exist (see `bid-scanner/docs/airtable-tracker-setup.md`). Sync now also
writes `Owner` (when `AIRTABLE_OWNER_EMAIL` is set — pending Robert's base seat) and
`Estimated Value` (when a value is known post-parse). **Conditional-formatting colour rules
are UI-only** — steps documented in `docs/airtable-tracker-setup.md` §2 (red ≤48h, amber ≤5d
off the `Days to Due` formula). Someone needs to click through that once.

### PlanetBids block-detection + resume — ✅ Session 5 (2026-08)

The scraper walks ~40 portals in one browser session. When PlanetBids' WAF trips,
every portal after it serves a blank page — the old code recorded those as "0 bids"
and `main.py` exited 0, so a mostly-failed run looked clean.

- `_search_planetbids` now classifies each portal: `ok` / `empty` / `blocked` /
  `error` / `pending`, written to `output/planetbids_state.json` (`pb_state.py`).
- After 4 blocked portals in a row it assumes the session is WAF-poisoned, stops,
  and leaves the rest `pending`.
- `python main.py --source planetbids --resume` re-scrapes only the unfinished
  portals and merges them into the Supabase queue. Repeatable; falls back to a full
  scan if the manifest is missing or >48h old.
- The CAPTCHA solve now lands on the **first portal actually being scraped**
  (`planetbids_scan_plan` picks it), not a hardcoded one — each PlanetBids tenant
  runs its own AWS WAF `/2001` challenge, so solving on Beverly Hills didn't help
  Long Beach. If a portal still bounces to `/2001` mid-run, the scraper pauses and
  asks for a manual solve (up to `PLANETBIDS_MAX_RESOLVES` = 3 per run) then retries.
- `main.py` prints an honest summary (`30 ok · 3 empty · 5 blocked`) and exits 2
  when portals are still incomplete. Add `--give-up` to that resume command to
  accept whatever loaded and exit 0 (the blocked portals stay unfinished and get
  retried on the next run).
- `scanner.PLANETBIDS_SKIP` — portal IDs excluded from every scan (full and
  resume). For chronically-broken tenants that only cost CAPTCHA solves and keep
  `--resume` looping. City of Long Beach (`15810`) is skipped there.
- `rerun_planetbids.sh` loops the resume up to 4× with a cooldown (still needs a
  CAPTCHA solve each round).
- **Phase 2 (not done):** randomized inter-portal delay, persist `aws-waf-token`
  cookie between runs, session-health recheck, incomplete-coverage line in the
  scan-summary email.

### PlanetBids portal expansion — follow-up task

41 portals configured, but Orange / Ventura / San Diego coverage is still thin. IDs verified
2026-08: Long Beach 15810 (LA), Santa Ana 20137 (OC), Anaheim 14424 (OC, legacy → moved to
OpenGov), San Diego 17950 (SD). **Still to add** (resolve each ID by logging into the FCU
PlanetBids vendor account and checking which portals FCU is registered on):

- **Orange:** County of Orange, Irvine, Huntington Beach, Costa Mesa, Newport Beach, Fullerton,
  Orange, Garden Grove, Tustin, Westminster, Mission Viejo, Lake Forest, Fountain Valley
- **Ventura:** County of Ventura, Ventura, Oxnard, Thousand Oaks, Simi Valley, Camarillo, Moorpark
- **San Diego:** County of San Diego, Chula Vista, Oceanside, Escondido, Carlsbad, El Cajon,
  Vista, San Marcos, Encinitas, National City, Santee, Poway
- **CCDs:** Coast CCD, South Orange County CCD, Rancho Santiago CCD, Ventura County CCD,
  San Diego CCD, Grossmont-Cuyamaca CCD, MiraCosta CCD, Palomar CCD
- **LA gaps:** Santa Clarita, Inglewood, Compton, Whittier, Alhambra, Arcadia, Monrovia,
  Claremont, El Segundo, LA County Public Works

---

## Key Contacts (for Setup)

| Person | Role | What We Need |
|--------|------|-------------|
| Joanne | Bid Coordinator / Estimator | Portal credentials, Excel worksheet copy, rep contact list, sample past bid packages |
| Lenny | Field Estimator / PM | Job walk scoring criteria, labor hour estimates by job type, no-bid reasons |
| Sales Reps | Material Pricing | Email contacts per category (flooring, carpet, window coverings) |
| Insurance Agent | Bid Bonds | Contact, bond turnaround time, request format |
| DVBE Contact | Certification | Current cert docs + expiration date |

---

## Quick Reference

```
LABOR RATES
  Journeyman (Prevailing Wage): $108.00/hr
  Journeyman (Standard):        $100.00/hr
  Apprentice:                    $58.00/hr

MARKUP
  Default:   30% — always submit this first
  To win:    25% — owner must approve
  Below 25%: NEVER without owner sign-off

MATERIAL RULE
  Never estimate without a rep quote.
  Quotes > 30 days old = stale, must refresh.

EMAIL (Resend)
  New bids:    Digest fires automatically after each scanner run
  Job walks:   Alert fires automatically after parsing walk_required=True bids
```
