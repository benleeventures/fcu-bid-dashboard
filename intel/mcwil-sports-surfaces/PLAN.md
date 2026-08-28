# Ad-hoc Intel Request — McWil Sports Surfaces $/SF Bid Parameters

**Requested by:** Ben (client) · **Analyst:** Leo · **Opened:** 2026-08-28
**Branch:** `intel/mcwil-sports-surfaces` · **Workspace:** `intel/mcwil-sports-surfaces/`
**Status:** APPROVED 2026-08-28 — building `sweep.py`

## Decisions (Ben, 2026-08-28)

1. **Scope:** include ALL McWil surface types — wood gym floors, synthetic/poured
   urethane, rubber, running tracks, outdoor sport courts. Same competitor, same
   $/SF logic, more data points.
2. **Auth:** ~~use `PLANETBIDS_EMAIL` to scrape the registered-agency list~~ —
   **NOT POSSIBLE.** PlanetBids retired the global vendor login (2025): a bare
   `vendors.planetbids.com/login` returns *"This is not a valid PlanetBids agency
   portal"*. Login is per-agency only; there is no cross-agency search or
   account-wide portal list. **But we don't need login** — awarded-bid
   tabulations are readable unauthenticated (the existing intel scan never logged
   in). Portal IDs are supplied explicitly. `--discover` now = manual harvest:
   browse agency bid pages in the live Chrome window, scoop `/portal/<id>/` links.
3. **Geo:** keep McWil's out-of-footprint awards (NorCal / Central Valley) as
   reference pricing, tagged `out_of_footprint = true`.
4. **Effort:** first pass = FCU-registered portals + a small curated
   K-12/CCD list. Review yield, then decide whether to go wider.
5. **Final output:** `MEMO.md` is a one-time deliverable — content will be
   pasted into WhatsApp. Keep it short and copy-paste friendly. No permanent
   docs, no memory entry, no production-pipeline changes.

## Portal IDs found so far (Phase 0)

| Agency | Portal ID | In current list? |
|--------|-----------|------------------|
| Long Beach Unified School District | `23758` | no — ADD |
| Port of Long Beach | `19236` | yes |
| City of Long Beach | `15810` | yes |
| LA Community College District | `21372` | yes |

---

## 1. The ask (verbatim)

> Search PlanetBids for gym-floor solicitations where **McWil Sports Surfaces**
> (Gardena, CA) either **bid** the job or **won** the bid. We are trying to
> determine what **per-square-foot** parameters they use to bid a job, so we can
> effectively bid against them.

**Deliverable:** a data table of every awarded gym-floor / sports-surface
solicitation with **bid results shared publicly**, showing McWil's bid amount,
where they ranked, who beat/lost to them, the project square footage, and the
derived **$/SF**.

This is a **one-off intelligence request**, not a change to normal bid-scanner
operations. All work lives in `intel/mcwil-sports-surfaces/`. Existing
`bid-scanner` code is *reused, not modified* (any tweak needed goes in a local
copy/wrapper in this folder).

---

## 2. Who McWil is (scope of what to search for)

Gardena, CA (135 W 155th St). Athletic-surface specialty contractor — **not** a
carpet/VCT flooring contractor. Product lines (from mcwilss.com):

| Line | Typical solicitation language |
|------|-------------------------------|
| Wood athletic flooring | "gymnasium floor", "wood gym floor", "hardwood athletic flooring", "maple floor", refinish / sand & recoat |
| Rubber athletic flooring | "rubber flooring", "weight room floor", "fitness floor" |
| Synthetic / poured urethane | "poured urethane", "synthetic sports floor", "resilient athletic surface", "MPR floor" |
| Outdoor surfaces | "sport court", "running track resurfacing", "rubberized track", "outdoor basketball court" |
| Turf | "athletic field turf" (usually a sub scope) |

McWil buyers are overwhelmingly **K-12 districts, community-college districts,
and city parks & rec** — not the LA-county *cities* that dominate the current
`PLANETBIDS_PORTALS` list.

---

## 3. What we already have (reuse targets)

`bid-scanner/intel_scanner.py`:
- `_scan_awarded_portal(page, portal_id, agency, mode=)` — pulls a portal's
  `/papi/bids`, keeps `stageStr == "awarded"`. **Filters through `_is_relevant`
  (carpet/VCT-biased) — needs a sports-flooring keyword override for this job.**
- `_fetch_bid_detail(page, portal_id, numeric_bid_id)` — opens the award detail
  page, captures the **submission tabulation** (every bidder + amount) + winner.
  Currently **sums away line items** — for this job we want to *keep* any
  square-footage unit-price line.
- `resolve_vendor` / `_name_overlap` — company-name normalization.

`bid-scanner/scanner.py`:
- `PLANETBIDS_PORTALS` — ~40 portals, mostly LA-county cities. Only LACCD /
  LACOE / Cal State LA on the education side.
- Playwright + live-CAPTCHA session pattern in `main.py --intel`.

Supabase `bid_intel` / `bid_intel_submissions` / `vendors` — currently 2 awards,
56 vendors, **no McWil, no gym-floor awards**. Not useful as-is.

---

## 4. Constraints & reality checks

1. **Post-award only.** PlanetBids shows tabulations only after a bid is awarded
   and results are published. Open/in-progress solicitations give nothing.
