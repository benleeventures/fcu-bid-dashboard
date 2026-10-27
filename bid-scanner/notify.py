"""
FCU Bid Scanner — notification module.

Channels:
  - Scan summary:      send_scan_summary(bids, duration_secs)   ← fires every run
  - New bid digest:    send_new_bids_digest(bids)
  - Cookie expired:    send_notification(reason)
  - Job walk:          jobwalk.py
  - Daily digest:      digest.py

Recipient routing (env vars):
  REPORTS_EMAIL  — opt-in: scanner summary, digest, cookie alerts, supervisor
                   (unset = these are not emailed)
  BEN_EMAIL      — job walks + new-bid alerts
  JOANNE_EMAIL   — job walks + new-bid alerts + RFQ drafts
  TEAM_EMAIL     — job walks + new-bid alerts
  ROBERT_EMAIL   — job walks + new-bid alerts

ADMIN_EMAIL is not read here — it belongs to the dashboard's scanner-down
watchdog (app/api/cron/scanner-watchdog), the only email Leo receives.

Cookie alerts also fire macOS desktop notification + terminal printout.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

COOKIES_FILE = Path(__file__).parent / "cookies.json"

# Public dashboard base URL — overridable via .env for staging/preview deploys.
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://bids.floorcoveringunlimited.com").rstrip("/")

# Sources the pipeline never auto-downloads bid documents from — legacy
# PlanetBids (~37 portals, no per-bid detail URL), LAUSD Facilities (one
# combined report PDF), and VendorLine (docs are on-demand via `--vl-docs`,
# manual CAPTCHA). New bids from these always need a human to pull the spec
# from the portal, so the new-bid digest flags them.
_NO_AUTO_DOC_SOURCES = {"PlanetBids", "LAUSD Facilities", "VendorLine"}


def dashboard_bid_url(bid_id: str) -> str:
    """Link to a bid's detail page on the FCU dashboard. From there the user can
    reach the parsed spec, the Go/No-Go score, and the source portal itself."""
    from urllib.parse import quote
    return f"{DASHBOARD_URL}/bids/{quote(str(bid_id), safe='')}"


# ─────────────────────────────────────────────
# Resend email (no extra deps — stdlib urllib)
# ─────────────────────────────────────────────

def _send_resend(to: str | list[str], subject: str, html: str) -> bool:
    """Send email via Resend API. Returns True on success."""
    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        print("  (Email skipped — set RESEND_API_KEY in .env)")
        return False

    import requests as _req

    from_addr = os.getenv("FROM_EMAIL", "FCU Bid Agent <bids@bids.benlee.ventures>")
    recipients = [to] if isinstance(to, str) else to
    try:
        resp = _req.post(
            "https://api.resend.com/emails",
            json={
                "from": from_addr,
                "to": recipients,
                "subject": subject,
                "html": html,
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        if resp.status_code == 200:
            print(f"  ✓ Email sent to {recipients}")
            return True
        else:
            print(f"  ⚠ Resend {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"  ⚠ Resend error: {e}")
        return False


def _parse_emails(*env_vars: str) -> list[str]:
    """Collect unique non-empty addresses from one or more env vars (comma-separated)."""
    seen: set[str] = set()
    result: list[str] = []
    for var in env_vars:
        for addr in os.getenv(var, "").split(","):
            addr = addr.strip()
            if addr and addr not in seen:
                seen.add(addr)
                result.append(addr)
    return result


def _report_recipients() -> list[str]:
    """Opt-in — scanner summary, digest, cookie alerts, supervisor failures."""
    return _parse_emails("REPORTS_EMAIL")


def _operational_recipients() -> list[str]:
    """Field/ops team — job walks + new-bid alerts. Ben, Joanne, Team, Robert."""
    return _parse_emails("BEN_EMAIL", "JOANNE_EMAIL", "TEAM_EMAIL", "ROBERT_EMAIL")


def _joanne_recipients() -> list[str]:
    """Joanne — RFQ drafts (she forwards to material reps)."""
    return _parse_emails("JOANNE_EMAIL")


def _recipients() -> list[str]:
    """Legacy alias — resolves to operational list."""
    return _operational_recipients()


# ─────────────────────────────────────────────
# Scan Summary (fires every run)
# ─────────────────────────────────────────────

def _persistent_source_issues(lookback: int = 6, min_streak: int = 2) -> list[str]:
    """
    Sources that have scraped 0 rows (or been blocked/errored) for `min_streak`
    or more consecutive recent runs — the early-warning the /scanner matrix shows.
    Returns human-readable strings like "Cal eProcure — 3 runs at 0".
    Best effort: silent [] if scan_run/scan_source_stat aren't there yet.
    """
    try:
        from db import get_client
        sb = get_client()
        if not sb:
            return []
        runs = (sb.table("scan_run")
                .select("id, started_at, mode")
                .neq("mode", "legacy")
                .order("started_at", desc=True)
                .limit(lookback).execute().data or [])
        if not runs:
            return []
        run_ids = [r["id"] for r in runs]
        stats = (sb.table("scan_source_stat")
                 .select("scan_run_id, source, raw_count, status")
                 .in_("scan_run_id", run_ids).execute().data or [])
    except Exception:
        return []

    by_run: dict[str, dict[str, dict]] = {}
    for s in stats:
        by_run.setdefault(s["scan_run_id"], {})[s["source"]] = s
    sources = {s["source"] for s in stats}

    issues = []
    for src in sorted(sources):
        streak = 0
        for rid in run_ids:                       # newest → oldest
            rec = by_run.get(rid, {}).get(src)
            if rec is None:
                continue                          # not scanned that run — skip
            bad = rec.get("raw_count", 0) == 0 or rec.get("status") in ("blocked", "error")
            if bad:
                streak += 1
            else:
                break
        if streak >= min_streak:
            issues.append(f"{src} — {streak} runs at 0")
    return issues


def send_scan_summary(bids: list[dict], duration_secs: float):
    """
    Email a per-source summary after every scanner run.
    Lets you spot broken scrapers (0 total) at a glance.
    """
    recipients = _report_recipients()
    if not recipients:
        return

    health_issues = _persistent_source_issues()
    health_banner = ""
    if health_issues:
        items = "".join(f"<li style='margin:2px 0;'>{i}</li>" for i in health_issues)
        health_banner = (
            "<div style=\"background:#3A2A0A;border-left:3px solid #FF9F0A;"
            "border-radius:6px;padding:12px 16px;margin-bottom:20px;\">"
            "<p style=\"margin:0 0 4px;font-size:11px;color:#FF9F0A;letter-spacing:.06em;"
            "text-transform:uppercase;\">Source health — needs attention</p>"
            f"<ul style=\"margin:4px 0 0;padding-left:18px;font-size:12px;color:#F5F5F0;\">{items}</ul>"
            "</div>"
        )

    # Per-source stats — _is_new is set by upsert_bids before this is called
    stats: dict[str, dict] = {}
    for b in bids:
        src = b.get("source") or "Unknown"
        if src not in stats:
            stats[src] = {"total": 0, "relevant": 0, "new": 0}
        stats[src]["total"] += 1
        if b.get("is_relevant"):
            stats[src]["relevant"] += 1
        if b.get("_is_new"):
            stats[src]["new"] += 1

    total   = len(bids)
    relevant = sum(1 for b in bids if b.get("is_relevant"))
    new      = sum(1 for b in bids if b.get("_is_new"))
    mins, secs = divmod(int(duration_secs), 60)
    duration_str = f"{mins}m {secs}s" if mins else f"{secs}s"

    # Sort: sources with new bids first, then by relevant desc
    sorted_sources = sorted(
        stats.items(),
        key=lambda x: (-x[1]["new"], -x[1]["relevant"], -x[1]["total"])
    )

    rows = ""
    for src, s in sorted_sources:
        has_new     = s["new"] > 0
        is_zero     = s["total"] == 0
        name_color  = "#F5F5F0" if not is_zero else "#8E8E93"
        new_color   = "#C8922A" if has_new else "#8E8E93"
        status_icon = "⚠" if is_zero else ("★" if has_new else "·")
        status_color= "#FF9F0A" if is_zero else ("#C8922A" if has_new else "#3A3A3C")
        rows += f"""
        <tr>
          <td style="padding:9px 14px;border-bottom:1px solid #2C2C2E;">
            <span style="font-size:13px;color:{name_color};">{src}</span>
          </td>
          <td style="padding:9px 14px;border-bottom:1px solid #2C2C2E;text-align:right;font-family:monospace;font-size:13px;color:#8E8E93;">{s['total']}</td>
          <td style="padding:9px 14px;border-bottom:1px solid #2C2C2E;text-align:right;font-family:monospace;font-size:13px;color:#8E8E93;">{s['relevant']}</td>
          <td style="padding:9px 14px;border-bottom:1px solid #2C2C2E;text-align:right;font-family:monospace;font-size:13px;font-weight:{'700' if has_new else '400'};color:{new_color};">{s['new']}</td>
          <td style="padding:9px 14px;border-bottom:1px solid #2C2C2E;text-align:center;font-size:14px;color:{status_color};">{status_icon}</td>
        </tr>"""

    subject = f"[FCU Scanner] {new} new · {relevant} relevant · {total} total — {datetime.now().strftime('%b %d')}"

    html = f"""
