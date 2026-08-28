"""
PlanetBids scraper — opens real Chrome, user solves CAPTCHA, scrapes in same session.

Usage:
  python main.py --source planetbids            ← full scan of all portals
  python main.py --source planetbids --resume   ← retry only blocked/unfinished portals
"""

import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PORTAL_ID = "39493"
BASE = "https://vendors.planetbids.com"

SCRIPT_DIR = Path(__file__).parent

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def run_with_live_browser(keywords: list[str], resume: bool = False) -> list[dict]:
    """
    Open real Chrome, wait for user to solve CAPTCHA, then scrape all portals
    in the same verified browser session. Returns list of bid dicts.

    resume=True re-scrapes only the portals left unfinished (blocked / error /
    pending) by the previous run — see pb_state.py.
    """
    from scanner import _search_planetbids, SEARCH_KEYWORDS

    if not keywords:
        keywords = SEARCH_KEYWORDS

    print("=" * 60)
    print("PLANETBIDS — Opening browser")
    print("=" * 60)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(channel="chrome", headless=False)
        except Exception:
            browser = await p.chromium.launch(headless=False)

        ctx = await browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()

        target = f"{BASE}/portal/{PORTAL_ID}/bo/bo-search"
        print(f"\nOpening Chrome → {target}")
        await page.goto(target, wait_until="domcontentloaded", timeout=30000)

        print("\n→ Solve the CAPTCHA in the Chrome window.")
        print("→ Press Enter here when done.")
        await asyncio.get_event_loop().run_in_executor(None, input, "")

        # Scrape all portals using this verified session
        bids = await _search_planetbids(ctx, keywords, live_page=page, resume=resume)

        await browser.close()
        return bids


if __name__ == "__main__":
    from scanner import SEARCH_KEYWORDS
    bids = asyncio.run(run_with_live_browser(SEARCH_KEYWORDS, resume="--resume" in sys.argv))
    print(f"\n✓ {len(bids)} bids found")
