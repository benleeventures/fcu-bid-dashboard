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

## Multi-Session Git Workflow
Multiple Claude Code sessions run in parallel, one branch per session. Follow this every session:

1. **Separate working directory per session.** Never run two sessions on different branches in the same folder — a `checkout` in one corrupts the others. Use `git worktree add ../fcu-<branch> <branch>` (or the `EnterWorktree` helper) or a separate clone.
2. **One branch = one scoped, non-overlapping change.** Keep sessions in different areas (`bid-scanner/`, `agent/`, docs). Merge and delete branches fast — don't let them live for days.
3. **Sync main before every merge:** `git fetch origin` → `git rebase origin/main` → **re-run tests/build on the result.** A branch that passed in isolation can break once other sessions' work lands under it.
4. **Merge via PR, not direct to main** (`gh pr create`), even solo — gives a diff to eyeball. Serialize merges: don't let sessions race. Prefer one integrator (usually Leo) merging PRs one at a time.
5. **After any merge, rebase the other sessions** onto the new main so they don't reintroduce stale code or hit avoidable conflicts.
6. **Shared files are conflict magnets** — `ROADMAP.md`, `CLAUDE.md`, `context/`, plan docs, lockfiles. Edit these on their own tiny branches merged immediately, or keep each session's edits in its own section.

Answer to "can I just tell any session to push and merge to main?" — only safely if branches don't overlap AND the session syncs main and re-verifies first. Otherwise expect conflicts or silent regressions.

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
