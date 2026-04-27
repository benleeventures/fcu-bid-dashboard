"""
FCU Daily Digest — runs at 7:00am via launchd.

Sends ONE daily email to Joanne + Ben with new GO/MAYBE scored bids
that have parsed spec documents. Bids without parsed specs are excluded
(those go to ADMIN_EMAIL via parser.py's no-spec alert instead).

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
from scoring import score_bid


DASHBOARD_BASE = "https://bids.floorcoveringunlimited.com"

VERDICT_LABEL = {"go": "GO", "maybe": "MAYBE", "no_go": "NO-GO"}
VERDICT_COLOR = {"go": "#2A8A3E", "maybe": "#C8922A", "no_go": "#D93025"}


def _get_spec(row: dict) -> dict | None:
    spec = row.get("spec")
    if isinstance(spec, list):
        return spec[0] if spec else None
    return spec or None


def build_digest_html(new_bids: list[dict], since: str) -> str:
    rows = ""
    for b in new_bids:
        spec   = _get_spec(b)
        result = score_bid(b, spec)
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
        verdict = result["verdict"]
        score   = result["score"]
        v_label = VERDICT_LABEL[verdict]
        v_color = VERDICT_COLOR[verdict]

        rows += f"""
<tr>
  <td style="padding:12px 16px;border-bottom:1px solid #E5DDD0">
    <a href="{link}" style="color:#C8922A;font-weight:600;text-decoration:none">{title}</a>
    {f'<br><span style="font-size:11px;color:#6A6A70">{flags}</span>' if flags else ''}
  </td>
  <td style="padding:12px 16px;border-bottom:1px solid #E5DDD0;font-size:13px;color:#6A6A70">{agency}</td>
  <td style="padding:12px 16px;border-bottom:1px solid #E5DDD0;font-family:monospace;font-size:12px;white-space:nowrap">{due}</td>
  <td style="padding:12px 16px;border-bottom:1px solid #E5DDD0;font-size:12px;color:#6A6A70">{sqft_s}</td>
  <td style="padding:12px 16px;border-bottom:1px solid #E5DDD0;text-align:center">
    <span style="background:{v_color}22;color:{v_color};padding:2px 7px;border-radius:4px;font-family:monospace;font-size:11px;font-weight:700">{v_label} {score}</span>
  </td>
</tr>"""

    return f"""
<!DOCTYPE html>
<html>
<body style="background:#FAF7F2;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;padding:0;color:#1A1A1C">
<div style="max-width:740px;margin:0 auto;padding:32px 24px">

  <div style="border-left:4px solid #C8922A;padding-left:16px;margin-bottom:28px">
    <p style="margin:0;font-size:11px;color:#6A6A70;letter-spacing:.08em;text-transform:uppercase">FCU Bid Agent · Daily Digest</p>
    <h1 style="margin:6px 0 0;font-size:20px;font-weight:700">{len(new_bids)} new bid{"s" if len(new_bids) != 1 else ""} to review</h1>
    <p style="margin:4px 0 0;font-size:13px;color:#6A6A70">GO and MAYBE scored · Found since {since}</p>
  </div>

  <table style="width:100%;border-collapse:collapse;background:#FFFFFF;border:1px solid #E5DDD0;border-radius:8px;overflow:hidden">
    <thead>
      <tr style="background:#E5DDD0">
        <th style="padding:10px 16px;text-align:left;font-size:11px;color:#6A6A70;letter-spacing:.05em;text-transform:uppercase">Title</th>
        <th style="padding:10px 16px;text-align:left;font-size:11px;color:#6A6A70;letter-spacing:.05em;text-transform:uppercase">Agency</th>
        <th style="padding:10px 16px;text-align:left;font-size:11px;color:#6A6A70;letter-spacing:.05em;text-transform:uppercase">Due</th>
        <th style="padding:10px 16px;text-align:left;font-size:11px;color:#6A6A70;letter-spacing:.05em;text-transform:uppercase">Scope</th>
        <th style="padding:10px 16px;text-align:center;font-size:11px;color:#6A6A70;letter-spacing:.05em;text-transform:uppercase">Score</th>
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
    Floor Covering Unlimited · FCU Bid Agent · Daily digest — GO and MAYBE bids only
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

    # Only bids with parsed spec documents
    rows = [r for r in rows if _get_spec(r)]

    # Only GO or MAYBE scored bids
    rows = [r for r in rows if score_bid(r, _get_spec(r))["verdict"] in ("go", "maybe")]

    print(f"Digest: {len(rows)} GO/MAYBE bids with docs since {since_str}")

    if not rows:
        print("Nothing to send — skipping email")
        set_idle("digest")
        return

    html = build_digest_html(rows, since_str)
    subject = f"[FCU] {len(rows)} new bid{'s' if len(rows) != 1 else ''} to review — {since_str}"

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
