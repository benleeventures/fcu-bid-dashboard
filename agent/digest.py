"""
Digest formatter — builds the plain text and HTML email body.
"""
from datetime import date

from config import FOLLOWUP_URGENT_DAYS


def _days_label(last_contacted: date | None) -> str:
    if not last_contacted:
        return "never contacted"
    delta = (date.today() - last_contacted).days
    return f"{delta} day{'s' if delta != 1 else ''} since last contact"


def _value_str(val: float | None) -> str:
    if val is None:
        return "est. unknown"
    if val >= 1_000_000:
        return f"est. ${val/1_000_000:.1f}M"
    if val >= 1_000:
        return f"est. ${val/1_000:.0f}k"
    return f"est. ${val:.0f}"


def _urgent(contact: dict) -> bool:
    if not contact["last_contacted"]:
        return True
    return (date.today() - contact["last_contacted"]).days >= FOLLOWUP_URGENT_DAYS


# ── Plain text ───────────────────────────────────────────────────────────────

def build_plain(
    new_bids: list[dict],
    bids_due: list[dict],
    followups: list[tuple[dict, list[dict], str]],  # (contact, log, suggestion)
) -> str:
    today = date.today().strftime("%A, %B %-d")
    lines = [f"Good morning — FCU Sales Digest for {today}", ""]

    # New bids
    lines.append(f"NEW BIDS ({len(new_bids)})")
    if new_bids:
        for b in new_bids:
            lines.append(f"  • {b['bid_name']} — {b['agency']}, {_value_str(b['estimated_value'])}")
    else:
        lines.append("  No new bids today.")
    lines.append("")

    # Follow-ups
    lines.append(f"FOLLOW-UPS DUE ({len(followups)})")
    if followups:
        for contact, log, suggestion in followups:
            urgency = "⚠ " if _urgent(contact) else ""
            lines.append(
                f"  {urgency}• {contact['name']} ({contact['company']}) — "
                f"{_days_label(contact['last_contacted'])}, status: {contact['status']}"
            )
            if suggestion:
                for line in suggestion.split("\n"):
                    lines.append(f"    AI: {line}")
        lines.append("")
    else:
        lines.append("  No follow-ups due today.")
        lines.append("")

    # Deadlines this week
    lines.append(f"DEADLINES THIS WEEK ({len(bids_due)})")
    if bids_due:
        for b in bids_due:
            due = b["due_date"].strftime("%A %b %-d") if b["due_date"] else "unknown"
            lines.append(f"  • {b['bid_name']} — due {due}")
    else:
        lines.append("  No upcoming deadlines.")
    lines.append("")

    return "\n".join(lines)


# ── HTML ─────────────────────────────────────────────────────────────────────

def build_html(
    new_bids: list[dict],
    bids_due: list[dict],
    followups: list[tuple[dict, list[dict], str]],
) -> str:
    today = date.today().strftime("%A, %B %-d")

    def section(title: str, count: int, body: str) -> str:
        return f"""
        <div style="margin-bottom:28px">
          <h2 style="font-size:13px;font-weight:700;text-transform:uppercase;
                     letter-spacing:1px;color:#1a1a2e;border-bottom:2px solid #e8e8e8;
                     padding-bottom:6px;margin-bottom:12px">
            {title} <span style="color:#666;font-weight:400">({count})</span>
          </h2>
          {body}
        </div>"""

    # New bids body
    if new_bids:
        bid_items = "".join(
            f'<li style="padding:4px 0">'
            f'<strong>{b["bid_name"]}</strong> — {b["agency"]}, '
            f'<span style="color:#555">{_value_str(b["estimated_value"])}</span></li>'
            for b in new_bids
        )
        bids_html = f'<ul style="margin:0;padding-left:18px">{bid_items}</ul>'
    else:
        bids_html = '<p style="color:#888;margin:0">No new bids today.</p>'

    # Follow-ups body
    if followups:
        fu_items = []
        for contact, log, suggestion in followups:
            urgent_color = "#c0392b" if _urgent(contact) else "#2c3e50"
            touches = len(log)
            fu_items.append(f"""
            <div style="padding:10px 0;border-bottom:1px solid #f0f0f0">
              <div style="font-weight:600;color:{urgent_color}">
                {contact['name']}
                <span style="font-weight:400;color:#555"> — {contact['company']}</span>
              </div>
              <div style="font-size:12px;color:#777;margin:2px 0">
                {_days_label(contact['last_contacted'])} &nbsp;·&nbsp;
                Status: {contact['status']} &nbsp;·&nbsp;
                {touches} touchpoint{'s' if touches != 1 else ''}
              </div>
              {f'<div style="margin-top:6px;padding:8px 10px;background:#f7f9fc;border-left:3px solid #3498db;font-size:13px;color:#333">'
               f'<strong>AI:</strong> {suggestion}</div>' if suggestion else ''}
            </div>""")
        fu_html = "".join(fu_items)
    else:
        fu_html = '<p style="color:#888;margin:0">No follow-ups due today.</p>'

    # Deadlines body
    if bids_due:
        dl_items = "".join(
            f'<li style="padding:4px 0">'
            f'<strong>{b["bid_name"]}</strong> — due '
            f'<span style="color:#c0392b">{b["due_date"].strftime("%A %b %-d") if b["due_date"] else "unknown"}</span>'
            f'</li>'
            for b in bids_due
        )
        dl_html = f'<ul style="margin:0;padding-left:18px">{dl_items}</ul>'
    else:
        dl_html = '<p style="color:#888;margin:0">No upcoming deadlines.</p>'

    return f"""<!DOCTYPE html>
<html>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
             max-width:620px;margin:0 auto;padding:24px;color:#1a1a2e;font-size:14px">
  <div style="margin-bottom:24px">
    <h1 style="font-size:18px;font-weight:700;margin:0">FCU Sales Digest</h1>
    <p style="color:#777;margin:4px 0 0">{today}</p>
  </div>

  {section("New Bids", len(new_bids), bids_html)}
  {section("Follow-ups Due", len(followups), fu_html)}
  {section("Deadlines This Week", len(bids_due), dl_html)}

  <p style="font-size:11px;color:#bbb;margin-top:32px;border-top:1px solid #eee;padding-top:12px">
    FCU Sales Intelligence · automated digest
  </p>
</body>
</html>"""
