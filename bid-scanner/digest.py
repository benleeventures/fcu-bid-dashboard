"""
FCU Daily Digest — morning briefing after parsing
Runs daily at 7:00am via launchd (com.fcu.digest).

Sends a richer email than the scan-time new-bid alert: includes parsed
bid_specs (sqft, compliance flags, walk status) for any bids parsed in
the last 24h, plus a count of still-unprocessed bids awaiting parsing.
"""

import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

LOG_FILE = Path(__file__).parent / "logs" / "digest.log"
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)


def run():
    from supabase import create_client
    from notify import _send_resend, _admin_recipients

    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        log.error("SUPABASE_URL/SUPABASE_KEY not set")
        sys.exit(1)
    sb = create_client(url, key)

    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    # Specs parsed in last 24h
    specs_resp = (
        sb.table("bid_specs")
        .select("bid_id,flooring_types,total_sqft,prevailing_wage,bid_bond,walk_required,walk_date_raw,summary,parsed_at")
        .gte("parsed_at", since)
        .order("parsed_at", desc=True)
        .execute()
    )
    fresh_specs = specs_resp.data or []

    # All relevant unprocessed bids (no spec yet)
    all_relevant_resp = sb.table("bids").select("bid_id").eq("is_relevant", True).execute()
    all_relevant_ids = [b["bid_id"] for b in (all_relevant_resp.data or [])]
    unprocessed_count = 0
    if all_relevant_ids:
        for i in range(0, len(all_relevant_ids), 200):
            chunk = all_relevant_ids[i:i+200]
            parsed_resp = sb.table("bid_specs").select("bid_id").in_("bid_id", chunk).execute()
            parsed_ids = {r["bid_id"] for r in (parsed_resp.data or [])}
            unprocessed_count += sum(1 for bid_id in chunk if bid_id not in parsed_ids)

    recipients = _admin_recipients()
    if not recipients:
        log.warning("ADMIN_EMAIL not set — skipping digest")
        return

    if not fresh_specs and unprocessed_count == 0:
        log.info("Nothing to report — no fresh specs and no pending bids")
        print("✓ Nothing to report today")
        return

    # Fetch bid details for fresh specs
    if fresh_specs:
        spec_ids = [s["bid_id"] for s in fresh_specs]
        bids_resp = sb.table("bids").select("bid_id,title,agency,due_date,url,source").in_("bid_id", spec_ids).execute()
        bids_by_id = {b["bid_id"]: b for b in (bids_resp.data or [])}
    else:
        bids_by_id = {}

    # Build spec cards
    cards = ""
    for s in fresh_specs:
        bid = bids_by_id.get(s["bid_id"], {})
        title   = bid.get("title", s["bid_id"])[:70]
        agency  = bid.get("agency", "")
        due     = bid.get("due_date") or "—"
        portal  = bid.get("url", "")
        link    = f'<a href="{portal}" style="color:#C8922A;">View ↗</a>' if portal else ""
        sqft    = f"{s['total_sqft']:,.0f} SF" if s.get("total_sqft") else "SF unknown"
        types   = ", ".join(s.get("flooring_types") or []) or "—"
        summary = s.get("summary") or ""

        flags = []
        if s.get("prevailing_wage"):
            flags.append('<span style="background:#FF9F0A22;color:#FF9F0A;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;">PREV WAGE</span>')
        if s.get("bid_bond"):
            flags.append('<span style="background:#FF453A22;color:#FF453A;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;">BID BOND</span>')
        if s.get("walk_required"):
            walk_label = s.get("walk_date_raw") or "date TBD"
            flags.append(f'<span style="background:#30D15822;color:#30D158;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;">WALK {walk_label}</span>')

        flags_html = " ".join(flags) if flags else '<span style="color:#555;font-size:12px;">No flags</span>'

        cards += f"""
        <div style="background:#2C2C2E;border-radius:8px;padding:16px 18px;margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
            <div>
              <div style="font-size:14px;font-weight:700;color:#F5F5F0;">{title}</div>
              <div style="font-size:12px;color:#8E8E93;margin-top:2px;">{agency} &nbsp;·&nbsp; Due {due} &nbsp;·&nbsp; {link}</div>
            </div>
          </div>
          <div style="font-size:12px;color:#8E8E93;margin-bottom:8px;">
            <strong style="color:#F5F5F0;">{sqft}</strong> &nbsp;·&nbsp; {types}
          </div>
          {f'<p style="font-size:13px;color:#8E8E93;margin:8px 0;">{summary}</p>' if summary else ''}
          <div style="margin-top:8px;">{flags_html}</div>
        </div>"""

    pending_note = ""
    if unprocessed_count > 0:
        pending_note = f"""
        <div style="background:#3A3A3C;border-radius:8px;padding:14px 16px;margin-top:4px;">
          <p style="margin:0;font-size:13px;color:#8E8E93;">
            <strong style="color:#F5F5F0;">{unprocessed_count} relevant bid{'s' if unprocessed_count > 1 else ''}</strong>
            still awaiting parsing. Run:
            <code style="background:#2C2C2E;padding:2px 6px;border-radius:3px;">python parser.py --parse-all --ollama</code>
          </p>
        </div>"""

    count = len(fresh_specs)
    subject = (
        f"[FCU Digest] {count} bid{'s' if count != 1 else ''} parsed"
        + (f" · {unprocessed_count} pending" if unprocessed_count else "")
        + f" — {datetime.now().strftime('%b %d')}"
    )

    html = f"""<!DOCTYPE html>
<html>
<body style="background:#1C1C1E;color:#F5F5F0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;padding:0;">
  <div style="max-width:680px;margin:0 auto;padding:32px 24px;">
    <div style="border-left:3px solid #C8922A;padding-left:16px;margin-bottom:24px;">
      <p style="margin:0;font-size:11px;color:#8E8E93;letter-spacing:.08em;text-transform:uppercase;">FCU Bid Agent · Morning Digest</p>
      <h1 style="margin:6px 0 0;font-size:22px;font-weight:700;">{datetime.now().strftime('%B %d, %Y')}</h1>
    </div>

    {f'<h2 style="font-size:13px;font-weight:700;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;margin-bottom:12px;">{count} Parsed in Last 24h</h2>{cards}' if fresh_specs else '<p style="color:#8E8E93;font-size:14px;">No bids parsed in the last 24 hours.</p>'}

    {pending_note}

    <p style="margin-top:20px;font-size:12px;color:#555;">
      <a href="https://fcu-dashboard.vercel.app" style="color:#C8922A;">Open Dashboard ↗</a>
    </p>
  </div>
</body>
</html>"""

    _send_resend(recipients, subject, html)
    log.info(f"Digest sent — {count} fresh specs, {unprocessed_count} pending")
    print(f"✓ Digest sent ({count} parsed, {unprocessed_count} pending)")


if __name__ == "__main__":
    run()