<!DOCTYPE html>
<html>
<body style="background:#1C1C1E;color:#F5F5F0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;padding:0;">
  <div style="max-width:640px;margin:0 auto;padding:32px 24px;">

    <div style="border-left:3px solid #C8922A;padding-left:16px;margin-bottom:24px;">
      <p style="margin:0;font-size:11px;color:#8E8E93;letter-spacing:.08em;text-transform:uppercase;">FCU Bid Agent · Scan Complete</p>
      <h1 style="margin:6px 0 0;font-size:22px;font-weight:700;">{datetime.now().strftime('%B %d, %Y')} — {duration_str}</h1>
    </div>

    {health_banner}

    <!-- Quick stats -->
    <div style="display:flex;gap:12px;margin-bottom:24px;">
      <div style="flex:1;background:#2C2C2E;border-radius:8px;padding:14px 16px;text-align:center;">
        <div style="font-size:26px;font-weight:700;color:#F5F5F0;">{total}</div>
        <div style="font-size:11px;color:#8E8E93;text-transform:uppercase;letter-spacing:.06em;margin-top:3px;">Total Bids</div>
      </div>
      <div style="flex:1;background:#2C2C2E;border-radius:8px;padding:14px 16px;text-align:center;">
        <div style="font-size:26px;font-weight:700;color:#F5F5F0;">{relevant}</div>
        <div style="font-size:11px;color:#8E8E93;text-transform:uppercase;letter-spacing:.06em;margin-top:3px;">Relevant</div>
      </div>
      <div style="flex:1;background:#{'C8922A' if new > 0 else '2C2C2E'};border-radius:8px;padding:14px 16px;text-align:center;">
        <div style="font-size:26px;font-weight:700;color:#{'1C1C1E' if new > 0 else 'F5F5F0'};">{new}</div>
        <div style="font-size:11px;color:#{'1C1C1E' if new > 0 else '8E8E93'};text-transform:uppercase;letter-spacing:.06em;margin-top:3px;">New</div>
      </div>
    </div>

    <!-- Per-source table -->
    <table style="width:100%;border-collapse:collapse;background:#2C2C2E;border-radius:8px;overflow:hidden;">
      <thead>
        <tr style="background:#3A3A3C;">
          <th style="padding:9px 14px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;">Source</th>
          <th style="padding:9px 14px;text-align:right;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;">Total</th>
          <th style="padding:9px 14px;text-align:right;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;">Relevant</th>
          <th style="padding:9px 14px;text-align:right;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;">New</th>
          <th style="padding:9px 14px;text-align:center;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;">Status</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>

    <p style="margin-top:20px;font-size:11px;color:#555;line-height:1.6;">
      ★ new bids found &nbsp;·&nbsp; ⚠ scraper returned 0 — may need attention<br>
      <a href="{DASHBOARD_URL}" style="color:#C8922A;">Open Dashboard ↗</a>
      &nbsp;·&nbsp;
      <a href="{DASHBOARD_URL}/scanner" style="color:#C8922A;">Scanner Health ↗</a>
    </p>
  </div>
