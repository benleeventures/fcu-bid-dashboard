"""
FCU Bid Scanner — One-time cookie setup for CAPTCHA-protected sources.

Usage (supervised with Claude):
    python setup_cookies.py

Opens Chrome for each protected source in sequence.
Solve the CAPTCHA/Cloudflare check, then tell Claude "done".
Claude signals the script to continue to the next source.

Sources:
  1. PlanetBids  → saves cookies.json
  2. OpenGov     → saves cookies_opengov.json
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

SCRIPT_DIR = Path(__file__).parent
FLAG_NEEDED = SCRIPT_DIR / "captcha.flag"
FLAG_DONE   = SCRIPT_DIR / "captcha.done"

PLANETBIDS_COOKIES = SCRIPT_DIR / "cookies.json"
OPENGOV_COOKIES    = SCRIPT_DIR / "cookies_opengov.json"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def _wait_for_done(label: str, timeout: int = 600):
    FLAG_DONE.unlink(missing_ok=True)
    FLAG_NEEDED.write_text(f"{label} — waiting for user")
    print(f"\n✓ captcha.flag written [{label}]")
    print(f"→ Tell Claude 'done' after completing the {label} check.\n")
    elapsed = 0
    while elapsed < timeout:
        await asyncio.sleep(3)
        elapsed += 3
        if FLAG_DONE.exists():
            FLAG_DONE.unlink()
            FLAG_NEEDED.unlink(missing_ok=True)
            print(f"  ✓ Done signal received")
            return
    print(f"  ⚠ Timeout — saving whatever cookies exist")
    FLAG_NEEDED.unlink(missing_ok=True)


async def collect_planetbids(p):
    print("\n" + "=" * 50)
    print("STEP 1 OF 2 — PlanetBids (AWS WAF CAPTCHA)")
    print("=" * 50)

    try:
        browser = await p.chromium.launch(channel="chrome", headless=False)
    except Exception:
        browser = await p.chromium.launch(headless=False)

    ctx = await browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
    page = await ctx.new_page()

    url = "https://vendors.planetbids.com/portal/39493/bo/bo-search"
    print(f"Opening: {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)

    await _wait_for_done("PlanetBids CAPTCHA")

    cookies = await ctx.cookies()
    PLANETBIDS_COOKIES.write_text(json.dumps(cookies, indent=2))
    useful = [c["name"] for c in cookies if any(k in c["name"].lower() for k in ["waf", "session", "auth", "token"])]
    print(f"✓ Saved {len(cookies)} PlanetBids cookies — key: {', '.join(useful) or '(check manually)'}")
    await browser.close()


async def collect_opengov(p):
    print("\n" + "=" * 50)
    print("STEP 2 OF 2 — OpenGov (Cloudflare)")
    print("=" * 50)

    try:
        browser = await p.chromium.launch(channel="chrome", headless=False)
    except Exception:
        browser = await p.chromium.launch(headless=False)

    ctx = await browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
    page = await ctx.new_page()

    # Use Pasadena as the trigger portal — same Cloudflare domain covers all portals
    url = "https://procurement.opengov.com/portal/pasadena"
    print(f"Opening: {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)

    await _wait_for_done("OpenGov Cloudflare")

    cookies = await ctx.cookies()
    OPENGOV_COOKIES.write_text(json.dumps(cookies, indent=2))
    print(f"✓ Saved {len(cookies)} OpenGov cookies")
    await browser.close()


async def main():
    print("FCU Bid Scanner — Cookie Setup")
    print("Two Chrome windows will open in sequence.")
    print("Solve each check, then tell Claude 'done'.\n")

    async with async_playwright() as p:
        await collect_planetbids(p)
        await collect_opengov(p)

    print("\n" + "=" * 50)
    print("✓ All cookies saved. Run the scanner:")
    print("  python3 main.py")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
