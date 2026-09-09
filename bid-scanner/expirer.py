"""
FCU Expirer — soft-archive bids that are no longer worth showing.
Runs Mon–Fri 7:30am via launchd (com.fcu.expirer).

Three sweeps, all of which set bid_status='expired' + is_relevant=False so the
row drops out of the active dashboard view (the archive toggle still surfaces it):

  1. Past-due    — due_date has passed
  2. Stale junk  — is_relevant=False and first seen > 30 days ago (we're not
                   bidding it; it just clutters the recent-scans window)
  3. Stale open  — no due_date ever parsed and first seen > 60 days ago
                   (almost certainly closed by now)

Only ever touches bids still in bid_status='active'. Bids manually moved to
submitted/won/lost/no_bid/expired are left alone — clobbering those destroys
win/loss tracking history.

A final pass syncs manually-closed bids (no_bid/expired) that are somehow still
flagged is_relevant=True.
"""

import os
import sys
from datetime import date, datetime, timedelta, timezone

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from logsetup import setup
log = setup("expirer")

STALE_JUNK_DAYS = 30   # non-relevant bids older than this get archived
STALE_OPEN_DAYS = 60   # no-due-date bids older than this get archived


def _expire(sb, rows, reason: str, dry_run: bool) -> int:
    """Archive a batch of candidate rows. Returns count actually expired."""
    if not rows:
        log.info(f"{reason}: nothing to expire")
        return 0

    log.info(f"{reason}: {len(rows)} bid(s){' (dry run)' if dry_run else ''}")
    for b in rows:
        tag = "[DRY]" if dry_run else "[EXPIRE]"
        log.info(f"  {tag} {b['bid_id']} — {(b.get('title') or '')[:55]} "
                 f"(due {b.get('due_date')} · seen {str(b.get('first_seen_at'))[:10]} · {b.get('source')})")

    if dry_run:
        return 0

    ids = [b["bid_id"] for b in rows]
    done = 0
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        try:
            sb.table("bids").update(
                {"bid_status": "expired", "is_relevant": False}
            ).in_("bid_id", chunk).execute()
            done += len(chunk)
        except Exception as e:
            log.error(f"{reason}: update error: {e}")
    return done


def run(dry_run: bool = False):
    from supabase import create_client
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        log.error("SUPABASE_URL/SUPABASE_KEY not set")
        sys.exit(1)
    sb = create_client(url, key)

    today = date.today().isoformat()
    now = datetime.now(timezone.utc)
    junk_cutoff = (now - timedelta(days=STALE_JUNK_DAYS)).isoformat()
    open_cutoff = (now - timedelta(days=STALE_OPEN_DAYS)).isoformat()

    cols = "bid_id,title,agency,due_date,source,first_seen_at"
    total = 0

    # 1. Past-due — due_date has passed. Scoped to bid_status='active' so the
    #    query returns only the handful of real candidates, never the whole
    #    table (PostgREST caps responses at 1000 rows — an unscoped .lt() query
    #    silently dropped past-due bids once the table grew past that).
    past_due = (
        sb.table("bids").select(cols)
        .eq("bid_status", "active").lt("due_date", today)
        .execute().data or []
    )
    total += _expire(sb, past_due, "Past-due", dry_run)

    # 2. Stale junk — non-relevant and old enough that no one is going to bid it.
    stale_junk = (
        sb.table("bids").select(cols)
        .eq("bid_status", "active").eq("is_relevant", False)
        .lt("first_seen_at", junk_cutoff)
        .execute().data or []
    )
    total += _expire(sb, stale_junk, f"Stale junk (>{STALE_JUNK_DAYS}d, not relevant)", dry_run)

    # 3. Stale open — relevant but no due_date was ever parsed, and it's been
    #    sitting for months. Treat as closed.
    stale_open = (
        sb.table("bids").select(cols)
        .eq("bid_status", "active").is_("due_date", "null")
        .lt("first_seen_at", open_cutoff)
        .execute().data or []
    )
    total += _expire(sb, stale_open, f"Stale open (>{STALE_OPEN_DAYS}d, no due date)", dry_run)

    if dry_run:
        print("Dry run — re-run without --dry-run to apply.")
    else:
        log.info(f"Expired {total} bid(s) total")
        print(f"✓ Expired {total} bid(s)" if total else "✓ Nothing to expire")

    # --- Sync manually-closed bids (no_bid/expired) still flagged relevant ---
    manual = (
        sb.table("bids").select("bid_id,title,bid_status")
        .eq("is_relevant", True).in_("bid_status", ["no_bid", "expired"])
        .execute().data or []
    )
    if manual:
        log.info(f"Manual-sync: {len(manual)} closed bid(s) still relevant{' (dry run)' if dry_run else ''}")
        for b in manual:
            tag = "[DRY]" if dry_run else "[SYNC]"
            log.info(f"  {tag} {b['bid_id']} — {(b.get('title') or '')[:55]} ({b['bid_status']})")
        if not dry_run:
            ids = [b["bid_id"] for b in manual]
            synced = 0
            for i in range(0, len(ids), 100):
                chunk = ids[i:i + 100]
                try:
                    sb.table("bids").update({"is_relevant": False}).in_("bid_id", chunk).execute()
                    synced += len(chunk)
                except Exception as e:
                    log.error(f"Manual-sync: update error: {e}")
            log.info(f"Manual-sync: {synced} bid(s)")
            print(f"✓ Synced {synced} manually-closed bids")
    else:
        log.info("Manual-sync: nothing to sync")


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
