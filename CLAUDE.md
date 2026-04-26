# FCU — Floor Covering Unlimited

## Client Overview
- **Business:** Floor Covering Unlimited, Inc. (FCU)
- **Type:** Commercial flooring contractor, Chatsworth, CA
- **Founded:** 50+ years, family-owned (Ben, Joanne, Lenny, Melvin, Harry Lee)
- **License:** C-15 | Union: IUPAT Local 1247 (District Council 36) | DVBE certified
- **Revenue:** ~$1.06M FY26 | **Situation:** 3-year loss streak ($202K total) — turnaround in progress
- **Primary contact:** Ben Lee (Sales Manager / Strategist)
- **Website (Framer preview):** https://sleepy-connection-873159.framer.app/
- **Full context:** `context/FCU_context.md` — read before any strategic work

## Team
- **Ben Lee** — Sales, strategy, main point of contact. Also runs re:center (capacity constraint).
- **Joanne Lee** — VP Ops, pricing, bids, certified payroll
- **Lenny** — Field Ops, IUPAT relations (highest-leverage GC referral channel)
- **Melvin** — Field Ops, primary client relationships, has undocumented CHP maintenance contract
- **Leo** — Research/Systems (bid monitoring, CRM, competitive intel)

## Critical Context
- **Root cause of losses:** Laborer rate priced at $44.32/hr vs. market $80–91/hr. Explained by using expired IUPAT rate. $202K in losses traces entirely to this.
- **LAUSD TOPO contract** (Jul 2023–Dec 2027, $3M ceiling) is the primary asset. Mid-contract repricing not possible. **2027 renewal = the single most important event.**
- **No new bids at old rates.** Corrected targets: Technician $107–$112, Laborer $80–$85.
- **Sale deprioritized** — turnaround + 2027 renewal first.

## What They Do
Commercial flooring installation: carpet, hard surface, blinds, ceiling work, hospitality and institutional renovations. Primary: government/public works. Expanding: hospitality GCs, TI contractors.

## Key Differentiators
- Security-cleared, background-checked, union-credentialed installers
- Government and federal compliance expertise (LAX, US Air Force, CHP, LAUSD)
- Complete closeout documentation upfront
- DVBE certified

## Brand
**Headline:** "When the Job Has Requirements — We Already Meet Them."
**Aesthetic:** Charcoal `#1C1C1E`, Gold `#C8922A`, Cream · Barlow Condensed, IBM Plex Mono
**Voice:** Professional, compliance-focused, zero-fluff. Audience = GCs and procurement officers.

## Active Systems
- **Framer site** — current website (preview above), primary marketing asset
- **Sales Intelligence System** — AI-powered daily digest agent + Notion CRM (`agent/`)
- **AI Bid Agent** — 9-step bid pipeline from portal monitoring → submitted package (`bid-scanner/`) → see `ROADMAP.md`

> **ROADMAP.md** — always read this before any bid agent work. Contains current build status, pricing rates, phase checklist, and portal coverage.

## Sales Intelligence System
Proposal approved. Architecture: Notion (database) → Python agent → Claude API → Gmail digest.

**Notion databases:** Contacts, Bids/Opportunities, Follow-up Log (linked)
**Agent:** runs daily, queries all three DBs, calls Claude for follow-up suggestions, sends Gmail digest
**Hosting:** Cloud Run scheduled job or Mac mini cron

**Build order:**
1. Notion DB setup (manual by client)
2. Python agent — Notion API queries + follow-up logic (`agent/`)
3. Gmail API integration — sends morning digest
4. Claude API — generates per-contact AI suggestions
5. Test with sample data → hand off

**Notion DB schema:** see `agent/notion_schema.md`

## Stack
- Frontend: Framer
- Automation: Python 3.11+
- Database: Notion API (free tier)
- AI: Claude API (`claude-sonnet-4-6`)
- Email: Gmail API
- Hosting: Cloud Run (scheduled) or local cron

## Primary CTA
"Submit Your Scope" — contact form for project bidding

## Notes
- Family-owned, not a franchise — important brand differentiator
- Primary audience is GCs and procurement officers, not homeowners
- Documentation and compliance are the core sales arguments