</body>
</html>"""

    _send_resend(recipients, subject, html)
    print(f"  ✓ Scan summary sent ({len(sorted_sources)} sources)")


# ─────────────────────────────────────────────
# New Bid Digest
# ─────────────────────────────────────────────

def send_new_bids_digest(new_bids: list[dict], scanned: int = 0):
    """
    The team's daily bid email, sent after each scan (Phase 2 layout).

    Lists every OPEN relevant bid in the area — not just today's — split by
    region (North -> Melvin, South -> Robert), prime flooring first, with
    today's arrivals badged NEW, job-walk dates and a flag on walks < 5 days
    out. Bids whose county isn't confirmed sit in a separate section.
    new_bids: this scan's new relevant bids (marks NEW).
    scanned: total bids the scan looked at — shown on the zero-bid email.
    """
    recipients = _operational_recipients()
    if not recipients:
        print("  (New-bid digest skipped — set BEN_EMAIL/JOANNE_EMAIL/TEAM_EMAIL/ROBERT_EMAIL in .env)")
        return
    feed = fetch_open_feed()
    if not feed:
        _send_zero_bids_digest(recipients, scanned)
        return
    new_ids = {b.get("bid_id") for b in new_bids if b.get("bid_id")}
    subject, html = build_feed_digest(feed, new_ids, scanned)
    _send_resend(recipients, subject, html)


# Region sections, in email order. Owner names are display only.
FEED_SECTIONS = [
    ("North", "North — Melvin", "Los Angeles · Ventura · Kern"),
    ("South", "South — Robert", "Orange · Riverside · San Bernardino · San Diego"),
    (None, "Needs county check", "Location not confirmed yet — not counted above. Open the bid and set the county."),
]
_TIER_RANK = {"prime": 0, "package": 1, "mixed": 2}
_CLOSED_STATUSES = ("expired", "no_bid", "submitted")


# A bid with no due date stays "open" forever unless something retires it.
# Drop it from the email once no source has listed it for this many days.
NO_DUE_STALE_DAYS = 3

_FEED_COLUMNS = ("bid_id,title,agency,source,county,region,geo_status,due_date,due_date_raw,"
                 "url,scope_tier,walk_date,walk_mandatory,description,location_raw,bid_status,"
                 "first_seen_at,last_seen_at")


def fetch_open_feed() -> list[dict]:
    """Open relevant bids that aren't out of area — see prepare_feed."""
    from datetime import date as _date
    from db import get_client, missing_bid_columns
    sb = get_client()
    if not sb:
        return []
    missing = missing_bid_columns()
    cols = ",".join(c for c in _FEED_COLUMNS.split(",") if c not in missing)
    today = _date.today().isoformat()
    rows = (sb.table("bids").select(cols)
            .eq("is_relevant", True)
            .or_(f"due_date.gte.{today},due_date.is.null")
            .execute().data or [])
    specs = {}
    ids = [r["bid_id"] for r in rows]
    for i in range(0, len(ids), 200):
        for sp in (sb.table("bid_specs").select("bid_id,walk_required,walk_date")
                   .in_("bid_id", ids[i:i + 200]).execute().data or []):
            specs[sp["bid_id"]] = sp
    return prepare_feed(rows, specs)


