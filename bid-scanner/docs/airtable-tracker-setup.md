# FCU Bid Tracker — Airtable setup (spec §5)

Base: **FCU Bid Tracker** (`appw7kb4Vuj6HPTYn`) · Table: **Opportunities** (`tblNz3qfw18c5Ngsa`)

The scanner writes new opportunities here automatically after each run
(`airtable_sync.sync_new_bids`). This doc covers the parts that must be set up
in the Airtable UI — the API can't do them.

---

## 1. Fields — already in place

| Column (spec §5) | Airtable field | Notes |
|---|---|---|
| Date surfaced | `Date Surfaced` | set by scanner |
| Source platform | `Source Platform` | single-select, scanner auto-adds new options |
| Agency or GC | `Agency or GC` | set by scanner |
| Project name | `Project Name` | set by scanner |
| County | `County` | single-select (LA / Orange / Ventura / San Diego); blank + a "Needs county check" note when unconfirmed |
| Estimated value | `Estimated Value` | currency; scanner fills it only once a value is known (post-parse) |
| Bid due date | `Bid Due Date` | set by scanner; **default sort** |
| Job walk date | `Job Walk Date` / `Job Walk Mandatory` | filled by `parser.py` after the spec PDF is parsed |
| Status | `Status` | Surfaced → Qualified → Estimating → Submitted → Won / Lost / Passed |
| Owner | `Owner` | see §3 below |
| Result | `Award Amount` + `Winner` | filled at close-out |
| Tabulation link | `Tabulation Link` | filled at close-out |
| Notes | `Notes` | scanner writes the geo-uncertainty flag here |
| — | `Days to Due` | formula: `DATETIME_DIFF({Bid Due Date}, TODAY(), 'days')` — drives the colour rules below |

---

## 2. Conditional formatting — DO THIS IN THE UI

Airtable colours records per **view**, so create a working view with two rules.

1. Open the **Opportunities** table → the view selector (top-left) → **Duplicate**
   "Grid view" → rename it **Robert — Pipeline**.
2. **Sort:** `Bid Due Date` → ascending (A→Z). Add a second sort on `Status` if you like.
3. **Filter** (so closed rows fall off): `Status` `is none of` `Won`, `Lost`, `Passed`.
4. Click **Color** (paint-roller icon in the view toolbar) → **Add a condition**, in
   this order (first match wins, so the tighter rule goes on top):

   | Order | Condition | Colour |
   |---|---|---|
   | 1 | `Days to Due` `≥ 0` **and** `Days to Due` `≤ 2` | **Red** |
   | 2 | `Days to Due` `≥ 0` **and** `Days to Due` `≤ 5` | Yellow / amber |

   (`Days to Due` goes negative once a bid is past due — the `≥ 0` guard keeps
   expired rows uncoloured; the `expirer.py` job archives them separately.)

5. Set this view as the table's default (view selector → drag it to the top, or
   "…" → **Set as default view**) so Robert lands on it.

Result: Robert opens the tracker and the next-48-hours bids are red, the
next-5-days bids are amber, everything else is plain — no reading required.

---

## 3. Owner default (spec §5: "Robert by default")

`Owner` is a single-collaborator field, so the value has to be a real base
collaborator. Once Robert has an Airtable seat on this base:

- **Option A (no code):** in the **Robert — Pipeline** view, right-click the
  `Owner` column header → **Edit field** → set a default? Airtable single-select
  has defaults but single-collaborator does not, so instead:
- **Option B (scanner sets it):** add to `bid-scanner/.env`:
  ```
  AIRTABLE_OWNER_EMAIL=robert@floorcoveringunlimited.com
  ```
  `airtable_sync` will stamp every new row's `Owner` to that person. If the
  email isn't a collaborator yet the create silently falls back to core fields,
  so it's safe to set ahead of time — but it won't take effect until he's added.

---

## 4. Keeping it clean

- The scanner only ever **creates** rows (matched on `Bid ID`); it never edits
  a row Robert has touched.
- `parser.py --save` back-fills `Job Walk Date` / `Job Walk Mandatory` on the
  existing row once a spec PDF is parsed.
- Rows flagged **"Needs county check"** in `Notes` are `geo_status = unknown` —
  Robert confirms the county and clears the note during qualification.
