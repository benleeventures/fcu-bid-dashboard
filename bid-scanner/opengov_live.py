"""
OpenGov manual scraper — real Chrome + I'm-not-a-robot handling.
Login via env vars OPENGOV_EMAIL / OPENGOV_PASSWORD.

Usage: python main.py --source opengov   (never run this file directly)

After a successful run, cookies are saved to cookies_opengov.json so the
regular scheduled scanner can reuse them without needing a manual run.
"""

import asyncio
import json
import os
import re
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

OPENGOV_BASE       = "https://procurement.opengov.com"
OPENGOV_LOGIN_URL  = f"{OPENGOV_BASE}/login"
COOKIES_FILE       = Path(__file__).parent / "cookies_opengov.json"

OPENGOV_PORTALS = {
    "cityofbell":       "City of Bell",
    "redondo":          "Redondo Beach",
    "citymb":           "Manhattan Beach",
    "pasadena":         "Pasadena",
    "santa-monica-ca":  "Santa Monica",
    "sacramento":       "Sacramento",
    "san-francisco":    "San Francisco",
    "alameda-county":   "Alameda County",
}

_EMAIL    = os.getenv("OPENGOV_EMAIL", "")
_PASSWORD = os.getenv("OPENGOV_PASSWORD", "")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


async def _wait_for_cloudflare(page, agency_name: str):
    """If Cloudflare is showing, pause and let the user solve it before continuing."""
    title = await page.title()
    if "just a moment" in title.lower() or "403" in title or "captcha" in title.lower():
        print(f"    ⚠ [{agency_name}] Cloudflare detected — solve the checkbox in the browser.")
        print(f"    → Press Enter when done.")
        await asyncio.get_event_loop().run_in_executor(None, input, "")
        await page.wait_for_timeout(2000)


