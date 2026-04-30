"""
FCU Bid Scanner — notification module.

Channels:
  - Scan summary:      send_scan_summary(bids, duration_secs)   ← fires every run
  - New bid digest:    send_new_bids_digest(bids)
  - Cookie expired:    send_notification(reason)

All email goes through Resend API (RESEND_API_KEY in .env).
Recipient: NOTIFY_EMAIL (comma-separated for multiple).

Cookie alerts also fire macOS desktop notification + terminal printout.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

COOKIES_FILE = Path(__file__).parent / "cookies.json"


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


def _recipients() -> list[str]:
    raw = os.getenv("NOTIFY_EMAIL", "")
    return [r.strip() for r in raw.split(",") if r.strip()]


# ─────────────────────────────────────────────
# Scan Summary (fires every run)
# ─────────────────────────────────────────────

def send_scan_summary(bids: list[dict], duration_secs: float):
    """
    Email a per-source summary after every scanner run.
    Lets you spot broken scrapers (0 total) at a glance.
    """
    recipients = _recipients()
    if not recipients:
        return

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
      <a href="https://fcu-dashboard.vercel.app" style="color:#C8922A;">Open Dashboard ↗</a>
    </p>
  </div>
</body>
</html>"""

    _send_resend(recipients, subject, html)
    print(f"  ✓ Scan summary sent ({len(sorted_sources)} sources)")


# ─────────────────────────────────────────────
# New Bid Digest
# ─────────────────────────────────────────────

def send_new_bids_digest(new_bids: list[dict]):
    """
    Email a digest of newly discovered relevant bids.
    new_bids: list of bid dicts from the scanner (title, agency, source, due_date, url).
    """
    recipients = _recipients()
    if not recipients:
        print("  (New-bid digest skipped — set NOTIFY_EMAIL in .env)")
        return
    if not new_bids:
        return

    count = len(new_bids)
    subject = f"[FCU Bid Agent] {count} new relevant bid{'s' if count > 1 else ''} found"

    rows = ""
    for b in new_bids:
        due = b.get("due_date") or b.get("due_date_raw") or "—"
        portal = b.get("url", "")
        link = f'<a href="{portal}" style="color:#C8922A;">View ↗</a>' if portal else "—"
        rows += f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #2C2C2E;font-weight:600;color:#F5F5F0;">{b.get('title','')[:80]}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #2C2C2E;color:#8E8E93;">{b.get('agency','')}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #2C2C2E;color:#8E8E93;font-family:monospace;">{b.get('source','')}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #2C2C2E;color:#8E8E93;font-family:monospace;">{due}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #2C2C2E;font-family:monospace;">{link}</td>
        </tr>"""

    html = f"""
<!DOCTYPE html>
<html>
<body style="background:#1C1C1E;color:#F5F5F0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;padding:0;">
  <div style="max-width:720px;margin:0 auto;padding:32px 24px;">
    <div style="border-left:3px solid #C8922A;padding-left:16px;margin-bottom:28px;">
      <p style="margin:0;font-size:11px;color:#8E8E93;letter-spacing:.08em;text-transform:uppercase;">FCU Bid Agent</p>
      <h1 style="margin:6px 0 0;font-size:22px;font-weight:700;">
        {count} New Relevant Bid{'s' if count > 1 else ''}
      </h1>
      <p style="margin:6px 0 0;font-size:13px;color:#8E8E93;">{datetime.now().strftime('%B %d, %Y')}</p>
    </div>

    <table style="width:100%;border-collapse:collapse;background:#2C2C2E;border-radius:8px;overflow:hidden;">
      <thead>
        <tr style="background:#3A3A3C;">
          <th style="padding:10px 12px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;">Title</th>
          <th style="padding:10px 12px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;">Agency</th>
          <th style="padding:10px 12px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;">Source</th>
          <th style="padding:10px 12px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;">Due</th>
          <th style="padding:10px 12px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;">Portal</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>

    <p style="margin-top:24px;font-size:12px;color:#8E8E93;">
      Review all bids in the <a href="https://fcu-dashboard.vercel.app" style="color:#C8922A;">FCU Dashboard</a>.
      Parse specs with: <code style="background:#2C2C2E;padding:2px 6px;border-radius:3px;">python parser.py --pending</code>
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
    recipients = _recipients()
    if not recipients:
        print("  (RFQ skipped — set NOTIFY_EMAIL in .env)")
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
      Generated by <a href="https://fcu-dashboard.vercel.app" style="color:#C8922A;">FCU Bid Agent</a>
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

    recipients = _recipients()
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
