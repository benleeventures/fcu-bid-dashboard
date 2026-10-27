# Email intake: info@ bid invitations → Airtable

`bid-scanner/email_intake.py` runs every 15 minutes (launchd job `com.fcu.emailintake`).
It reads info@floorcoveringunlimited.com through the Gmail API with **read-only**
access, keeps bid invitations, and creates one Airtable Opportunities record for each
(Source Platform = Email, with Region and Owner filled in).

- **Read-only.** It can't mark mail read, move, delete or send anything.
- **Attachments are never opened.** Only their filenames go into Notes.
- **Links are stored, never fetched.**
- **The block list** is `data/email_blocklist.json`. Junk on it is skipped before any Claude call.

## One-time setup

### 1. Google OAuth client (about 10 minutes, in a browser signed in as info@)

1. Go to https://console.cloud.google.com and sign in as **info@floorcoveringunlimited.com**.
2. Create a project named **FCU Email Intake**.
3. Go to **APIs & Services → Library → Gmail API → Enable**.
4. Go to **APIs & Services → OAuth consent screen** and set:
   - User type: **Internal**. This works because info@ is on Google Workspace, and it means no Google review and no 7-day token expiry.
   - App name: FCU Email Intake.
   - Support email: info@.
5. Go to **APIs & Services → Credentials → Create credentials → OAuth client ID**.
   - Type: **Desktop app**. Name: FCU Email Intake.
6. Click **Download JSON** and save it as `~/fcu-cron/bid-scanner/gmail_intake_client.json`.

If step 4 shows "Internal" greyed out, the Workspace admin console is blocking it.
Choose **External** instead and add info@ as a test user. External test-mode tokens
expire after 7 days, so publish the app once it works.

### 2. Sign in once

```bash
cd ~/fcu-cron/bid-scanner
python email_intake.py --auth
```

A browser opens. Sign in as info@ and approve **"View your email messages and settings"**.
The token is saved to `gmail_intake_token.json` (gitignored, mode 600).

### 3. Airtable fields

```bash
python email_intake.py --setup-airtable
```

This creates the following fields on Opportunities, if they're missing:

| Field | Type |
|---|---|
| Date Received | date + time |
| Sender Company | text |
| Email Link | URL |
| Decision | Yes / No / Maybe |
| Decision Date | date |

Airtable's API can't create formula fields. Add **Decision Overdue** by hand with the
formula the command prints. It shows 🔴 when an invitation is more than 48 hours old
with no Decision.

### 4. Dry run on real mail, then turn it on

```bash
python email_intake.py --dry-run --since 2026-10-01 --limit 80
```

Read the output. Add any estimating or takeoff senders that got through to
`data/email_blocklist.json`. Then load the job:

```bash
bash setup/launchd/install.sh        # from the primary checkout
```

The first scheduled run looks back 3 days (`GMAIL_INTAKE_BACKFILL_DAYS`). After that,
each run picks up where the last one stopped (`output/email_intake_state.json`).

## MSN

floorcoveringunltd@msn.com forwards into info@. To check that forwarding is complete,
search info@ for `to:floorcoveringunltd@msn.com newer_than:7d`. If recent alerts from
the MSN inbox are missing there, sign in to Outlook.com once and go to
**Settings → Mail → Forwarding** to turn it on (keep a copy). The intake never reads MSN directly.

## Logs

- `logs/email_intake.log` has one line per message: blocked, skipped (vendor or phishing), created or duplicate.
- `logs/emailintake.cron.log` has launchd output and crashes.