def _title_key(title: str | None) -> str:
    import re
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())[:60]


def prepare_feed(rows: list[dict], specs: dict, now=None) -> list[dict]:
    """
    Turn raw open-bid rows into email rows:
      - drop out-of-area and closed (expired / no_bid / submitted) bids
      - drop no-due-date bids not listed by any source for NO_DUE_STALE_DAYS
      - merge job-walk info from the parsed spec when the listing had none;
        `walk_checked` says whether anything (listing detail page or parsed
        docs) actually looked for a walk
      - collapse the same bid seen on two sources (BidNet + VendorLine …),
        keeping the row with the most information
    """
    from datetime import datetime as _dt, timedelta, timezone as _tz
    now = now or _dt.now(_tz.utc)
    stale_before = (now - timedelta(days=NO_DUE_STALE_DAYS)).isoformat()

    kept = []
    for r in rows:
        if r.get("geo_status") == "out" or r.get("bid_status") in _CLOSED_STATUSES:
            continue
        if not r.get("due_date") and (r.get("last_seen_at") or "") < stale_before:
            continue
        sp = specs.get(r["bid_id"])
        if sp and not r.get("walk_date") and sp.get("walk_date"):
            r["walk_date"] = sp["walk_date"]
        if sp and r.get("walk_mandatory") is None and sp.get("walk_required") is not None:
            r["walk_mandatory"] = sp["walk_required"]
        r["walk_checked"] = (bool(sp) or r.get("description") is not None
                             or r.get("location_raw") is not None   # listing detail page read
                             or r.get("walk_date") is not None or r.get("walk_mandatory") is not None)
        kept.append(r)

    def richness(r):
        return (r.get("geo_status") == "in", r.get("walk_checked", False),
                bool(r.get("due_date")), bool(r.get("url")))

    best: dict[str, dict] = {}
    for r in kept:
        k = _title_key(r.get("title")) or r["bid_id"]
        if k not in best or richness(r) > richness(best[k]):
            best[k] = r
    return list(best.values())


def _days_until(d: str | None, today) -> int | None:
    from datetime import date as _date
    if not d:
        return None
    try:
        return (_date.fromisoformat(str(d)[:10]) - today).days
    except ValueError:
        return None


def _fmt_day(d: str | None) -> str:
    from datetime import date as _date
    try:
        return _date.fromisoformat(str(d)[:10]).strftime("%a %b %-d")
    except (TypeError, ValueError):
        return "—"


def _badge(text: str, color: str) -> str:
    return (f'<span style="display:inline-block;margin:0 6px 4px 0;padding:2px 7px;border-radius:4px;'
            f'font-size:10px;font-weight:700;letter-spacing:.05em;color:#1C1C1E;background:{color};">{text}</span>')


