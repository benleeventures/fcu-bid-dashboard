"""
FCU Expirer — soft-archive past-due relevant bids
Runs daily at 7:30am via launchd (com.fcu.expirer).

Sets is_relevant=False for bids whose due_date has passed so they drop
out of the active dashboard view. Logs what was archived.
"""

import logging
import os
import sys
from datetime import date
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

LOG_FILE = Path(__file__).parent / "logs" / "expirer.log"
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)
log = logging.getLogger(__name__)


def run(dry_run: bool = False):
    from supabase import create_client
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        log.error("SUPABASE_URL/SUPABASE_KEY not set")
        sys.exit(1)
    sb = create_client(url, key)

    today = date.today().isoformat()

    resp = (
        sb.table("bids")
        .select("bid_id,title,agency,due_date,source")
        .lt("due_date", today)
        .neq("bid_status", "expired")
        .execute()
    )
    past_due = resp.data or []

    if not past_due:
        log.info("No past-due relevant bids — nothing to expire")
        print("✓ Nothing to expire")
        return

    log.info(f"Found {len(past_due)} past-due bid(s){'(dry run)' if dry_run else ''}")
    for b in past_due:
        log.info(f"  {'[DRY]' if dry_run else '[EXPIRE]'} {b['bid_id']} — {b['title'][:55]} (due {b.get('due_date')} · {b.get('source')})")

    if dry_run:
        print(f"Dry run — {len(past_due)} bids would be expired. Re-run without --dry-run to apply.")
        return

    ids = [b["bid_id"] for b in past_due]
    expired = 0
    for i in range(0, len(ids), 100):
        try:
            sb.table("bids").update({"bid_status": "expired", "is_relevant": False}).in_("bid_id", ids[i:i + 100]).execute()
            expired += len(ids[i:i + 100])
        except Exception as e:
            log.error(f"Update error: {e}")

    log.info(f"Expired {expired} bid(s)")
    print(f"✓ Expired {expired} past-due bids")

    # --- Sync manually-set no_bid / expired → is_relevant=False ---
    manual_resp = (
        sb.table("bids")
        .select("bid_id,title,bid_status")
        .eq("is_relevant", True)
        .in_("bid_status", ["no_bid", "expired"])
        .execute()
    )
    manual = manual_resp.data or []

    if manual:
        log.info(f"Found {len(manual)} manually-closed bid(s) still marked relevant{'(dry run)' if dry_run else ''}")
        for b in manual:
            log.info(f"  {'[DRY]' if dry_run else '[SYNC]'} {b['bid_id']} — {b['title'][:55]} (status: {b['bid_status']})")

        if not dry_run:
            manual_ids = [b["bid_id"] for b in manual]
            synced = 0
            for i in range(0, len(manual_ids), 100):
                try:
                    sb.table("bids").update({"is_relevant": False}).in_("bid_id", manual_ids[i:i+100]).execute()
                    synced += len(manual_ids[i:i+100])
                except Exception as e:
                    log.error(f"Sync update error: {e}")
            log.info(f"Synced {synced} manually-closed bid(s)")
            print(f"✓ Synced {synced} manually-closed bids (no_bid/expired → archived)")
    else:
        log.info("No manually-closed bids to sync")


if __name__ == "__main__":
    dry = "--dry-run" in __import__("sys").argv
    run(dry_run=dry)
