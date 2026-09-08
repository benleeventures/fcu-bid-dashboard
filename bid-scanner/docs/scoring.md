# Bid relevance filter + winnability score

Authoritative reference for how a bid gets from "scraped" to a GO / MAYBE / NO-GO /
NEEDS REVIEW verdict on the dashboard.

Two code paths, kept in lockstep:

| | File | When it runs |
|---|---|---|
| Relevance filter | `bid-scanner/scanner.py` (`_is_relevant`, `_is_non_flooring_service`) | every scan, on the title |
| Winnability score | `bid-scanner/scoring.py` + `app/lib/scoring.ts` | at parse time (stored) and live in the dashboard |

---

## 1. Relevance filter

FCU is a flooring + window-covering **wholesaler** that supplies product with or
without installation, **and** takes floor-care maintenance contracts (it holds a
quarterly CHP floor-maintenance job and wants more). So the filter keeps a wide net:

**Kept (`is_relevant = true`):**
- Flooring / window-covering **installation** — carpet, VCT, LVT, hardwood,
  resilient, tile, blinds, shades (`RELEVANT_KEYWORDS`).
- **Furnish-only / supply-only** — "furnish and deliver carpet tile", "flooring
  materials – supply only". Wholesale supply is real FCU work.
- **Install-only** — labor on owner-supplied material.
- **Floor / window-covering maintenance** (`FLOORING_SERVICE_PATTERNS`) — strip &
  wax, floor refinishing / buffing / sealing, carpet cleaning / extraction /
  shampoo, blind & drapery cleaning / repair, on-call flooring repair, seam repair.

**Dropped (`_is_non_flooring_service` → `is_relevant = false`):**
- Services with **no floor-covering component** (`NON_FLOORING_SERVICE_PATTERNS`) —
  janitorial, custodial, housekeeping, pest control, extermination, fumigation,
  grounds / landscape maintenance, exterior window / glass washing, pressure
  washing. A bare "carpet" or "floor" mention does **not** rescue these — only an
  affirmative install phrase or a flooring-service pattern does.

**Second pass:** construction-adjacent titles ("renovation", "school", "facility"…)
with no keyword hit go to Claude Haiku (`_claude_relevance`), which answers YES only
when flooring / window-covering work (install, supply, or maintenance) is the
**primary** scope — not one trade among many on a building remodel.

**Parser backstop:** `_EXTRACTION_PROMPT` extracts `non_flooring_service`; if the
docs reveal a bid is janitorial/pest/landscaping after all, `save_spec` flips
`is_relevant = false`.

---

## 2. Winnability score

Only three things move the number — they are what predict FCU *winning* a job it can
perform. Everything from the old 12-factor model (square footage, prevailing wage,
bid bond, job walk, DVBE, DBE) is gone.

```
score = geography(0–60) + lead_time(0–30) + award_adj(−6…+10)   → clamp 0–100

verdict:   score >= 58  → GO
           33–57        → MAYBE
           < 33         → NO-GO
```

### Geography (0–60) — drive time from the shop (9601 Cozycroft Ave, Chatsworth 91311)

Not a gate — the 4-county hard filter in `geo.py` still applies; this only lowers
the score for farther jobs. Resolved from `spec.project_city` (exact band) → else
`bids.county` (county default).

| Band | ~Drive | Score | Where |
|------|--------|-------|-------|
| A | ≤ 45 min | 60 | San Fernando Valley, Simi Valley, Thousand Oaks, Burbank, Glendale, Santa Clarita, Calabasas, Agoura Hills |
| B | ≤ 75 min | 48 | Central / DTLA, Pasadena, Culver City, Santa Monica, Alhambra; Oxnard, Ventura, Camarillo — **Ventura county default** |
| C | ≤ 110 min | 32 | South Bay, Long Beach, Whittier, Downey, Pomona; N. Orange County (Anaheim, Fullerton, Santa Ana) — **LA + Orange county default** |
| D | > 110 min | 16 | Deep S. Orange County (Irvine, Newport, Mission Viejo, San Clemente); all of San Diego county — **San Diego county default** |

City → band lists live in `geo.py` (`_BAND_A_CITIES` … `_BAND_D_CITIES`) and are
mirrored in `app/lib/scoring.ts`.

### Lead time (0–30) — days from today to `bids.due_date`

| Days out | Score |
|----------|-------|
| ≥ 21 | 30 |
| 14–20 | 24 |
| 10–13 | 15 |
| 7–9 | 8 |
| 4–6 | 3 |
| < 4 | 0 |

### Award adjustment (−6 … +10) — `spec.award_method`

| Method | Adj | Why |
|--------|-----|-----|
| `best_value` / `qualifications` | +10 | price plus other factors — FCU's compliance / past-performance story counts |
| `low_bid` | −6 | pure price fight; FCU's rates are now market-correct, not cheap |
| null (not stated) | 0 | |

---

## 3. Hard NO-GO (score 0, still listed)

- **`flooring_is_primary == false`** — flooring is a minor part of a larger
  multi-trade construction / renovation scope. Stays visible; `is_relevant`
  untouched.
- **Past due** — dashboard only (`scoring.ts`); the scanner leaves past-due
  archiving to `expirer.py`.

---

## 4. NEEDS MANUAL REVIEW (no score)

Shown whenever a scoring input is missing. The card lists exactly which:

| Code | Means | Trigger |
|------|-------|---------|
| `no_docs` | Bid documents not downloaded / parsed | no `bid_specs` row |
| `no_location` | Job location not identified | `bids.geo_status == 'unknown'` and no `project_city` |
| `no_due_date` | No bid due date on file | `bids.due_date` is null |
| `no_scope_read` | Scope not assessed by parser | spec exists but `flooring_is_primary` is null |

Stored as `bid_specs.go_verdict = 'review'`, `go_score = NULL`.

---

## 5. Storage

`bid_specs` columns (migration `supabase/add_scoring_v2.sql`):
`award_method`, `flooring_is_primary`, `project_city`, `bid_type` (display only),
plus `go_score` / `go_verdict` (now allows `'review'`).

Recompute all stored scores after a rule change: `python parser.py --recompute-scores`.