def _feed_row(b: dict, is_new: bool, today) -> str:
    from html import escape
    badges = ""
    if is_new:
        badges += _badge("NEW", "#C8922A")
    tier = b.get("scope_tier")
    if tier == "package":
        badges += _badge("FLOORING PACKAGE", "#8E8E93")
    elif tier == "mixed":
        badges += _badge("MIXED SCOPE", "#8E8E93")
    if b.get("source") == "SAM.gov":
        badges += _badge("FEDERAL", "#8E8E93")
    if b.get("source") in _NO_AUTO_DOC_SOURCES:
        badges += _badge("DOCS: PULL FROM PORTAL", "#FF9F0A")

    meta = " · ".join(escape(x) for x in (b.get("agency") or "", b.get("county") and f"{b['county']} County",
                                          b.get("source") or "") if x)

    due_days = _days_until(b.get("due_date"), today)
    if due_days is None:
        due = f'Due {escape(b.get("due_date_raw") or "—")}'
    else:
        left = "today" if due_days == 0 else f"{due_days} day{'s' if due_days != 1 else ''} left"
        color = "#FF453A" if due_days <= 3 else "#F5F5F0"
        due = f'Due <b style="color:{color};">{_fmt_day(b["due_date"])}</b> <span style="color:#8E8E93;">({left})</span>'

    walk_days = _days_until(b.get("walk_date"), today)
    mand = b.get("walk_mandatory")
    if b.get("walk_date") and walk_days is not None and walk_days >= 0:
        label = "MANDATORY walk" if mand else ("Optional walk" if mand is False else "Job walk")
        if walk_days < 5:
            when = "today" if walk_days == 0 else f"in {walk_days} day{'s' if walk_days != 1 else ''}"
            walk = (f'<b style="color:#FF453A;">⚠ {label} {_fmt_day(b["walk_date"])} — {when}</b>')
        else:
            walk = f'{label} <b>{_fmt_day(b["walk_date"])}</b>'
    elif b.get("walk_date") and walk_days is not None:
        walk = f'<span style="color:#8E8E93;">{"Mandatory walk" if mand else "Walk"} was {_fmt_day(b["walk_date"])}</span>'
    elif mand:
        walk = '<span style="color:#FF9F0A;">Mandatory walk — date not read, check the docs</span>'
    elif b.get("walk_checked"):
        walk = '<span style="color:#8E8E93;">No job walk listed</span>'
    else:
        walk = '<span style="color:#8E8E93;">Job walk: not checked yet — bid documents not read</span>'

    link = dashboard_bid_url(b["bid_id"]) if b.get("bid_id") else (b.get("url") or DASHBOARD_URL)
    return f"""
      <tr><td style="padding:14px 16px;border-bottom:1px solid #3A3A3C;">
        <div>{badges}</div>
        <a href="{link}" style="color:#F5F5F0;font-size:15px;font-weight:600;text-decoration:none;line-height:1.35;">{escape(b.get("title") or "")}</a>
        <div style="margin-top:4px;font-size:12px;color:#8E8E93;">{meta}</div>
        <div style="margin-top:8px;font-size:13px;color:#F5F5F0;line-height:1.6;">{due}<br>{walk}</div>
      </td></tr>"""


def build_feed_digest(feed: list[dict], new_ids: set, scanned: int = 0,
                      today=None) -> tuple[str, str]:
    """Render (subject, html) for the daily email from fetch_open_feed() rows."""
    from datetime import date as _date
    today = today or _date.today()

    def key(b):
        return (_TIER_RANK.get(b.get("scope_tier"), 3), b.get("due_date") or "9999-12-31")

    groups = {region: sorted([b for b in feed if (b.get("region") if b.get("geo_status") == "in" else None) == region],
                             key=key)
              for region, _, _ in FEED_SECTIONS}
    n_north, n_south, n_check = len(groups["North"]), len(groups["South"]), len(groups[None])
    n_new = sum(1 for b in feed if b.get("bid_id") in new_ids)
    walks_soon = sum(1 for b in feed
                     if (d := _days_until(b.get("walk_date"), today)) is not None and 0 <= d < 5)

    subject = (f"[FCU Bids] {n_new} new · {n_north + n_south} open — "
               f"North {n_north} / South {n_south}")

    sections = ""
    for region, heading, sub in FEED_SECTIONS:
        rows = groups[region]
        if region is None and not rows:
            continue
        body = ("".join(_feed_row(b, b.get("bid_id") in new_ids, today) for b in rows)
                or '<tr><td style="padding:14px 16px;font-size:13px;color:#8E8E93;">No open bids right now.</td></tr>')
        accent = "#8E8E93" if region is None else "#C8922A"
        sections += f"""
    <h2 style="margin:28px 0 2px;font-size:16px;font-weight:700;border-left:3px solid {accent};padding-left:10px;">
      {heading} <span style="color:#8E8E93;font-weight:400;">({len(rows)})</span></h2>
    <p style="margin:0 0 10px 13px;font-size:11px;color:#8E8E93;">{sub}</p>
    <table style="width:100%;border-collapse:collapse;background:#2C2C2E;border-radius:8px;overflow:hidden;">{body}</table>"""

    stats = f"{n_new} new today · {n_north + n_south} open in the area"
    if walks_soon:
        stats += f' · <span style="color:#FF453A;">{walks_soon} job walk{"s" if walks_soon != 1 else ""} in the next 5 days</span>'
    scanned_line = f"Scanned {scanned:,} bids across all portals. " if scanned else ""

    html = f"""<!DOCTYPE html>
<html>
<body style="background:#1C1C1E;color:#F5F5F0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;padding:0;">
  <div style="max-width:680px;margin:0 auto;padding:28px 16px;">
    <div style="border-left:3px solid #C8922A;padding-left:16px;">
      <p style="margin:0;font-size:11px;color:#8E8E93;letter-spacing:.08em;text-transform:uppercase;">FCU Bid Agent · {today.strftime('%A, %B %-d, %Y')}</p>
      <h1 style="margin:6px 0 0;font-size:22px;font-weight:700;">North {n_north} · South {n_south}</h1>
      <p style="margin:6px 0 0;font-size:13px;color:#8E8E93;">{stats}</p>
    </div>
    {sections}
    <p style="margin-top:24px;font-size:12px;color:#8E8E93;line-height:1.7;">
      {scanned_line}Prime flooring jobs first, then flooring packages of larger projects, then mixed-scope jobs.
      Federal work appears on Mondays only. Every bid still needs a yes / no / maybe in the tracker.
      <br>All bids: <a href="{DASHBOARD_URL}" style="color:#C8922A;">FCU Dashboard</a>.
    </p>
  </div>
</body>
</html>"""
    return subject, html


