# `intel/` — ad-hoc competitive intelligence

One folder per investigation. These are **one-off** research tasks (a client asks
"what does competitor X charge for Y?"), kept separate from the production
`bid-scanner/` pipeline. They reuse `bid-scanner/` helpers but write nothing back
to Supabase / Airtable.

| Folder | Ask | Status |
|--------|-----|--------|
| `mcwil-sports-surfaces/` | McWil Sports Surfaces gym-floor $/SF pricing (PlanetBids) | first pass done — 0 hits in city portals, needs school-district portal IDs |

## Pattern

Each folder has a `PLAN.md` (approach + decisions), a `README.md`, a runnable
sweep/scraper, and its deliverable CSV. To start a new one, copy the closest
existing folder and adjust the target vendor, trade keywords, and portal list —
see that folder's README "Reusing this" section.
