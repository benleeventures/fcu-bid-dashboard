"""
FCU Bid Scanner — entry point

Usage:
  python main.py                    # run full scan
  python main.py --check-cookies    # just check if cookies are valid
"""

import asyncio
import os
import sys
from datetime import date
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional — set vars in environment directly

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")


async def main():
    import time
    from scanner import run_scan, SEARCH_KEYWORDS
    from report import generate_report
    from notify import check_planetbids_cookies, send_notification
    from db import upsert_bids, log_scan

    print("FCU Bid Scanner")
    print("=" * 50)

    # --- Cookie check before starting ---
    pb_email = os.getenv("PLANETBIDS_EMAIL", "")
    if pb_email:
        valid, reason = check_planetbids_cookies()
        if not valid:
            send_notification(reason)
            sys.exit(1)
        elif "warning" in reason:
            print(f"⚠  Cookie warning: {reason}")

    print(f"Searching {len(SEARCH_KEYWORDS)} keyword groups across sources...\n")

    t_start = time.time()
    bids = await run_scan()
    duration = time.time() - t_start

    if not bids:
        print("\n⚠ No bids found. Check internet connection or agency portal availability.")
        sys.exit(0)

    relevant = sum(1 for b in bids if b["is_relevant"])

    # --- Persist to Supabase ---
    new_count = 0
    if sb_url := os.getenv("SUPABASE_URL", ""):
        print("\nSaving to Supabase...")
        new_count, updated_count = upsert_bids(bids)
        source_counts = {}
        for b in bids:
            s = b.get("source", "unknown")
            source_counts[s] = source_counts.get(s, 0) + 1
        log_scan(len(bids), relevant, new_count, source_counts, duration)
        print(f"  ✓ {new_count} new bids added · {updated_count} existing updated")
    else:
        print("\n  (Supabase not configured — set SUPABASE_URL + SUPABASE_KEY in .env to persist)")

    # --- New-bid email digest ---
    if new_count > 0:
        new_relevant = [b for b in bids if b.get("is_relevant") and b.get("_is_new")]
        if new_relevant:
            print(f"\nSending new-bid digest ({len(new_relevant)} relevant)...")
            from notify import send_new_bids_digest
            send_new_bids_digest(new_relevant)
        elif os.getenv("NOTIFY_EMAIL"):
            # No new relevant bids this run — skip silently
            pass

    # --- HTML report ---
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_file = os.path.join(OUTPUT_DIR, f"bid-report-{date.today()}.html")
    generate_report(bids, output_file)

    print(f"\n✓ Report saved: {output_file}")
    print(f"  {len(bids)} total bids · {relevant} flooring/relevant")
    print(f"\nOpen in browser:")
    print(f"  open \"{output_file}\"")


if __name__ == "__main__":
    if "--check-cookies" in sys.argv:
        from notify import check_planetbids_cookies, send_notification
        valid, reason = check_planetbids_cookies()
        if valid:
            print(f"✓ PlanetBids cookies OK — {reason}")
        else:
            print(f"✗ PlanetBids cookies need refresh — {reason}")
            send_notification(reason)
        sys.exit(0 if valid else 1)

    asyncio.run(main())