2. **Registered-vendor visibility.** FCU can only see tabulations on portals
   where FCU has a vendor account. Some agencies hide the tab entirely.
3. **Sub-bids are invisible.** When McWil subs to a GC on a gym *renovation*,
   they won't appear in the prime tabulation. Best signal = districts that
   procure the gym floor as a direct prime contract.
4. **$/SF is derived, not published.** Award amount is a lump sum. Square footage
   comes from (a) a unit-price line item in the bid schedule, or (b) the bid
   form / plans, or (c) a manual estimate (HS main gym ≈ 8,000–12,000 SF;
   practice gym / MPR ≈ 3,000–6,000 SF). Every $/SF figure will be tagged with
   its SF source and a confidence level.
5. **Geo.** Stay in the 4-county footprint (LA / Orange / Ventura / San Diego)
   for direct relevance, but McWil's statewide awards are still useful reference
   points — capture them, tag them out-of-footprint.
6. **CAPTCHA.** The sweep needs a human (Leo) to solve one AWS-WAF challenge per
   PlanetBids tenant at run time. Not fully autonomous.

---

## 5. Plan

### Phase 0 — Public-record OSINT (in progress, no code)
Board agendas / BoardDocs / city-council resolutions publish award actions with
dollar amounts verbatim. Sweep:
- Google + BoardDocs for `"McWil Sports Surfaces"` + award / bid / resolution
- CA county & city Legistar portals
- Maple Flooring Mfrs Assn / USA-NTC project references
- `californiabids.com`, `bidnetdirect` public award notices

Output: `phase0-osint.md` — every hit with agency, project, date, amount, source
link. **Early result: thin.** One confirmed (Oakland Rainbow Rec Center gym
renovation, Good Tidings Foundation-funded, ~$52K total scope — out of footprint,
donor-funded so not a competitive price signal).

### Phase 1 — Targeted PlanetBids awarded-bid sweep (ad-hoc script)
`intel/mcwil-sports-surfaces/sweep.py` — a standalone runner that imports helper
functions from `bid-scanner/` but writes nothing to the production pipeline:

1. **Portal set** = current `PLANETBIDS_PORTALS` **+** a `SCHOOL_PORTALS` list
   added *in this folder only* (SoCal K-12 + CCD PlanetBids tenants — IDs
   resolved from the FCU vendor account; where FCU isn't registered, note it and
   check if results are public anyway).
2. For each portal: load `bo-search`, **page through the full awarded-bids list**
   (not just page 1 — the current code grabs one `/papi/bids` response; the
   sweep will paginate/scroll until the list is exhausted).
3. Keep any award whose title/description matches the **sports-flooring keyword
   set** (§2) — a local override, not `_is_relevant`.
4. For each hit: `_fetch_bid_detail` → full tabulation. Keep the row if **McWil
   appears as any bidder or the winner** (fuzzy match: "mcwil", "mcwill",
   "mc wil", "mcwil sports"). Also keep non-McWil gym-floor awards as
   competitor-context rows (secondary tab).
5. **Square-footage capture:** preserve bid-schedule line items; regex for
   `sq\.?\s?ft|\bSF\b|square f` + quantity + unit price. Download the bid form /
   ITB PDF to `intel/mcwil-sports-surfaces/docs/` for manual SF confirmation.
6. Write results to `results.csv` + `findings.md`.

### Phase 2 — Analysis & memo
`intel/mcwil-sports-surfaces/MEMO.md`:
- Table: agency · project · award date · SF · SF source/confidence · McWil bid $ ·
  McWil rank · winner · winning $ · **McWil $/SF** · spread to next bidder
- McWil $/SF range by surface type (wood vs. synthetic vs. track)
- Where McWil sits vs. field (aggressive / middle / high)
- How much room FCU needs to beat them, and on which project types McWil is
  beatable
- Data-quality caveats

---

## 6. Deliverables checklist

- [ ] `phase0-osint.md` — public-record hits
- [ ] `SCHOOL_PORTALS` list (IDs + FCU-registration status)
- [ ] `sweep.py` — ad-hoc runner (no writes to prod Supabase/Airtable)
- [ ] `results.csv` — raw rows
- [ ] `docs/` — downloaded bid forms / tabulation PDFs
- [ ] `MEMO.md` — the answer for Ben

---

## 7. Open questions for review

1. **Scope of "gym floor"** — just wood/synthetic *indoor gym floors*, or also
   McWil's running tracks + outdoor sport courts? (Recommend: include all — same
   competitor, same $/SF logic, more data points.)
2. **Portal list** — OK to pull the FCU PlanetBids vendor account to enumerate
   which school-district portals FCU can see tabulations on? Need Joanne's login
   if not already in `bid-scanner/.env` (`PLANETBIDS_EMAIL` is set — will try
   that first).
3. **Statewide reference data** — keep McWil's out-of-footprint awards (NorCal,
   Central Valley) as pricing reference, or strictly 4-county? (Recommend: keep,
   tagged.)
4. **Effort ceiling** — how many portals / how deep? A full SoCal school-district
   sweep is ~40–60 additional portals and several CAPTCHA solves. Recommend a
   first pass on the ~15 highest-probability portals, review yield, then decide.
