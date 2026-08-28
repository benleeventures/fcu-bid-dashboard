# McWil Sports Surfaces — competitor bid intel (ad-hoc)

One-off intelligence request (Ben, Aug 2026): find PlanetBids gym-floor
solicitations where McWil Sports Surfaces bid or won, to reverse-engineer their
$/SF pricing. Not part of normal bid-scanner operations. Everything here writes
only to this folder — nothing touches the production Supabase / Airtable pipeline.

| File | What |
|------|------|
| `PLAN.md` | approach + decisions |
| `phase0-osint.md` | public-record findings (board agendas, council resolutions) |
| `sweep.py` | PlanetBids awarded-bid sweep — the main tool |
| `debug_papi.py` | one-shot inspector for the PlanetBids `/papi/bids` API |
| `build_csv.py` | collapse `results_raw.json` → one flat CSV |
| `mcwil_intel_results.csv` | **the deliverable** |
| `all_awarded.json` | every awarded title per portal (keyword-filter QA) |
| `results_raw.json` | full structured capture (bidders + amounts per bid) |
| `papi_dump_23758.json` | reference capture of the API request/response shape |

## Outcome (first pass, 16 portals, ~3,125 awarded contracts)

**McWil appears in zero tabulations.** These portals are LA-county *cities* +
a handful of education agencies — the wrong hunting ground. McWil's wood-gym-floor
work is on K-12 district / community-college portals (LAUSD, Santa Ana USD,
Cerritos/Rio Hondo/Mt. SAC/Rancho Santiago CCDs…) whose portal IDs we still need
to resolve, or it's sub-tier inside GC packages. See `PLAN.md` §7 for the
second-pass list.

## Running the sweep

Needs a real screen — you solve one CAPTCHA per PlanetBids tenant.

```bash
cd intel/mcwil-sports-surfaces

python sweep.py                       # first pass: 16 verified portal IDs
python sweep.py --resume              # retry only blocked/unfinished portals
python sweep.py --portals 23758,41631 # specific portals
python sweep.py --discover            # harvest more portal IDs by browsing
python build_csv.py                   # regenerate the consolidated CSV
```

Chrome opens on the first portal. Solve the CAPTCHA, wait for the bid list, press
Enter. It pages through every portal's full awarded history (scrolls the list to
lazy-load all `/papi/bids` pages), pulls each sports-flooring award's tabulation,
and flags any row containing the target vendor.

**No login.** PlanetBids retired the global vendor login (`/login` → "not a valid
agency portal"). Awarded tabulations are readable unauthenticated. Portal IDs
must be supplied explicitly — there's no cross-agency search.

## Reusing this for a different vendor / trade

1. Copy this folder to `intel/<new-target>/`.
2. In `sweep.py`: edit `SPORTS_KEYWORDS` (the trade filter), `MCWIL_RE` /
   `is_mcwil` (the target-name matcher), and `HIGH_PROB_IDS` / `EXTRA_PORTALS`
   (which portals to hit — education vs. cities vs. counties depends on the trade).
3. In `build_csv.py`: set `TARGET`.
4. `python debug_papi.py <cid>` first if PlanetBids' API has changed since Aug 2026
   (the `/papi/bids` params or `em-version` header) — it dumps the current shape.

## Getting to $/SF

`mcwil_intel_results.csv` gives award **amounts**. $/SF = amount ÷ project square
footage, which comes from the bid form / plans per project — a manual second pass
once real McWil rows exist.