def _send_zero_bids_digest(recipients: list[str], scanned: int):
    """Daily 'scanner ran, nothing new' email — confirms the scan actually happened."""
    subject = "[FCU Bid Agent] 0 new relevant bids today"
    scanned_line = f"Scanned {scanned:,} bids across all portals — " if scanned else ""
    html = f"""
<!DOCTYPE html>
<html>
<body style="background:#1C1C1E;color:#F5F5F0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;padding:0;">
  <div style="max-width:720px;margin:0 auto;padding:32px 24px;">
    <div style="border-left:3px solid #C8922A;padding-left:16px;margin-bottom:28px;">
      <p style="margin:0;font-size:11px;color:#8E8E93;letter-spacing:.08em;text-transform:uppercase;">FCU Bid Agent</p>
      <h1 style="margin:6px 0 0;font-size:22px;font-weight:700;">0 New Relevant Bids Today</h1>
      <p style="margin:6px 0 0;font-size:13px;color:#8E8E93;">{datetime.now().strftime('%B %d, %Y')}</p>
    </div>

    <p style="font-size:14px;color:#F5F5F0;line-height:1.7;">
      {scanned_line}none were new and relevant to FCU. The scanner ran normally; nothing needs action today.
    </p>

    <p style="margin-top:24px;font-size:12px;color:#8E8E93;line-height:1.7;">
      Open bids are still tracked in the <a href="{DASHBOARD_URL}" style="color:#C8922A;">FCU Dashboard</a>.
    </p>
  </div>
</body>
</html>"""

    _send_resend(recipients, subject, html)


# ─────────────────────────────────────────────
# RFQ Email (material quote requests)
# ─────────────────────────────────────────────

