"""
FCU Bid Scanner — entry point

Usage:
  python main.py                        # run full scan (all sources)
  python main.py --source sam           # SAM.gov only (headless, no cookies needed)
  python main.py --source planetbids    # PlanetBids only (requires CAPTCHA solve)
  python main.py --source opengov       # OpenGov only (requires I'm-not-a-robot solve)
  python main.py --intel                # competitive intel: scan PlanetBids awarded bids
  python main.py --headless             # suppress browser windows
  python main.py --check-cookies        # just check if cookies are valid
"""

import asyncio
import os
import sys
from datetime import date
from pathlib import Path

SOURCE  = next((sys.argv[sys.argv.index("--source") + 1] for i, a in enumerate(sys.argv) if a == "--source"), None) if "--source" in sys.argv else None
HEADLESS = "--headless" in sys.argv
INTEL   = "--intel" in sys.argv

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional — set vars in environment directly


async def main():
    import time
    from scanner import run_scan, SEARCH_KEYWORDS
    from db import upsert_bids, log_scan

    print("FCU Bid Scanner")
    print("=" * 50)

    print(f"Searching {len(SEARCH_KEYWORDS)} keyword groups across sources...\n")

    t_start = time.time()

    if INTEL:
        # On-demand intel scan — open real Chrome, user solves CAPTCHA, scrape awarded bids.
        from intel_scanner import run_intel_scan
        print("=" * 60)
        print("FCU INTEL SCAN — PlanetBids Competitive Intelligence")
        print("=" * 60)
        print("\nOpening Chrome for PlanetBids CAPTCHA verification...")

        from playwright.async_api import async_playwright

        UA = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        PORTAL_ID = "39493"  # Beverly Hills — used for initial CAPTCHA solve

        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(channel="chrome", headless=False)
            except Exception:
                browser = await p.chromium.launch(headless=False)

            ctx = await browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
            page = await ctx.new_page()

            target = f"https://vendors.planetbids.com/portal/{PORTAL_ID}/bo/bo-search"
            print(f"\nOpening Chrome → {target}")
            await page.goto(target, wait_until="domcontentloaded", timeout=30000)

            print("\n→ Solve the CAPTCHA in the Chrome window.")
            print("→ Press Enter here when done.")
            await asyncio.get_event_loop().run_in_executor(None, input, "")

            summary = await run_intel_scan(live_page=page)
            await browser.close()

        print(f"\n  ✓ Intel scan complete")
        print(f"    {summary['new_awards']} new awards · {summary['vendors_resolved']} vendors resolved · {summary['new_vendors']} new vendors")
        return

    if SOURCE == "planetbids":
        # Manual run — open real Chrome, user solves CAPTCHA, scrape and queue in Supabase.
        # Bids are NOT emailed now — they are picked up by the next scheduled run.
        from test_planetbids import run_with_live_browser
        from db import upsert_bids, log_scan
        bids = await run_with_live_browser(SEARCH_KEYWORDS)
        duration = time.time() - t_start
        if not bids:
            print("\n⚠ No bids found.")
            sys.exit(0)
        if os.getenv("SUPABASE_URL", ""):
            print("\nQueuing bids for next scheduled digest...")
            new_count, updated_count = upsert_bids(bids)
            log_scan(len(bids), sum(1 for b in bids if b["is_relevant"]), new_count,
                     {"PlanetBids": len(bids)}, duration)
            print(f"  ✓ {new_count} new bids queued · {updated_count} already known")
            print(f"  → These will appear in tomorrow's email digest automatically.")
        else:
            print("\n  (Supabase not configured — bids not queued)")
        print(f"\n  {len(bids)} total bids scanned across {len(set(b['agency'] for b in bids))} portals")
        return

    if SOURCE == "opengov":
        # Manual run — open real Chrome, user handles I'm-not-a-robot, scrape and queue.
        # Bids are NOT emailed now — they are picked up by the next scheduled run.
        from opengov_live import run_opengov_scraper
        bids = await run_opengov_scraper()
        duration = time.time() - t_start
        if not bids:
            print("\n⚠ No bids found.")
            sys.exit(0)
        if os.getenv("SUPABASE_URL", ""):
            print("\nQueuing bids for next scheduled digest...")
            new_count, updated_count = upsert_bids(bids)
            log_scan(len(bids), sum(1 for b in bids if b["is_relevant"]), new_count,
                     {"OpenGov": len(bids)}, duration)
            print(f"  ✓ {new_count} new bids queued · {updated_count} already known")
            print(f"  → These will appear in tomorrow's email digest automatically.")
        else:
            print("\n  (Supabase not configured — bids not queued)")
        print(f"\n  {len(bids)} total bids scanned across {len(set(b['agency'] for b in bids))} portals")
        return

    # --- Scheduled / full run ---
    bids = await run_scan(source=SOURCE, headless=HEADLESS)
    duration = time.time() - t_start

    if not bids:
        print("\n⚠ No bids found. Check internet connection or agency portal availability.")
        sys.exit(0)

    relevant = sum(1 for b in bids if b["is_relevant"])

    # --- Persist to Supabase ---
    new_count = 0
    queued_pb_bids = []
    queued_og_bids = []
    if os.getenv("SUPABASE_URL", ""):
        print("\nSaving to Supabase...")
        new_count, updated_count = upsert_bids(bids)
        source_counts = {}
        for b in bids:
            s = b.get("source", "unknown")
            source_counts[s] = source_counts.get(s, 0) + 1

        # Pull any manually-scraped bids queued from previous manual runs
        from db import fetch_undigested_planetbids, fetch_undigested_opengov, mark_digested
        queued_pb_bids = fetch_undigested_planetbids()
        if queued_pb_bids:
            print(f"  + {len(queued_pb_bids)} PlanetBids bids pulled from queue")
            for b in queued_pb_bids:
                b["_is_new"] = True  # treat as new for digest purposes
            source_counts["PlanetBids"] = len(queued_pb_bids)

        queued_og_bids = fetch_undigested_opengov()
        if queued_og_bids:
            print(f"  + {len(queued_og_bids)} OpenGov bids pulled from queue")
            for b in queued_og_bids:
                b["_is_new"] = True
            source_counts["OpenGov"] = source_counts.get("OpenGov", 0) + len(queued_og_bids)

        log_scan(len(bids) + len(queued_pb_bids) + len(queued_og_bids), relevant, new_count, source_counts, duration)
        print(f"  ✓ {new_count} new bids added · {updated_count} existing updated")
    else:
        print("\n  (Supabase not configured — set SUPABASE_URL + SUPABASE_KEY in .env to persist)")

    # Merge queued manual bids into the full list for email
    all_bids = bids + queued_pb_bids + queued_og_bids

    # --- Scan summary (always fires) + new-bid digest ---
    from notify import send_scan_summary, send_new_bids_digest, _admin_recipients
    if _admin_recipients():
        print("\nSending scan summary...")
        send_scan_summary(all_bids, duration)

        new_relevant = [b for b in all_bids if b.get("is_relevant") and b.get("_is_new")]
        if new_relevant:
            print(f"  Sending new-bid digest ({len(new_relevant)} relevant)...")
            send_new_bids_digest(new_relevant)

    # Mark queued manual bids as digested now that the email has been sent
    if queued_pb_bids:
        mark_digested([b["bid_id"] for b in queued_pb_bids])
        print(f"  ✓ {len(queued_pb_bids)} PlanetBids bids marked as digested")

    if queued_og_bids:
        mark_digested([b["bid_id"] for b in queued_og_bids])
        print(f"  ✓ {len(queued_og_bids)} OpenGov bids marked as digested")

    print(f"\n  {len(all_bids)} total bids · {relevant} flooring/relevant")


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
