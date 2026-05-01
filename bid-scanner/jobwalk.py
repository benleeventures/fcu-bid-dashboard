"""
FCU Job Walk Notifier — one daily email with all qualifying upcoming walks.
Runs daily at 7:15am via launchd (com.fcu.jobwalk).

Rules:
  - Only bids with go_verdict='go' (stored in bid_specs)
  - Only is_relevant=True and bid_status NOT IN ('expired', 'no_bid')
  - Shows walks in next WALK_WINDOW_DAYS days
  - Walks happening tomorrow are highlighted as urgent
  - If nothing qualifies, no email sent
"""

import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

LOG_FILE = Path(__file__).parent / "logs" / "jobwalk.log"
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)

WALK_WINDOW_DAYS = 7


def run():
    from supabase import create_client
    from notify import _send_resend, _operational_recipients

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        log.error("SUPABASE_URL/SUPABASE_KEY not set")
        sys.exit(1)
    sb = create_client(url, key)

    today     = date.today()
    tomorrow  = today + timedelta(days=1)
    window_end = today + timedelta(days=WALK_WINDOW_DAYS)

    # Specs: GO verdict, walk in window
    specs_resp = (
        sb.table("bid_specs")
        .select("bid_id,walk_date,walk_date_raw,go_score,go_verdict,summary")
        .eq("walk_required", True)
        .eq("go_verdict", "go")
        .gte("walk_date", today.isoformat())
        .lte("walk_date", window_end.isoformat())
        .order("walk_date")
        .execute()
    )
    specs = specs_resp.data or []

    if not specs:
        log.info("No qualifying GO walks in next %d days", WALK_WINDOW_DAYS)
        print("✓ No qualifying job walks to report")
        return

    # Fetch bids — filter out expired / no_bid / irrelevant
    bid_ids = [s["bid_id"] for s in specs]
    bids_resp = (
        sb.table("bids")
        .select("bid_id,title,agency,due_date,url,bid_status,is_relevant")
        .in_("bid_id", bid_ids)
        .eq("is_relevant", True)
        .execute()
    )
    bids_by_id = {
        b["bid_id"]: b
        for b in (bids_resp.data or [])
        if b.get("bid_status") not in ("expired", "no_bid")
    }

    # Only specs whose bid passed the filter
    qualifying = [s for s in specs if s["bid_id"] in bids_by_id]
    if not qualifying:
        log.info("No qualifying walks after bid_status filter")
        print("✓ No qualifying job walks after status filter")
        return

    tomorrow_walks = [s for s in qualifying if s.get("walk_date") == tomorrow.isoformat()]
    upcoming_walks = [s for s in qualifying if s.get("walk_date") != tomorrow.isoformat()]

    log.info(f"Qualifying walks: {len(tomorrow_walks)} tomorrow, {len(upcoming_walks)} upcoming")

    recipients = _operational_recipients()
    if not recipients:
        log.warning("BEN_EMAIL/JOANNE_EMAIL/TEAM_EMAIL/ADMIN_EMAIL not set — skipping")
        return

    def _fmt_date(iso: str) -> str:
        """Convert '2026-05-08' → 'May 8'."""
        try:
            from datetime import date as _date
            d = _date.fromisoformat(str(iso))
            return d.strftime("%b %-d")
        except Exception:
            return str(iso)

    def _row(s: dict, urgent: bool) -> str:
        bid      = bids_by_id[s["bid_id"]]
        title    = bid.get("title", s["bid_id"])[:55]
        agency   = bid.get("agency", "")[:50]
        bid_due  = _fmt_date(bid["due_date"]) if bid.get("due_date") else "—"
        portal   = bid.get("url", "")
        link     = f'<a href="{portal}" style="color:#C8922A;text-decoration:none;">View ↗</a>' if portal else "—"
        walk_raw = s.get("walk_date_raw") or _fmt_date(s.get("walk_date", "")) or "TBD"
        score    = s.get("go_score", "—")

        walk_color = "#FF9F0A" if urgent else "#F5F5F0"
        row_bg     = "#FF9F0A0A" if urgent else "transparent"

        return f"""
        <tr style="background:{row_bg}">
          <td style="padding:12px 14px;border-bottom:1px solid #3A3A3C;vertical-align:top;width:38%;">
            <div style="font-size:13px;font-weight:600;color:#F5F5F0;line-height:1.3;">{title}</div>
            <div style="font-size:11px;color:#8E8E93;margin-top:3px;">{agency}</div>
          </td>
          <td style="padding:12px 14px;border-bottom:1px solid #3A3A3C;font-size:13px;font-weight:700;color:{walk_color};white-space:nowrap;vertical-align:top;width:28%;">{walk_raw}</td>
          <td style="padding:12px 14px;border-bottom:1px solid #3A3A3C;font-size:12px;color:#8E8E93;white-space:nowrap;vertical-align:top;width:14%;text-align:center;">{bid_due}</td>
          <td style="padding:12px 14px;border-bottom:1px solid #3A3A3C;font-size:12px;color:#30D158;font-weight:700;vertical-align:top;width:10%;text-align:center;white-space:nowrap;">GO&nbsp;{score}</td>
          <td style="padding:12px 14px;border-bottom:1px solid #3A3A3C;font-size:12px;vertical-align:top;width:10%;text-align:center;">{link}</td>
        </tr>"""

    def _section(title: str, walks: list, urgent: bool) -> str:
        if not walks:
            return ""
        header_color = "#FF9F0A" if urgent else "#8E8E93"
        rows = "".join(_row(s, urgent) for s in walks)
        return f"""
        <h2 style="font-size:11px;font-weight:700;color:{header_color};letter-spacing:.08em;text-transform:uppercase;margin:24px 0 10px;">{title}</h2>
        <table style="width:100%;border-collapse:collapse;background:#2C2C2E;border-radius:8px;overflow:hidden;table-layout:fixed;">
          <thead>
            <tr style="background:#3A3A3C;">
              <th style="padding:8px 14px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;width:38%;">Bid</th>
              <th style="padding:8px 14px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;width:28%;">Walk Date</th>
              <th style="padding:8px 14px;text-align:center;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;width:14%;">Bid Due</th>
              <th style="padding:8px 14px;text-align:center;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;width:10%;">Score</th>
              <th style="padding:8px 14px;text-align:center;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;width:10%;">Portal</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>"""

    total = len(qualifying)
    subject_parts = []
    if tomorrow_walks:
        subject_parts.append(f"⚠ {len(tomorrow_walks)} TOMORROW")
    if upcoming_walks:
        subject_parts.append(f"{len(upcoming_walks)} upcoming")
    subject = f"[Job Walk] {' · '.join(subject_parts)} — {today.strftime('%b %d')}"

    html = f"""<!DOCTYPE html>
<html>
<body style="background:#1C1C1E;color:#F5F5F0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;padding:0;">
  <div style="max-width:740px;margin:0 auto;padding:32px 24px;">

    <div style="border-left:3px solid #C8922A;padding-left:16px;margin-bottom:8px;">
      <p style="margin:0;font-size:11px;color:#8E8E93;letter-spacing:.08em;text-transform:uppercase;">FCU Bid Agent · Job Walk Briefing</p>
      <h1 style="margin:6px 0 0;font-size:22px;font-weight:700;">{total} GO-Scored Walk{'s' if total != 1 else ''}</h1>
      <p style="margin:6px 0 0;font-size:13px;color:#8E8E93;">{today.strftime('%B %d, %Y')} · Next {WALK_WINDOW_DAYS} days</p>
    </div>

    {_section('⚠ Tomorrow — Action Required', tomorrow_walks, urgent=True)}
    {_section(f'Upcoming — Next {WALK_WINDOW_DAYS} Days', upcoming_walks, urgent=False)}

    <div style="margin-top:24px;padding:14px 16px;background:#2C2C2E;border-radius:8px;border-left:3px solid #C8922A;">
      <p style="margin:0;font-size:13px;color:#8E8E93;">
        After each walk, call Joanne with <strong style="color:#F5F5F0;">BID or NO BID</strong> + any site notes that affect scope or quantities.
        &nbsp;·&nbsp;
        <a href="https://fcu-dashboard.vercel.app" style="color:#C8922A;">Dashboard ↗</a>
      </p>
    </div>
  </div>
</body>
</html>"""

    _send_resend(recipients, subject, html)
    log.info(f"Job walk email sent — {len(tomorrow_walks)} tomorrow, {len(upcoming_walks)} upcoming")
    print(f"✓ Job walk email sent ({len(tomorrow_walks)} tomorrow, {len(upcoming_walks)} upcoming)")


if __name__ == "__main__":
    run()