def send_rfq_emails(bid: dict, spec: dict, estimate: dict):
    """
    Email Joanne a formatted RFQ draft she can forward to her material reps.
    Called from parser.py --rfq <bid_id> or from the dashboard Send RFQ button.
    estimate: dict with line_items (list of LineItem dicts).
    """
    recipients = _joanne_recipients()
    if not recipients:
        print("  (RFQ skipped — set JOANNE_EMAIL in .env)")
        return

    title     = bid.get("title", "Unknown Job")
    agency    = bid.get("agency", "")
    bid_due   = bid.get("due_date_raw") or bid.get("due_date") or "—"
    portal    = bid.get("url", "")
    sqft      = spec.get("total_sqft")
    sqft_str  = f"{sqft:,} SF total" if sqft else "SF TBD"
    pw_note   = "Prevailing wage project." if spec.get("prevailing_wage") else ""

    material_lines = [l for l in (estimate.get("line_items") or []) if l.get("type") == "material"]
    if not material_lines:
        print("  (RFQ skipped — no material lines in estimate)")
        return

    mat_rows = "".join(f"""
    <tr style="background:{'#2C2C2E' if i % 2 == 0 else '#3A3A3C'};">
      <td style="padding:12px 16px;font-size:14px;font-weight:600;color:#F5F5F0;">{l.get('description','')}</td>
      <td style="padding:12px 16px;font-size:14px;font-family:monospace;color:#F5F5F0;text-align:right;">{l.get('qty', 0):,}</td>
      <td style="padding:12px 16px;font-size:14px;font-family:monospace;color:#8E8E93;">{l.get('unit','SF')}</td>
      <td style="padding:12px 16px;font-size:13px;color:#FF9F0A;font-weight:600;">Quote needed</td>
    </tr>""" for i, l in enumerate(material_lines))

    portal_link = f'<a href="{portal}" style="color:#C8922A;">{portal[:80]}</a>' if portal else "—"
    mat_count = len(material_lines)
    subject = f"[RFQ Draft] {title[:55]} — {mat_count} material line{'s' if mat_count > 1 else ''}"

    html = f"""
<!DOCTYPE html>
<html>
<body style="background:#1C1C1E;color:#F5F5F0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;padding:0;">
  <div style="max-width:700px;margin:0 auto;padding:32px 24px;">

    <div style="border-left:3px solid #C8922A;padding-left:16px;margin-bottom:24px;">
      <p style="margin:0;font-size:11px;color:#8E8E93;letter-spacing:.08em;text-transform:uppercase;">FCU Bid Agent · RFQ Draft</p>
      <h1 style="margin:6px 0 0;font-size:22px;font-weight:700;">{title}</h1>
      <p style="margin:6px 0 0;font-size:13px;color:#8E8E93;">{agency}</p>
    </div>

    <div style="background:#2C2C2E;border-radius:8px;padding:16px 20px;margin-bottom:28px;font-size:13px;color:#8E8E93;">
      <strong style="color:#F5F5F0;">How to use this draft:</strong> Forward (or copy-paste) the quote request block below
      to your material reps. Fill in the rep's name/company at the top. Return completed quotes to Joanne
      before <strong style="color:#FF9F0A;">{bid_due}</strong>.
    </div>

    <!-- Divider: the actual forwarding email starts here -->
    <div style="border:1px dashed #3A3A3C;border-radius:8px;padding:24px;margin-bottom:24px;">
      <p style="margin:0 0 16px;font-size:12px;color:#8E8E93;letter-spacing:.05em;text-transform:uppercase;">
        ── Forward this to your rep ──
      </p>

      <p style="margin:0 0 12px;font-size:14px;color:#F5F5F0;">Hi [Rep Name],</p>
      <p style="margin:0 0 16px;font-size:14px;color:#F5F5F0;line-height:1.6;">
        We are bidding on a flooring project and need material pricing. Please provide your best pricing
        by <strong>{bid_due}</strong>.
      </p>

      <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
        <tr>
          <td style="padding:6px 0;color:#8E8E93;font-size:13px;width:120px;">Project</td>
          <td style="padding:6px 0;font-size:13px;color:#F5F5F0;">{title}</td>
        </tr>
        <tr>
          <td style="padding:6px 0;color:#8E8E93;font-size:13px;">Agency</td>
          <td style="padding:6px 0;font-size:13px;color:#F5F5F0;">{agency}</td>
        </tr>
        <tr>
          <td style="padding:6px 0;color:#8E8E93;font-size:13px;">Scope</td>
          <td style="padding:6px 0;font-size:13px;color:#F5F5F0;">{sqft_str}. {pw_note}</td>
        </tr>
        <tr>
          <td style="padding:6px 0;color:#8E8E93;font-size:13px;">Bid Due</td>
          <td style="padding:6px 0;font-size:13px;font-weight:700;color:#FF9F0A;">{bid_due}</td>
        </tr>
      </table>

      <h3 style="font-size:12px;font-weight:700;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;margin-bottom:10px;">
        Materials Needed
      </h3>
      <table style="width:100%;border-collapse:collapse;border-radius:8px;overflow:hidden;">
        <thead>
          <tr style="background:#3A3A3C;">
            <th style="padding:10px 16px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.05em;text-transform:uppercase;">Description</th>
            <th style="padding:10px 16px;text-align:right;font-size:10px;color:#8E8E93;letter-spacing:.05em;text-transform:uppercase;">Qty</th>
            <th style="padding:10px 16px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.05em;text-transform:uppercase;">Unit</th>
            <th style="padding:10px 16px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.05em;text-transform:uppercase;">Your Price</th>
          </tr>
        </thead>
        <tbody>{mat_rows}</tbody>
      </table>

      <p style="margin:20px 0 0;font-size:14px;color:#F5F5F0;line-height:1.6;">
        Please include product specs, color options, and lead time with your quote.
        Questions? Call or email Joanne.<br><br>
        Thank you,<br>
        <strong>Joanne Lee</strong><br>
        Floor Covering Unlimited<br>
        Chatsworth, CA
      </p>
    </div>

    <p style="font-size:12px;color:#8E8E93;">
      Portal: {portal_link}<br>
      Generated by <a href="{DASHBOARD_URL}" style="color:#C8922A;">FCU Bid Agent</a>
    </p>
  </div>
</body>
</html>"""

    _send_resend(recipients, subject, html)
    print(f"  ✓ RFQ draft sent for: {title[:55]}")


