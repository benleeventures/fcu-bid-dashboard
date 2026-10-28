# Robert's prospect tab (Phase 2 · Priority 3)

Two tables in the bid tracker base (`appw7kb4Vuj6HPTYn`), next to Opportunities:

| Table | What it holds |
|---|---|
| **Prospects** | One row per senior living / care center / hotel. Status: New → Visited → Quoted → Monthly contract signed / Not a fit. `Follow-up Due` shows ⏰ when the next step date is today or past. `Contract Signed Date` feeds Friday scoreboard #4. |
| **Visits** | One row per visit, from Robert's phone form. `Visit Date` is filled automatically (created time). Linked to the property, so every property shows its visit history. |

`bid-scanner/prospects.py` creates both tables (`--setup`, idempotent) and
imports prospects from a CSV (`--seed FILE`, skips names already there). The
starting 42 rows are in `data/prospects_seed.csv`: the three contacts from Ben's
scope, plus Anaheim, Orange County and San Diego senior living and skilled nursing
properties from public directories (`Source = Research`).

**Robert's own list** (32 hotels + 15 senior living in Anaheim) isn't in info@.
Get it from him as a spreadsheet, save it as CSV with the column names used
in the seed file, then run:

```bash
cd ~/fcu-cron/bid-scanner
python ../../fcu/bid-scanner/prospects.py --seed robert_list.csv --dry-run   # preview
python ../../fcu/bid-scanner/prospects.py --seed robert_list.csv             # write
```

(or run it from the merged checkout; set `Source` to `Robert's list`).

## One-time UI setup (about 10 min; the API can't create forms, views or automations)

### 1. "Log a visit" form (Visits table)
1. Visits → **+ Create** → **Form**. Name it `Log a visit`.
2. Fields, in this order. Mark the first two **required**:
   - **Property** (search by name)
   - **Status Now**
   - **Next Step**
   - **Next Step Date**
   - **What They Said**
   - **Contact Met**
   - **Photo**
3. Leave Visit Date off the form, because it fills itself.
4. Turn on **"Show a 'Submit another response' button"**.
5. **Share form** → copy the link. On Robert's iPhone, open it in Safari, tap
   Share, then **Add to Home Screen**. One tap opens the form, with no login.
   (Anyone with the link can submit. The property picker only shows property
   names, never contacts.)

### 2. Automation: a visit updates its property
Automations → **Create automation** → name `Visit → Prospect`.
- **Trigger:** When a form is submitted. Choose the `Log a visit` form.
- **Action:** Update record.
  - Table: **Prospects**.
  - Record ID: *Property → Airtable record ID* (from the trigger record).
  - Set these fields:
    - Last Visit Date = *Visit Date*
    - Status = *Status Now*
    - Next Step = *Next Step*
    - Next Step Date = *Next Step Date*
- Test with a real visit, then turn it **on**.

Second automation, `Contract signed date`:
- **Trigger:** When a record matches conditions. Table Visits, where Status Now
  is `Monthly contract signed`.
- **Action:** Update record in Prospects. Use the same Record ID, and set
  Contract Signed Date = *Visit Date*.

### 3. Views on Prospects
| View | Setup |
|---|---|
| `Robert — follow up` (grid) | Filter: Follow-up Due is not empty. Sort: Next Step Date ascending. |
| `By city` (grid) | Group by City. Filter: Status is not Not a fit. Hide Address and Source. |
| `Pipeline` (kanban) | Stack by Status. Card fields: City, Contact Name, Next Step Date. |
| `Signed contracts` (grid) | Filter: Status = Monthly contract signed. Sort: Contract Signed Date descending. The Friday scoreboard (#4) reads this view. |

### 4. Robert's access
Robert (robert@floorcoveringunlimited.com) is already on the base as a
collaborator. On his phone: install the Airtable app, sign in, then open the
FCU base → Prospects → `Robert — follow up`. Check that he can edit a record
before the walkthrough.

## The 30-minute walkthrough with Robert (side by side, no manual)

| Min | What |
|---|---|
| 0–5 | Open the app on **his** phone. Prospects → `By city` → Anaheim. He reads his own territory. |
| 5–12 | Fix the seed together: say which Belmont and which Ivy community his contacts are at, move the contact, delete the two placeholder rows. Add 2–3 places from his own list by hand (+ in the app). |
| 12–20 | He logs a **real** visit from the home-screen form, timed. Target: under 60 seconds. Show the property updating (status, next step, last visit). |
| 20–25 | `Robert — follow up` = his to-do list each morning. `Pipeline` = where every place stands. |
| 25–30 | Agree how he'll send his 32-hotel / 15-senior list (spreadsheet or photos) so we can import it. Agree the habit: log every visit before driving off. |

Done when (Nov 14): Robert logs a visit from his phone in under a minute.
