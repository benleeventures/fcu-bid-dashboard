# Notion Database Schema — FCU Sales Intelligence

Create three databases in Notion and link them as described below.
Copy each database ID from the URL: `notion.so/<workspace>/<DATABASE_ID>?v=...`

---

## Database 1 — Contacts

| Field | Type | Notes |
|---|---|---|
| Name | Title | Person's full name |
| Company | Text | GC, agency, or vendor |
| Contact Type | Select | GC / Agency / DVBE / Supplier |
| Email | Email | |
| Phone | Phone | |
| Assigned To | Select | Sales rep name |
| Status | Select | New / Contacted / Quoted / Won / Lost / Nurturing |
| Last Contacted | Date | Updated manually after each touchpoint |
| Next Follow-up Date | Date | Optional override — agent uses this if set |
| Notes | Text | Free-form, also read by AI |
| Created At | Created time | Automatic |

---

## Database 2 — Bids / Opportunities

| Field | Type | Notes |
|---|---|---|
| Bid Name | Title | Project name |
| Bid Number | Text | Agency reference number |
| Agency | Text | Who posted the bid |
| Estimated Value | Number | Dollar amount |
| Due Date | Date | Submission deadline |
| Status | Select | New / In Progress / Submitted / Won / Lost |
| Assigned To | Select | Sales rep |
| Contact | Relation | → Contacts database |
| Notes | Text | |

---

## Database 3 — Follow-up Log

Each row = one touchpoint. Reps add a row after every call, email, or meeting.

| Field | Type | Notes |
|---|---|---|
| Contact | Relation | → Contacts database (required) |
| Bid | Relation | → Bids database (optional) |
| Date | Date | When the touchpoint happened |
| Channel | Select | Email / Call / Meeting / LinkedIn |
| Summary | Text | 1–2 lines: what was said or sent |
| Outcome | Select | No reply / Positive / Negative / Meeting booked / Quote requested |
| Next Action | Text | e.g. "call back in 2 weeks" |
| Logged By | Select | Which rep |

---

## Setup Steps

1. Create all three databases in a Notion page (e.g. "FCU CRM")
2. Set up the Relation fields to link them
3. Create a Notion integration at https://www.notion.so/my-integrations
4. Share each database with the integration (click Share → Invite)
5. Copy each database ID into `.env`