# ─────────────────────────────────────────────
# Cookie expiry (existing — kept for scanner)
# ─────────────────────────────────────────────

def check_planetbids_cookies() -> tuple[bool, str]:
    """Check if PlanetBids cookies exist and haven't expired."""
    if not COOKIES_FILE.exists():
        return False, "cookies.json not found"

    try:
        cookies = json.loads(COOKIES_FILE.read_text())
    except Exception:
        return False, "cookies.json is corrupt"

    if not cookies:
        return False, "cookies.json is empty"

    now_ts = datetime.now(timezone.utc).timestamp()

    waf_cookies = [c for c in cookies if "waf" in c.get("name", "").lower()]
    if waf_cookies:
        for c in waf_cookies:
            expires = c.get("expires", -1)
            if expires != -1 and expires < now_ts:
                return False, f"aws-waf-token expired at {datetime.fromtimestamp(expires).strftime('%Y-%m-%d %H:%M')}"
        return True, "ok"

    session_cookies = [c for c in cookies if c.get("expires", -1) != -1]
    if session_cookies:
        soonest = min(session_cookies, key=lambda c: c["expires"])
        if soonest["expires"] < now_ts:
            return False, f"Session cookies expired at {datetime.fromtimestamp(soonest['expires']).strftime('%Y-%m-%d %H:%M')}"
        if soonest["expires"] - now_ts < 7200:
            mins = int((soonest["expires"] - now_ts) / 60)
            return True, f"warning: cookies expire in {mins} minutes"

    return True, "ok (no expiry data)"


def send_notification(reason: str):
    """Fire all available channels when cookies need refreshing."""
    _notify_terminal(reason)
    _notify_mac(reason)

    recipients = _report_recipients()
    if recipients:
        html = f"""
<div style="font-family:monospace;padding:20px;background:#1C1C1E;color:#F5F5F0;border-radius:8px;">
  <h2 style="color:#FF9F0A;">FCU Bid Scanner — Action Required</h2>
  <p>PlanetBids cookies need refresh.</p>
  <p><strong>Reason:</strong> {reason}</p>
  <hr style="border-color:#3A3A3C;"/>
  <p><strong>To fix:</strong></p>
  <ol>
    <li>Run: <code>python bid-scanner/test_planetbids.py --save-cookies</code></li>
    <li>Chrome opens → solve CAPTCHA → log in → press Enter</li>
    <li>Re-run the scanner</li>
  </ol>
</div>"""
        _send_resend(recipients, "FCU Bid Scanner — PlanetBids login refresh needed", html)

    # Telegram fallback
    tg_token = os.getenv("NOTIFY_TELEGRAM_TOKEN", "")
    tg_chat_id = os.getenv("NOTIFY_TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat_id:
        _notify_telegram(reason, tg_token, tg_chat_id)


def _notify_terminal(reason: str):
    script_dir = Path(__file__).parent
    print()
    print("=" * 60)
    print("  FCU BID SCANNER — ACTION REQUIRED")
    print("=" * 60)
    print(f"  PlanetBids cookies need refresh.")
    print(f"  Reason: {reason}")
    print()
    print("  To fix:")
    print(f"    1. Run:  python {script_dir}/test_planetbids.py --save-cookies")
    print(f"    2. Chrome opens → solve CAPTCHA → log in → press Enter")
    print(f"    3. Re-run the scanner")
    print("=" * 60)
    print()


def _notify_mac(reason: str):
    try:
        script = (
            'display notification "PlanetBids cookies expired — run --save-cookies to refresh." '
            'with title "FCU Bid Scanner" '
            'subtitle "Action required" '
            'sound name "Ping"'
        )
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    except Exception:
        pass


def _notify_telegram(reason: str, token: str, chat_id: str):
    import urllib.request
    import urllib.parse

    text = (
        f"*FCU Bid Scanner — Action Required*\n\n"
        f"PlanetBids cookies expired.\n"
        f"Reason: `{reason}`\n\n"
        f"*To fix:*\n"
        f"1\\. Run: `python bid\\-scanner/test_planetbids.py \\-\\-save\\-cookies`\n"
        f"2\\. Chrome opens → solve CAPTCHA → log in → press Enter\n"
        f"3\\. Re\\-run the scanner"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
    }).encode()

    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                print(f"  ✓ Telegram message sent (chat_id: {chat_id})")
            else:
                print(f"  ⚠ Telegram returned {resp.status}")
    except Exception as e:
        print(f"  ⚠ Telegram error: {e}")


if __name__ == "__main__":
    valid, reason = check_planetbids_cookies()
    if valid:
        print(f"✓ Cookies OK — {reason}")
    else:
        print(f"✗ Cookies invalid — {reason}")
        send_notification(reason)
