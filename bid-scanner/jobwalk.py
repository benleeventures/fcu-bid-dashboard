"""
FCU Job Walk Notifier — runs daily at 7:15am via launchd.

Finds GO-scored bids with upcoming job walks (next 14 days) that Lenin
hasn't been notified about yet. Sends ONE email per bid (tracked via
walk_notified column in Supabase). CC's Joanne on every email.

Usage:
  python jobwalk.py
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from agent_state import heartbeat, set_idle, set_error
from scoring import score_bid as score_go_no_go


# ── Email builder ─────────────────────────────────────────────────────────────

def build_job_walk_email(bid: dict, spec: dict, score_result: dict) -> tuple[str, str]:
    title      = bid.get("title", "Unknown Job")
    agency     = bid.get("agency", "")
    bid_id     = bid.get("bid_id", "")
    walk_raw   = spec.get("walk_date_raw") or spec.get("walk_date") or "See bid documents"
    sqft       = spec.get("total_sqft")
    sqft_str   = f"{sqft:,} SF" if sqft else "SF TBD"
    ft_types   = ", ".join(spec.get("flooring_types") or []) or "—"
    pw         = "Yes — prevailing wage" if spec.get("prevailing_wage") else "No"
    bond       = "Yes" if spec.get("bid_bond") else "No"
    score      = score_result["score"]
    dashboard  = f"https://bids.floorcoveringunlimited.com/bids/{bid_id}"
    summary    = spec.get("summary", "")

    subject = f"[Job Walk] {title} — {walk_raw}"

    html = f"""
<!DOCTYPE html>
<html>
<body style="background:#FAF7F2;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;padding:0;color:#1A1A1C">
<div style="max-width:640px;margin:0 auto;padding:32px 24px">

  <div style="border-left:4px solid #C8922A;padding-left:16px;margin-bottom:24px">
    <p style="margin:0;font-size:11px;color:#6A6A70;letter-spacing:.08em;text-transform:uppercase">FCU Bid Agent · Job Walk Alert</p>
    <h1 style="margin:6px 0 0;font-size:20px;font-weight:700">{title}</h1>
    <p style="margin:4px 0 0;font-size:13px;color:#6A6A70">{agency}</p>
  </div>

  <div style="background:#FFFFFF;border:1px solid #E5DDD0;border-radius:8px;padding:20px;margin-bottom:20px">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <tr><td style="padding:5px 0;color:#6A6A70;width:130px">Walk Date</td><td style="font-weight:700;color:#C8922A">{walk_raw}</td></tr>
      <tr><td style="padding:5px 0;color:#6A6A70">Agency</td><td>{agency}</td></tr>
      <tr><td style="padding:5px 0;color:#6A6A70">Bid No.</td><td style="font-family:monospace">{bid_id}</td></tr>
      <tr><td style="padding:5px 0;color:#6A6A70">Scope</td><td>{sqft_str} · {ft_types}</td></tr>
      <tr><td style="padding:5px 0;color:#6A6A70">Prev. Wage</td><td>{pw}</td></tr>
      <tr><td style="padding:5px 0;color:#6A6A70">Bid Bond</td><td>{bond}</td></tr>
      <tr><td style="padding:5px 0;color:#6A6A70">GO Score</td><td><strong style="color:#1E7A35">GO — {score}/100</strong></td></tr>
    </table>
    {f'<p style="margin-top:12px;font-size:13px;color:#6A6A70;line-height:1.6">{summary}</p>' if summary else ''}
  </div>

  <div style="background:#FFFFFF;border:1px solid #E5DDD0;border-radius:8px;padding:20px;margin-bottom:20px">
    <h3 style="margin:0 0 14px;font-size:12px;font-weight:700;color:#6A6A70;letter-spacing:.06em;text-transform:uppercase">Job Walk Checklist</h3>
    {"".join(f'<div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:10px"><div style="width:16px;height:16px;border:1.5px solid #C8922A;border-radius:3px;flex-shrink:0;margin-top:1px"></div><span style="font-size:13px">{item}</span></div>' for item in [
      "Site conditions — existing flooring removal complexity, subfloor condition, delivery access",
      "Scope accuracy — do drawings match what's actually there? Hidden scope?",
      "Crew requirements — how many workers? Any specialty skills or difficult conditions?",
      "Timeline feasibility — is the project timeline realistic? Phasing requirements?",
      "Material storage & staging — space on site? Distance from parking to work area?",
      "Competition — likely 10+ bidders? Are we in a strong position?",
      "Profitability gut check — does this feel like a job worth winning?",
    ])}
  </div>

  <div style="text-align:center;margin-top:24px">
    <a href="{dashboard}" style="background:#C8922A;color:#FAF7F2;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600;font-size:13px">
      View Bid in Dashboard →
    </a>
  </div>

  <p style="margin-top:24px;font-size:12px;color:#6A6A70;text-align:center">
    Call Joanne with your BID / NO BID after the walk.<br>
    Floor Covering Unlimited · FCU Bid Agent
  </p>
</div>
</body>
</html>"""

    return subject, html


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import requests
    from supabase import create_client

    heartbeat("jobwalk", status="running")

    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    today     = date.today().isoformat()
    cutoff    = (date.today() + timedelta(days=14)).isoformat()
    resend_key = os.getenv("RESEND_API_KEY")
    lenin_email = os.getenv("LENIN_EMAIL")
    joanne_email = os.getenv("JOANNE_EMAIL") or os.getenv("NOTIFY_EMAIL")

    if not resend_key or not lenin_email:
        print("⚠ RESEND_API_KEY or LENIN_EMAIL not set — skipping job walk notifier")
        set_idle("jobwalk")
        return

    # Bids with upcoming walks not yet notified
    rows = (
        sb.table("bids")
        .select("*, spec:bid_specs(*)")
        .eq("walk_notified", False)
        .gte("walk_date", today)
        .lte("walk_date", cutoff)
        .execute()
        .data or []
    )

    print(f"Job walk notifier: {len(rows)} candidate bids")
    sent = 0

    for row in rows:
        spec = row.get("spec")
        if isinstance(spec, list):
            spec = spec[0] if spec else None
        if not spec or not spec.get("walk_required"):
            continue

        result = score_go_no_go(row, spec)
        if result["verdict"] != "go":
            continue

        subject, html = build_job_walk_email(row, spec, result)
        cc = [joanne_email] if joanne_email else []

        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
            json={
                "from": "FCU Bid Agent <agent@bids.benlee.ventures>",
                "to": [lenin_email],
                "cc": cc,
                "subject": subject,
                "html": html,
            },
            timeout=10,
        )

        if resp.ok:
            sb.table("bids").update({"walk_notified": True}).eq("bid_id", row["bid_id"]).execute()
            print(f"  ✓ Notified Lenin: {row['bid_id']} — {row.get('title', '')[:60]}")
            sent += 1
        else:
            print(f"  ✗ Email failed for {row['bid_id']}: {resp.text[:200]}")

    print(f"Job walk notifier done — {sent} emails sent")
    set_idle("jobwalk")


if __name__ == "__main__":
    main()