async def _scrape_portal_listing(page, portal_slug: str, agency_name: str) -> list[dict]:
    """
    Scrape one OpenGov portal listing page only — no detail page visits.
    Extracts title, due date, and URL entirely from the table.
    Pauses if Cloudflare appears — does NOT move on until user solves it.
    """
    from scanner import _is_relevant

    portal_url = f"{OPENGOV_BASE}/portal/{portal_slug}"
    bids = []

    try:
        await page.goto(portal_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # Pause here if Cloudflare is showing — wait for user to solve before proceeding
        await _wait_for_cloudflare(page, agency_name)

        # Wait for React table
        try:
            await page.wait_for_selector(".rt-tbody .rt-tr, .rt-noData, [class*='solicitation']", timeout=12000)
        except Exception:
            print(f"    ⚠ Table not found — skipping")
            return []

        await page.wait_for_timeout(1000)

        # Extract all rows from the listing table in one JS call — no detail page visits
        rows = await page.evaluate("""() => {
            const rows = [];

            // React Table approach (most OpenGov portals)
            const rtRows = document.querySelectorAll('.rt-tbody .rt-tr');
            if (rtRows.length > 0) {
                rtRows.forEach(row => {
                    const cells = row.querySelectorAll('.rt-td');
                    if (cells.length < 2) return;
                    const title = cells[0]?.innerText?.trim();
                    if (!title || title.length < 3) return;

                    // Find a date in any cell
                    let dueRaw = '';
                    cells.forEach(cell => {
                        const text = cell.innerText.trim();
                        if (!dueRaw && /\d{1,2}\/\d{1,2}\/\d{4}/.test(text)) dueRaw = text;
                    });

                    const link = row.querySelector('a');
                    rows.push({
                        title:   title,
                        due_raw: dueRaw,
                        href:    link?.href || '',
                    });
                });
                return rows;
            }

            // Fallback: card-based layout
            const cards = document.querySelectorAll('[class*="solicitation"], [class*="bid-card"], article');
            cards.forEach(card => {
                const title = card.querySelector('h2, h3, [class*="title"]')?.innerText?.trim();
                if (!title) return;
                const text = card.innerText;
                const dm = text.match(/\d{1,2}\/\d{1,2}\/\d{4}/);
                const link = card.querySelector('a');
                rows.push({
                    title:   title,
                    due_raw: dm ? dm[0] : '',
                    href:    link?.href || '',
                });
            });
            return rows;
        }""")

        if not rows:
            print(f"    0 bids found")
            return []

        for i, row in enumerate(rows):
            title = row.get("title", "")
            due_raw = row.get("due_raw", "")
            href = row.get("href", "") or portal_url

            # Extract project ID from URL if available
            m = re.search(r"/projects/(\d+)", href)
            project_id = m.group(1) if m else str(i)

            bids.append({
                "bid_id":         f"OG-{portal_slug}-{project_id}",
                "title":          title,
                "agency":         agency_name,
                "state":          "California",
                "published_date": None,
                "published_raw":  "",
                "due_date":       _parse_date(due_raw),
                "due_date_raw":   due_raw,
                "url":            href if href.startswith("http") else portal_url,
                "is_relevant":    _is_relevant(title),
                "search_keyword": "opengov",
                "source":         "OpenGov",
                "summary":        "",
            })

        relevant = sum(1 for b in bids if b["is_relevant"])
        print(f"    ✓ {len(bids)} bids ({relevant} flooring-relevant)")

    except Exception as e:
        print(f"    ✗ {agency_name}: {e}")

    return bids


CHROME_PROFILE_DIR = Path.home() / "Library/Application Support/Google/Chrome"


def _kill_chrome():
    """Kill any running Chrome processes so the profile lock is released."""
    import subprocess
    result = subprocess.run(["pkill", "-x", "Google Chrome"], capture_output=True)
    if result.returncode == 0:
        print("  ✓ Chrome processes stopped")
    # Also remove the SingletonLock if it exists
    lock = CHROME_PROFILE_DIR / "SingletonLock"
    if lock.exists():
        lock.unlink()
        print("  ✓ SingletonLock removed")


async def run_opengov_scraper() -> list[dict]:
    """
    Open Chrome using your real profile (Cloudflare trusts it).
    Kills any running Chrome first to release the profile lock.
    Suppresses --enable-automation so Cloudflare doesn't detect Playwright.

    Flow: Chrome opens → login + solve any Cloudflare once → press Enter → scrapes all portals.
    Pauses per-portal if Cloudflare reappears. Saves cookies when done.
    """
    print("=" * 60)
    print("OPENGOV — Opening browser (your real Chrome profile)")
    print("=" * 60)

    print("\n  Stopping Chrome to release profile lock...")
    _kill_chrome()
    import time; time.sleep(1)

    all_bids = []

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=str(CHROME_PROFILE_DIR),
            channel="chrome",
            headless=False,
            viewport={"width": 1280, "height": 900},
            ignore_default_args=["--enable-automation", "--no-sandbox"],
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = await ctx.new_page()

        print(f"\n→ Chrome is open. In the browser:")
        print(f"  1. Go to:  {OPENGOV_LOGIN_URL}")
        print(f"  2. Log in and solve any I'm-not-a-robot check")
        print(f"  3. Once you can see a portal listing, come back here and press Enter.")
        await asyncio.get_event_loop().run_in_executor(None, input, "→ Press Enter when ready: ")

        # Save cookies so the scheduled scanner can reuse them
        cookies = await ctx.cookies()
        COOKIES_FILE.write_text(json.dumps(cookies, indent=2))
        print(f"  ✓ Cookies saved → {COOKIES_FILE.name}")

        # Scrape each portal — pauses automatically if Cloudflare reappears
        for portal_slug, agency_name in OPENGOV_PORTALS.items():
            print(f"\n  [{agency_name}]")
            portal_bids = await _scrape_portal_listing(page, portal_slug, agency_name)
            all_bids.extend(portal_bids)

        # Refresh cookies after scraping
        cookies = await ctx.cookies()
        COOKIES_FILE.write_text(json.dumps(cookies, indent=2))
        print(f"\n  ✓ Cookies refreshed → {COOKIES_FILE.name}")

        await ctx.close()

    total_relevant = sum(1 for b in all_bids if b["is_relevant"])
    print(f"\n✓ {len(all_bids)} total OpenGov bids · {total_relevant} relevant to flooring")
    print(f"  Cookies saved — scheduled scanner will reuse this session until they expire.")
    return all_bids
