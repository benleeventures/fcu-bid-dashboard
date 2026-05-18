"""
PlanetBids full test — all 34 portals, navigate+capture approach.

Usage:
  cd bid-scanner
  python test_pb3.py           # all 34 portals
  python test_pb3.py 3         # first N portals only
"""

import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from playwright.async_api import async_playwright
from scanner import PLANETBIDS_PORTALS

READY_FILE = Path("/tmp/pb_continue")

_limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
TEST_PORTALS = list(PLANETBIDS_PORTALS.items())[:_limit]

BASE = "https://vendors.planetbids.com"
UA   = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
SKIP_STAGES = {"closed", "canceled", "cancelled", "awarded", "rejected"}


async def scrape_portal(page, portal_id: str, agency: str) -> list[dict]:
    """Navigate to portal and capture the browser's own /papi/bids response."""
    portal_url = f"{BASE}/portal/{portal_id}/bo/bo-search"
    loop = asyncio.get_event_loop()
    captured: asyncio.Future = loop.create_future()

    async def on_response(response, cid=portal_id):
        if "/papi/bids" in response.url and not captured.done():
            if parse_qs(urlparse(response.url).query).get("cid", [""])[0] == cid:
                try:
                    captured.set_result(await response.json())
                except Exception as exc:
                    if not captured.done():
                        captured.set_exception(exc)

    page.on("response", on_response)
    try:
        await page.goto(portal_url, wait_until="domcontentloaded", timeout=30000)
        data = await asyncio.wait_for(captured, timeout=20)
        records = data.get("data", [])
        bids = []
        for rec in records:
            attrs = rec.get("attributes", {})
            title = (attrs.get("title") or "").strip()
            if not title or (attrs.get("stageStr") or "").lower() in SKIP_STAGES:
                continue
            bids.append({
                "title": title,
                "stage": attrs.get("stageStr", ""),
                "due":   str(attrs.get("bidDueDate", ""))[:10],
            })
        return bids
    except asyncio.TimeoutError:
        print(f"    ⚠ Timed out — bids did not load (CAPTCHA re-triggered?)")
        return []
    except Exception as e:
        print(f"    ⚠ Error: {e}")
        return []
    finally:
        page.remove_listener("response", on_response)


async def main():
    print("=" * 60)
    print("PlanetBids 3-portal test — navigate + response capture")
    print("=" * 60)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(channel="chrome", headless=False)
        except Exception:
            browser = await p.chromium.launch(headless=False)

        ctx  = await browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()

        # Portal 1 — user solves CAPTCHA here
        pid1, name1 = TEST_PORTALS[0]
        print(f"\nOpening {name1} → {BASE}/portal/{pid1}/bo/bo-search")
        await page.goto(f"{BASE}/portal/{pid1}/bo/bo-search", wait_until="domcontentloaded", timeout=30000)

        READY_FILE.unlink(missing_ok=True)
        print("\n→ Solve the CAPTCHA and wait for bids to appear.")
        print(f"→ Then:  touch {READY_FILE}")
        while not READY_FILE.exists():
            await asyncio.sleep(1)
        READY_FILE.unlink(missing_ok=True)

        print(f"\n--- Scraping {len(TEST_PORTALS)} portals ---\n")

        results = {}
        for portal_id, agency in TEST_PORTALS:
            print(f"→ {agency} (cid={portal_id})")
            bids = await scrape_portal(page, portal_id, agency)
            results[agency] = bids
            if bids:
                for b in bids:
                    print(f"    [{b['stage']}] {b['title'][:72]} — due {b['due']}")
            else:
                print("    (no open bids)")
            print()

        await browser.close()

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    loaded = sum(1 for v in results.values() if v is not None)
    total  = sum(len(v) for v in results.values())
    for agency, bids in results.items():
        status = "✓" if bids else ("✗" if bids is not None else "⚠")
        print(f"  {status} {agency}: {len(bids)} open bids")
    print(f"\n{loaded}/{len(TEST_PORTALS)} portals loaded  |  {total} total open bids")


if __name__ == "__main__":
    asyncio.run(main())
