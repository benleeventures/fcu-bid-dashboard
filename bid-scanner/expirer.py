"""
FCU Bid Expirer — runs daily at 7:30am via launchd.

Finds bids where the deadline has passed and no decision was made
(status is active or null) and marks them as 'expired'.

This keeps the dashboard clean without any manual work.
Bids with status submitted/won/lost/no_bid are never touched.

Usage:
  python expirer.py
"""

import os
import sys
from datetime import date
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from agent_state import heartbeat, set_idle, set_error


def main():
    from supabase import create_client

    heartbeat("expirer", status="running")

    sb    = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
    today = date.today().isoformat()

    # Bids past due that were never acted on
    rows = (
        sb.table("bids")
        .select("bid_id, title, due_date, bid_status")
        .lt("due_date", today)
        .or_("bid_status.is.null,bid_status.eq.active")
        .execute()
        .data or []
    )

    print(f"Expirer: {len(rows)} past-due active bids found")

    expired = 0
    for row in rows:
        sb.table("bids").update({"bid_status": "expired"}).eq("bid_id", row["bid_id"]).execute()
        print(f"  ↪ expired: {row['bid_id']} — {row.get('title','')[:60]} (due {row.get('due_date','')})")
        expired += 1

    print(f"Expirer done — {expired} bids marked expired")
    set_idle("expirer")


if __name__ == "__main__":
    main()
