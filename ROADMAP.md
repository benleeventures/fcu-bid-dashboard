# FCU — AI Bid Agent Roadmap
**Last updated:** 2026-04-27 (infrastructure v1 plan)

> Always read this before any bid agent work. Contains current build status, pricing rates, phase checklist, and portal coverage.

---

## Current Status

| System | Status | Notes |
|--------|--------|-------|
| Bid Scanner (SAM.gov + PlanetBids + BidNet) | ✅ Running | CA filter applied |
| Dashboard (Next.js + Supabase) | ✅ Live on Vercel | Showing bid results |
| Estimate Worksheet | ✅ Done | In dashboard — labor rates, 25/30% markup, approve flow |
| Document Download | ✅ Done | Playwright-based, all sources |
| AI Parsing → bid_specs | ✅ Done (manual mode) | `--parse-all` prints prompts for Claude Code; `--ollama` for auto |
| New-Bid Email Digest | ✅ Done | Fires via Resend after each scanner run with new relevant bids |
| Job Walk Alert Email | ✅ Done | Fires via Resend when `walk_required=True` after parsing |
| Compliance Alert Email | ✅ Done | Fires via Resend on `--save` when bid_bond/prevailing_wage/dvbe/dbe flags set |
| RFQ Email Generator | ✅ Done | `--rfq <bid_id>` CLI + "Send RFQ →" button in dashboard; To (rep) + Joanne always CC'd |
| Scheduler | 🔄 In progress | SAM.gov + BidNet: launchd cron 6am (headless). PlanetBids: manual CLI, headful Chrome, human solves CAPTCHA. |
| BidNet Direct (public listing page) | ⛔ Login-only | Public listing page permanently login-gated; not automatable. Doc download via cookie-auth still works. |
| LAUSD Portal | ⬜ Not connected | High priority — TOPO renewal 2027 |
| AI RFQ Generator | ⬜ Phase 3 | |
| Compliance Auto-Checker | ⬜ Phase 3 | Compliance fields exist in bid_specs, no alert yet |
| Bid Package Assembler | ✅ Done | `/api/bids/[id]/package` — PDF download from dashboard |
| Bid Results Tracking | ✅ Done | Status badges, win/loss tracker, amount fields in bid detail + table filter |
| Go/No-Go Scoring | ✅ Done | Score pill in table + GoNoGoCard in bid detail; 9-factor model (scope, SF, PW, deadline, etc.) |
| Dashboard UX | ✅ Done | Light cream theme, archive/restore bids (no-bid), "No docs" badge, portal button |
| Competitive Intelligence | ⬜ Phase 4 | |

---

## Immediate Next Steps

### 1. Test AI Parsing + Notifications
Env vars needed in `bid-scanner/.env`:
```
RESEND_API_KEY=your_resend_api_key_here
NOTIFY_EMAIL=gutarra.leonardo@gmail.com
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
| 5 | Material Quote Requests (RFQs) | Agent drafts / Joanne approves | ✅ Done — dashboard button sends to rep; Joanne always CC'd |
| 6 | AI-Powered Estimate Worksheet | Agent + Joanne | ✅ Done (dashboard) |
| 7 | Compliance & Requirements Check | Agent | ⚠ Fields captured in bid_specs, no alert email yet |
| 8 | Bid Package Preparation | Agent + Joanne signs | ✅ Done — PDF bid package download in dashboard |
| 9 | Submission, Tracking & Learning | Joanne submits / Agent logs | ✅ Done — outcome tracker: status, submitted amount, award amount |

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
- [ ] Ollama/LLaMA 3 local model for auto-parsing (replace manual mode)

### Phase 4: Intelligence
- [x] Bid results tracking and logging — status badges, win/loss, submitted/award amounts
- [x] Go/no-go scoring model — 8-factor score (scope, SF, prevailing wage, DVBE, etc.) — deadline proximity removed; system catches bids early
- [ ] Competitive intelligence dashboard (win/loss by agency, job type)
- [ ] Markup recommendation engine

### Phase 5: Infrastructure (Mac Mini)
- [ ] `agent_state.py` — shared heartbeat writer for all agents
- [ ] `supervisor.py` — Ollama (llama3.2:3b) watchdog: heartbeats → restart | escalate to Claude API → email Leo
- [ ] `digest.py` — daily 7am email to Joanne + Ben: new relevant bids since yesterday
- [ ] `jobwalk.py` — daily 7:15am: GO-scored bids with walk_required → email Lenin once per bid
- [ ] `expirer.py` — daily 7:30am: auto-archive past-due unbid bids (status=`expired`)
- [ ] launchd plist files for all scheduled agents
- [ ] Mac Mini setup runbook (`setup/mac-mini-setup.md`)
- [ ] `walk_notified` column added to `bids` table in Supabase
- [ ] All recipient emails as env vars (JOANNE_EMAIL, BEN_EMAIL, LENIN_EMAIL, ADMIN_EMAIL)

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
| SAM.gov | ✅ Active | Federal contracts, CA filter applied |
| PlanetBids | ✅ Active | Cookies-based auth working |
| BidNet Direct | ⚠ Partial | Doc download works; public listing page blocked by bot detection |
| LAUSD | ⬜ Not connected | Highest priority — TOPO contract renewal 2027 |
| City of LA | ⬜ Not connected | Phase 1 expansion |
| County of LA | ⬜ Not connected | Phase 1 expansion |
| Long Beach Unified | ⬜ Not connected | Phase 1 expansion (DVBE required) |

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
