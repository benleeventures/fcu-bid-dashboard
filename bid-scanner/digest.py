"""
FCU Daily Digest — runs at 7:00am via launchd.

Sends ONE daily email to Joanne + Ben summarizing all new relevant bids
found since yesterday's run. If nothing new, skips silently.

Usage:
  python digest.py
"""

import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from agent_state import heartbeat, set_idle


DASHBOARD_BASE = "https://bids.floorcoveringunlimited.com"


def score_label(bid: dict, spec: dict | None) -> str:
    """Quick label without importing TS scoring — mirrors the Python version in jobwalk.py."""
    if not bid.get("is_relevant"):
        return "Not flooring"
    return "GO" if spec else "Pending"


def build_digest_html(new_bids: list[dict], since: str) -> str:
    rows = ""
    for b in new_bids:
        spec  = b.get("spec")
        if isinstance(spec, list): spec = spec[0] if spec else None
        title  = b.get("title", "—")
        agency = b.get("agency", "—")
        due    = b.get("due_date_raw") or b.get("due_date") or "—"
        bid_id = b.get("bid_id", "")
        link   = f"{DASHBOARD_BASE}/bids/{bid_id}"
        sqft   = spec.get("total_sqft") if spec else None
        sqft_s = f"{sqft:,} SF" if sqft else "—"
        pw     = "⚠ Prev. wage" if (spec and spec.get("prevailing_wage")) else ""
        walk   = "🚶 Job walk" if (spec and spec.get("walk_required")) else ""
        flags  = " · ".join(f for f in [pw, walk] if f)

        rows += f"""
<tr>
  <td style="padding:12px 16px;border-bottom:1px solid #E5DDD0">
    <a href="{link}" style="color:#C8922A;font-weight:600;text-decoration:none">{title}</a>
    {f'<br><span style="font-size:11px;color:#6A6A70">{flags}</span>' if flags else ''}
  </td>
  <td style="padding:12px 16px;border-bottom:1px solid #E5DDD0;font-size:13px;color:#6A6A70">{agency}</td>
  <td style="padding:12px 16px;border-bottom:1px solid #E5DDD0;font-family:monospace;font-size:12px;white-space:nowrap">{due}</td>
  <td style="padding:12px 16px;border-bottom:1px solid #E5DDD0;font-size:12px;color:#6A6A70">{sqft_s}</td>
</tr>"""

    return f"""
<!DOCTYPE html>
<html>
<body style="background:#FAF7F2;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;padding:0;color:#1A1A1C">
<div style="max-width:700px;margin:0 auto;padding:32px 24px">

  <div style="border-left:4px solid #C8922A;padding-left:16px;margin-bottom:28px">
    <p style="margin:0;font-size:11px;color:#6A6A70;letter-spacing:.08em;text-transform:uppercase">FCU Bid Agent · Daily Digest</p>
    <h1 style="margin:6px 0 0;font-size:20px;font-weight:700">{len(new_bids)} new flooring bid{"s" if len(new_bids) != 1 else ""}</h1>
    <p style="margin:4px 0 0;font-size:13px;color:#6A6A70">Found since {since}</p>
  </div>

  <table style="width:100%;border-collapse:collapse;background:#FFFFFF;border:1px solid #E5DDD0;border-radius:8px;overflow:hidden">
    <thead>
      <tr style="background:#E5DDD0">
        <th style="padding:10px 16px;text-align:left;font-size:11px;color:#6A6A70;letter-spacing:.05em;text-transform:uppercase">Title</th>
        <th style="padding:10px 16px;text-align:left;font-size:11px;color:#6A6A70;letter-spacing:.05em;text-transform:uppercase">Agency</th>
        <th style="padding:10px 16px;text-align:left;font-size:11px;color:#6A6A70;letter-spacing:.05em;text-transform:uppercase">Due</th>
        <th style="padding:10px 16px;text-align:left;font-size:11px;color:#6A6A70;letter-spacing:.05em;text-transform:uppercase">Scope</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>

  <div style="text-align:center;margin-top:24px">
    <a href="{DASHBOARD_BASE}" style="background:#C8922A;color:#FAF7F2;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600;font-size:13px">
      Open Dashboard →
    </a>
  </div>

  <p style="margin-top:24px;font-size:12px;color:#6A6A70;text-align:center">
    Floor Covering Unlimited · FCU Bid Agent · Automated daily digest
  </p>
</div>
</body>
</html>"""


def main():
    import requests
    from supabase import create_client

    heartbeat("digest", status="running")

    sb         = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    resend_key = os.getenv("RESEND_API_KEY")
    joanne     = os.getenv("JOANNE_EMAIL") or os.getenv("NOTIFY_EMAIL")
    ben        = os.getenv("BEN_EMAIL")

    recipients = [r for r in [joanne, ben] if r]
    if not resend_key or not recipients:
        print("⚠ RESEND_API_KEY or recipient emails not set — skipping digest")
        set_idle("digest")
        return

    # New relevant bids added in the last 25 hours (overlap handles timing drift)
    since_dt  = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    since_str = date.today().strftime("%B %d, %Y")

    rows = (
        sb.table("bids")
        .select("*, spec:bid_specs(*)")
        .eq("is_relevant", True)
        .gte("first_seen_at", since_dt)
        .neq("bid_status", "expired")
        .order("due_date", desc=False)
        .execute()
        .data or []
    )

    print(f"Digest: {len(rows)} new relevant bids since {since_str}")

    if not rows:
        print("Nothing new — skipping email")
        set_idle("digest")
        return

    html = build_digest_html(rows, since_str)
    subject = f"[FCU] {len(rows)} new flooring bid{'s' if len(rows) != 1 else ''} — {since_str}"

    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
        json={
            "from": "FCU Bid Agent <agent@bids.benlee.ventures>",
            "to": recipients,
            "subject": subject,
            "html": html,
        },
        timeout=10,
    )

    if resp.ok:
        print(f"  ✓ Digest sent to: {', '.join(recipients)}")
    else:
        print(f"  ✗ Digest email failed: {resp.text[:300]}")

    set_idle("digest")


if __name__ == "__main__":
    main()
