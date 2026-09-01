"""
FCU Bid Scanner — entry point

Usage:
  python main.py                        # run full scan (all sources)
  python main.py --source sam           # SAM.gov only (headless, no cookies needed)
  python main.py --source planetbids    # PlanetBids only (requires CAPTCHA solve)
  python main.py --source planetbids --resume  # retry only portals blocked/missed last run
  python main.py --source planetbids --resume --give-up  # ...and don't fail if a few won't load
  python main.py --source opengov       # OpenGov only (requires I'm-not-a-robot solve)
  python main.py --source ucla          # UCLA Capital Programs only (public, no browser)
  python main.py --source longbeach     # Long Beach Buys (BuySpeed) only (public, browser)
  python main.py --source lausd         # LAUSD Facilities bid-date report only (public PDF)
  python main.py --source securebids    # SecureBids / Colbi CA agencies only (public API)
  python main.py --source ramp          # RAMP LA County only (data.lacity.org open-data feed)
  python main.py --intel                # competitive intel: scan PlanetBids awarded bids (+ GC watchlist)
  python main.py --gc-watchlist         # GC watchlist: seed list + harvest from intel data (no browser)
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
GC_WATCHLIST = "--gc-watchlist" in sys.argv
RESUME  = "--resume" in sys.argv
GIVE_UP = "--give-up" in sys.argv   # PlanetBids: exit 0 even if some portals stay blocked

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

    if GC_WATCHLIST:
        # Spec §7 — seed the GC watchlist and harvest GC winners from award
        # data the intel scans have already collected. No browser needed.
        from gc_watchlist import run as run_gc_watchlist
        run_gc_watchlist()
        return

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

            # Spec §7 — reuse the live session to scan general-construction
            # award winners for the GC watchlist.
            gc_summary = {"found": 0, "added": 0}
            try:
                from intel_scanner import run_gc_award_scan
                gc_summary = await run_gc_award_scan(live_page=page)
            except Exception as e:
                print(f"  ⚠ GC watchlist scan failed: {e}")

            await browser.close()

        print(f"\n  ✓ Intel scan complete")
        print(f"    {summary['new_awards']} new awards · {summary['vendors_resolved']} vendors resolved · {summary['new_vendors']} new vendors")
        print(f"    GC watchlist: {gc_summary['found']} GC(s) found · {gc_summary['added']} new")
        return

    if SOURCE == "planetbids":
        # Manual run — open real Chrome, user solves CAPTCHA, scrape and queue in Supabase.
        # Bids are NOT emailed now — they are picked up by the next scheduled run.
        from test_planetbids import run_with_live_browser
        from db import upsert_bids, log_scan, log_scan_run
        from geo import enrich
        from funnel import ScanFunnel
        from scanner import PLANETBIDS_PORTALS
        import pb_state
        bids = await run_with_live_browser(SEARCH_KEYWORDS, resume=RESUME)
        duration = time.time() - t_start

        # Distinguish "portals loaded, nothing matched" from "portals blocked".
        manifest = pb_state.load()
        incomplete = pb_state.unfinished_portal_ids(manifest) if manifest else []

        funnel = ScanFunnel(mode="planetbids")
        for b in bids:
            b.setdefault("source", "PlanetBids")
        funnel.note_raw(bids)
        for b in bids:
            enrich(b)
        funnel.note_geo(bids)
        bids = [b for b in bids if b.get("geo_status") != "out"]
        funnel.note_kept(bids)
        funnel.note_final(bids, len(bids))
        funnel.apply_planetbids_manifest(manifest, PLANETBIDS_PORTALS)
        funnel.finish(duration)

        if not bids:
            log_scan_run(funnel)
            if incomplete:
                print(f"\n⚠ No bids captured and {len(incomplete)} portal(s) still "
                      f"blocked/unfinished.")
                if GIVE_UP:
                    print("  --give-up set — leaving them for the next run.")
                    sys.exit(0)
                print("  Re-run later today:  python main.py --source planetbids --resume")
                sys.exit(1)
            print("\n⚠ No bids found (all portals loaded — nothing matched).")
            sys.exit(0)
        if os.getenv("SUPABASE_URL", ""):
            print("\nQueuing bids for next scheduled digest...")
            new_count, updated_count = upsert_bids(bids)
            log_scan(len(bids), sum(1 for b in bids if b["is_relevant"]), new_count,
                     {"PlanetBids": len(bids)}, duration)
            funnel.new_bids = new_count
            funnel.updated_bids = updated_count
            funnel.note_new(bids)
            log_scan_run(funnel)
            print(f"  ✓ {new_count} new bids queued · {updated_count} already known")
            print(f"  → These will appear in tomorrow's email digest automatically.")
        else:
            print("\n  (Supabase not configured — bids not queued)")
        print(f"\n  {len(bids)} total bids scanned across {len(set(b['agency'] for b in bids))} portals")
        if incomplete and not GIVE_UP:
            print(f"\n⚠ {len(incomplete)} portal(s) still blocked/unfinished — re-run later today:")
            print("    python main.py --source planetbids --resume")
            sys.exit(2)
        if incomplete:
            print(f"\n⚠ {len(incomplete)} portal(s) still blocked — --give-up set, "
                  f"leaving them for the next run.")
        sys.exit(0)

    if SOURCE == "opengov":
        # Manual run — open real Chrome, user handles I'm-not-a-robot, scrape and queue.
        # Bids are NOT emailed now — they are picked up by the next scheduled run.
        from opengov_live import run_opengov_scraper
        from db import upsert_bids, log_scan, log_scan_run
        from geo import enrich
        from funnel import ScanFunnel
        bids = await run_opengov_scraper()
        duration = time.time() - t_start

        funnel = ScanFunnel(mode="opengov")
        for b in bids:
            b.setdefault("source", "OpenGov")
        funnel.note_raw(bids)
        for b in bids:
            enrich(b)
        funnel.note_geo(bids)
        bids = [b for b in bids if b.get("geo_status") != "out"]
        funnel.note_kept(bids)
        funnel.note_final(bids, len(bids))
        funnel.finish(duration)

        if not bids:
            log_scan_run(funnel)
            print("\n⚠ No bids found.")
            sys.exit(0)
        if os.getenv("SUPABASE_URL", ""):
            print("\nQueuing bids for next scheduled digest...")
            new_count, updated_count = upsert_bids(bids)
            log_scan(len(bids), sum(1 for b in bids if b["is_relevant"]), new_count,
                     {"OpenGov": len(bids)}, duration)
            funnel.new_bids = new_count
            funnel.updated_bids = updated_count
            funnel.note_new(bids)
            log_scan_run(funnel)
            print(f"  ✓ {new_count} new bids queued · {updated_count} already known")
            print(f"  → These will appear in tomorrow's email digest automatically.")
        else:
            print("\n  (Supabase not configured — bids not queued)")
        print(f"\n  {len(bids)} total bids scanned across {len(set(b['agency'] for b in bids))} portals")
        return

    # --- Scheduled / full run ---
    from funnel import ScanFunnel
    funnel = ScanFunnel(mode=SOURCE or "full")
    bids = await run_scan(source=SOURCE, headless=HEADLESS, funnel=funnel)
    duration = time.time() - t_start
    funnel.finish(duration)

    if not bids:
        print("\n⚠ No bids found. Check internet connection or agency portal availability.")
        from db import log_scan_run
        log_scan_run(funnel)
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
        funnel.new_bids = new_count
        funnel.updated_bids = updated_count
        funnel.note_new(bids)
        print(f"  ✓ {new_count} new bids added · {updated_count} existing updated")
    else:
        print("\n  (Supabase not configured — set SUPABASE_URL + SUPABASE_KEY in .env to persist)")

    # Merge queued manual bids into the full list for email
    all_bids = bids + queued_pb_bids + queued_og_bids

    new_relevant = [b for b in all_bids if b.get("is_relevant") and b.get("_is_new")]

    # --- Scan summary (always fires) + new-bid digest ---
    from notify import send_scan_summary, send_new_bids_digest, _admin_recipients
    if _admin_recipients():
        print("\nSending scan summary...")
        send_scan_summary(all_bids, duration)

        if new_relevant:
            print(f"  Sending new-bid digest ({len(new_relevant)} relevant)...")
            send_new_bids_digest(new_relevant)
            funnel.digest_sent = True

    if new_relevant and os.getenv("AIRTABLE_API_KEY", "") and os.getenv("AIRTABLE_BASE_ID", ""):
        from airtable_sync import sync_new_bids
        print("\nSyncing new relevant bids to Airtable tracker...")
        added = sync_new_bids(new_relevant)
        print(f"  ✓ {added} new row(s) added to Opportunities")

    # Mark queued manual bids as digested now that the email has been sent
    if queued_pb_bids:
        mark_digested([b["bid_id"] for b in queued_pb_bids])
        print(f"  ✓ {len(queued_pb_bids)} PlanetBids bids marked as digested")

    if queued_og_bids:
        mark_digested([b["bid_id"] for b in queued_og_bids])
        print(f"  ✓ {len(queued_og_bids)} OpenGov bids marked as digested")

    from db import log_scan_run
    run_id = log_scan_run(funnel)
    if run_id:
        print(f"  ✓ scan_run {run_id[:8]} logged "
              f"({funnel.raw_found} raw → {funnel.after_dedup} deduped → "
              f"{funnel.relevant} relevant → {funnel.new_bids} new)")

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
