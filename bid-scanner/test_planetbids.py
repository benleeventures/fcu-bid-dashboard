"""
PlanetBids scraper — cookie-based auth to bypass AWS WAF CAPTCHA.

  SUPERVISED MODE (with Claude):
    python test_planetbids.py --save-cookies

  Chrome opens → you solve CAPTCHA + log in → tell Claude "done" → cookies saved.
  Claude writes captcha.done to signal the script to continue.

  DAILY USE:
    python test_planetbids.py

  Loads saved cookies, runs headlessly, extracts bids.
"""

import asyncio
import json
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
EMAIL = "floorcoveringunltd@msn.com"
PASSWORD = "LVTFloors9601$"

SCRIPT_DIR = Path(__file__).parent
COOKIES_FILE = SCRIPT_DIR / "cookies.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def save_cookies():
    """
    Open Chrome, wait for user to solve CAPTCHA and press Enter, save cookies.
    """
    print("=" * 60)
    print("PLANETBIDS — COOKIE SETUP")
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

        cookies = await ctx.cookies()
        COOKIES_FILE.write_text(json.dumps(cookies, indent=2))

        useful = [c["name"] for c in cookies if any(
            k in c["name"].lower() for k in ["waf", "session", "auth", "token", "login"]
        )]
        print(f"\n✓ Saved {len(cookies)} cookies → {COOKIES_FILE.name}")
        print(f"  Key cookies: {', '.join(useful) or '(check manually)'}")
        await browser.close()


async def scrape_bids():
    """Load saved cookies and extract bids from PlanetBids portal."""
    if not COOKIES_FILE.exists():
        print("No cookies.json found. Run: python test_planetbids.py --save-cookies")
        return

    cookies = json.loads(COOKIES_FILE.read_text())
    print(f"Loaded {len(cookies)} cookies from {COOKIES_FILE.name}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = await browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        await ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        await ctx.add_cookies(cookies)
        page = await ctx.new_page()

        search_url = f"{BASE}/portal/{PORTAL_ID}/bo/bo-search"
        print(f"\nNavigating to: {search_url}")
        await page.goto(search_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        title = await page.title()
        current_url = page.url
        print(f"Title: {title}")
        print(f"URL:   {current_url}")

        if "verification" in title.lower() or "captcha" in title.lower() or "human" in title.lower():
            print("\n⚠  Cookies expired — rerun with --save-cookies to refresh.")
            await browser.close()
            return

        if "login" in current_url.lower():
            print("Redirected to login — attempting auto-login...")
            email_el = await page.query_selector('input[type="email"], input[name*="email" i]')
            pass_el = await page.query_selector('input[type="password"]')
            if email_el and pass_el:
                await email_el.fill(EMAIL)
                await pass_el.fill(PASSWORD)
                submit = await page.query_selector('button[type="submit"], input[type="submit"]')
                if submit:
                    await submit.click()
                    await page.wait_for_load_state("networkidle", timeout=20000)
                    await page.wait_for_timeout(2000)
                    print(f"After login: {page.url}")
                    await page.goto(search_url, wait_until="networkidle", timeout=30000)
                    await page.wait_for_timeout(2000)

        body = await page.inner_text("body")
        lines = [l.strip() for l in body.split("\n") if l.strip()]
        print(f"\nPage preview (first 50 lines):")
        for line in lines[:50]:
            print(f"  {line}")

        bid_links = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a')).map(a => ({
                href: a.href,
                text: (a.innerText || '').trim().substring(0, 100)
            })).filter(l => l.href.includes('/bo/bo-detail/') || l.href.includes('/bid/'));
        }""")

        print(f"\nBid links found: {len(bid_links)}")
        for link in bid_links[:20]:
            print(f"  [{link['text']}] → {link['href']}")

        rows = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('tr, .bid-row, [class*="bid"]')).map(r => ({
                tag: r.tagName,
                cls: r.className,
                text: (r.innerText || '').trim().substring(0, 150).replace(/\\n/g, ' | ')
            })).filter(r => r.text.length > 10).slice(0, 20);
        }""")

        print(f"\nTable/bid rows ({len(rows)}):")
        for row in rows[:15]:
            print(f"  [{row['tag']}.{row['cls'][:30]}] {row['text']}")

        await browser.close()


if __name__ == "__main__":
    if "--save-cookies" in sys.argv:
        asyncio.run(save_cookies())
    else:
        asyncio.run(scrape_bids())
