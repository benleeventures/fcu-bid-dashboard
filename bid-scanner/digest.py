"""
FCU Daily Digest — morning briefing after parsing
Runs daily at 7:00am via launchd (com.fcu.digest).

Sends a richer email than the scan-time new-bid alert: includes parsed
bid_specs (sqft, compliance flags, walk status) for any bids parsed in
the last 24h, plus a count of still-unprocessed bids awaiting parsing.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from logsetup import setup
from notify import DASHBOARD_URL, dashboard_bid_url
log = setup("digest")


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

    # Relevant bids by parse lifecycle. "pending" = still actionable (no spec,
    # not terminal, under the attempt cap). "stuck" = gave up (no_docs /
    # unparseable) — surfaced separately so the pending number stays honest.
    MAX_PARSE_ATTEMPTS = 3
    TERMINAL = {"parsed", "no_docs", "unparseable", "skipped"}
    _COLS = "bid_id,title,agency,due_date,due_date_raw,url,source,parse_status,parse_attempts"
    try:
        all_relevant_resp = (
            sb.table("bids").select(_COLS)
            .eq("is_relevant", True).execute()
        )
    except Exception:
        all_relevant_resp = sb.table("bids").select("bid_id").eq("is_relevant", True).execute()
    all_relevant = all_relevant_resp.data or []
    parsed_ids = set()
    for i in range(0, len(all_relevant), 200):
        chunk = [b["bid_id"] for b in all_relevant[i:i+200]]
        parsed_resp = sb.table("bid_specs").select("bid_id").in_("bid_id", chunk).execute()
        parsed_ids.update(r["bid_id"] for r in (parsed_resp.data or []))

    def _due_key(b):
        return b.get("due_date") or "9999-12-31"

    # "pending" = still actionable (no spec, not terminal, under the attempt cap).
    # "stuck" = gave up (no_docs / unparseable) — a human has to pull docs from
    # the portal or write it off. Both itemised below so nothing falls through.
    pending_bids = sorted(
        (b for b in all_relevant
         if b["bid_id"] not in parsed_ids
         and (b.get("parse_status") or "") not in TERMINAL
         and (b.get("parse_attempts") or 0) < MAX_PARSE_ATTEMPTS),
        key=_due_key,
    )
    stuck_bids = sorted(
        (b for b in all_relevant
         if b["bid_id"] not in parsed_ids
         and (b.get("parse_status") or "") in {"no_docs", "unparseable"}),
        key=_due_key,
    )
    unprocessed_count = len(pending_bids)
    stuck_count = len(stuck_bids)

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
        link    = f'<a href="{dashboard_bid_url(s["bid_id"])}" style="color:#C8922A;">View ↗</a>'
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

    def _review_rows(rows: list[dict]) -> str:
        out = ""
        for b in rows:
            title = (b.get("title") or b["bid_id"])[:80]
            agency = b.get("agency") or "—"
            due = b.get("due_date_raw") or b.get("due_date") or "—"
            link = f'<a href="{dashboard_bid_url(b["bid_id"])}" style="color:#C8922A;">Review ↗</a>'
            out += f"""
            <tr>
              <td style="padding:8px 12px;border-bottom:1px solid #2C2C2E;font-size:13px;color:#F5F5F0;">{title}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #2C2C2E;font-size:12px;color:#8E8E93;">{agency}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #2C2C2E;font-size:12px;color:#8E8E93;font-family:monospace;">{due}</td>
              <td style="padding:8px 12px;border-bottom:1px solid #2C2C2E;font-size:12px;font-family:monospace;">{link}</td>
            </tr>"""
        return out

    def _review_table(heading: str, sub: str, rows: list[dict], accent: str, cap: int = 15) -> str:
        if not rows:
            return ""
        shown, extra = rows[:cap], max(0, len(rows) - cap)
        more = (
            f'<p style="margin:10px 0 0;font-size:12px;color:#8E8E93;">'
            f'+ {extra} more — <a href="{DASHBOARD_URL}" style="color:#C8922A;">see the dashboard</a></p>'
            if extra else ""
        )
        return f"""
        <div style="margin-top:20px;">
          <h2 style="font-size:13px;font-weight:700;color:{accent};letter-spacing:.06em;text-transform:uppercase;margin:0 0 4px;">{heading} ({len(rows)})</h2>
          <p style="margin:0 0 10px;font-size:12px;color:#8E8E93;">{sub}</p>
          <table style="width:100%;border-collapse:collapse;background:#2C2C2E;border-radius:8px;overflow:hidden;">
            <thead><tr style="background:#3A3A3C;">
              <th style="padding:8px 12px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;">Title</th>
              <th style="padding:8px 12px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;">Agency</th>
              <th style="padding:8px 12px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;">Due</th>
              <th style="padding:8px 12px;text-align:left;font-size:10px;color:#8E8E93;letter-spacing:.06em;text-transform:uppercase;"></th>
            </tr></thead>
            <tbody>{_review_rows(shown)}</tbody>
          </table>
          {more}
        </div>"""

    pending_note = (
        _review_table(
            "Awaiting parse", "No spec yet — the 6:30am <code>--parse-all --claude</code> job retries these automatically.",
            pending_bids, "#8E8E93",
        )
        + _review_table(
            "Needs a human — stuck", "Auto-parse gave up (no docs found, or the docs won't parse). Pull the spec from the portal manually, or mark no-bid.",
            stuck_bids, "#FF9F0A",
        )
    )

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
      <a href="{DASHBOARD_URL}" style="color:#C8922A;">Open Dashboard ↗</a>
    </p>
  </div>
</body>
</html>"""

    _send_resend(recipients, subject, html)
    log.info(f"Digest sent — {count} fresh specs, {unprocessed_count} pending")
    print(f"✓ Digest sent ({count} parsed, {unprocessed_count} pending)")


if __name__ == "__main__":
    run()
