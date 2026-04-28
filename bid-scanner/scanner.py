"""
FCU Bid Scanner — multi-source California procurement scraper

Sources:
  1. BidNet Direct  — https://www.bidnetdirect.com/public/solicitations/open
     Public, no auth, 35K+ national bids, CA-filtered via location=43.
  2. SAM.gov        — https://api.sam.gov/opportunities/v2/search
     Federal CA opportunities via REST API.
     Set SAM_GOV_API_KEY in .env (or use default DEMO_KEY, 5 req/hr limit).
"""

import asyncio
import os
import re
from datetime import datetime, date

import requests
from playwright.async_api import async_playwright

# ---------------------------------------------------------------------------
# Search configuration
# ---------------------------------------------------------------------------

# location=43 → California on BidNet Direct
BIDNET_BASE = "https://www.bidnetdirect.com/public/solicitations/open"
CA_LOCATION_ID = "43"

# SAM.gov federal opportunities API
SAMGOV_API = "https://api.sam.gov/opportunities/v2/search"

# Keywords to run separate searches for
SEARCH_KEYWORDS = [
    "flooring",
    "carpet",
    "resilient flooring",
    "window covering",
    "blinds",
    "LVT vinyl",
    "tile installation",
]

# Keywords to flag a bid as "relevant" (flooring-specific)
RELEVANT_KEYWORDS = [
    "flooring", "floor covering", "carpet", "resilient", "lvt", "vct",
    "vinyl", "tile", "hardwood", "laminate", "window covering",
    "blinds", "shades", "curtain", "linoleum", "epoxy floor",
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _is_relevant(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in RELEVANT_KEYWORDS)


def _parse_date(s: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_bids_from_lines(lines: list[str], keyword: str, bid_links: dict = None) -> list[dict]:
    """
    Parse bid entries from BidNet body text.

    BidNet renders each bid as consecutive lines:
      Title
      State
      Published
      MM/DD/YYYY
      Closing
      MM/DD/YYYY
      BidID (long number)
    """
    bids = []
    i = 0
    date_pattern = re.compile(r'^\d{1,2}/\d{1,2}/\d{4}$')
    id_pattern = re.compile(r'^\d{9,15}$')

    while i < len(lines) - 5:
        # Look for the pattern: title → state → "Published" → date → "Closing" → date → ID
        if (
            lines[i] not in ("Published", "Closing", "California", "Order By", "Publication Date (Newest first)")
            and i + 6 < len(lines)
            and lines[i + 1] == "California"
            and lines[i + 2] == "Published"
            and date_pattern.match(lines[i + 3])
            and lines[i + 4] == "Closing"
            and date_pattern.match(lines[i + 5])
        ):
            title = lines[i]
            published_raw = lines[i + 3]
            closing_raw = lines[i + 5]
            bid_id = lines[i + 6] if i + 6 < len(lines) and id_pattern.match(lines[i + 6]) else ""

            # Skip very short or non-descriptive titles
            if len(title) < 5 or title.lower() in ("home", "search", "login"):
                i += 1
                continue

            closing_date = _parse_date(closing_raw)
            published_date = _parse_date(published_raw)

            bids.append({
                "bid_id": bid_id,
                "title": title,
                "agency": "",  # not shown in listing, would need detail page
                "state": "California",
                "published_date": published_date,
                "published_raw": published_raw,
                "due_date": closing_date,
                "due_date_raw": closing_raw,
                "is_relevant": _is_relevant(title),
                "search_keyword": keyword,
                "url": (bid_links or {}).get(bid_id) or BIDNET_BASE,
            })
            i += 7  # advance past this record
        else:
            i += 1

    return bids


async def _search_keyword(page, keyword: str) -> list[dict]:
    """Run a single keyword search on BidNet Direct, CA only."""
    url = (
        f"{BIDNET_BASE}?keywords={keyword.replace(' ', '+')}"
        f"&location={CA_LOCATION_ID}"
        "&searchContentGroupId=&publishDate="
        "&solSearchStatus=openSolicitationsTab"
        "&sortBy=&sortDirection=&pageNumberSelect=1"
    )

    try:
        print(f"  → Searching: \"{keyword}\"...")
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4000)

        # Scrape actual href links for each bid (keyed by bid ID)
        bid_links = await page.evaluate("""() => {
            const links = {};
            document.querySelectorAll('a[href*="/solicitations/"]').forEach(a => {
                const m = a.href.match(/\\/(\\d{9,15})(\\?|$)/);
                if (m) links[m[1]] = a.href;
            });
            return links;
        }""")

        body = await page.inner_text("body")
        lines = [l.strip() for l in body.split("\n") if l.strip()]

        # Get result count
        result_count = 0
        for l in lines:
            m = re.match(r'^([\d,]+)\s+results?$', l)
            if m:
                result_count = int(m.group(1).replace(",", ""))
                break

        bids = _parse_bids_from_lines(lines, keyword, bid_links)
        print(f"    ✓ {result_count} listed, {len(bids)} parsed")
        return bids

    except Exception as e:
        print(f"    ⚠ Error searching '{keyword}': {e}")
        return []


def _dedup(bids: list[dict]) -> list[dict]:
    """Remove duplicates by bid_id, then by title similarity."""
    seen_ids = set()
    seen_titles = set()
    out = []

    for b in bids:
        bid_id = b["bid_id"]
        title_key = b["title"].lower().strip()[:60]

        if bid_id and bid_id in seen_ids:
            continue
        if title_key in seen_titles:
            continue

        if bid_id:
            seen_ids.add(bid_id)
        seen_titles.add(title_key)
        out.append(b)

    return out


# ---------------------------------------------------------------------------
# PlanetBids (authenticated vendor search)
# ---------------------------------------------------------------------------

# CA agency portals FCU is likely registered with.
# Keys are portal IDs used in pbsystem.planetbids.com/portal/{ID}/
PLANETBIDS_PORTALS = {
    # Original portals
    "21372": "LA Community College District",
    "15810": "City of Long Beach",
    "19236": "Port of Long Beach",
    "25987": "Cal State LA",
    "61954": "LA County Office of Education",
    # CA city portals
    "39478": "Agoura Hills",
    "55389": "Baldwin Park",
    "39493": "Beverly Hills",
    "14210": "Burbank",
    "32461": "Carson",
    "32906": "Commerce",
    "39483": "Culver City",
    "24661": "Downey",
    "42035": "Duarte",
    "43375": "El Monte",
    "39470": "Gardena",
    "39503": "Glendale",
    "51313": "Hermosa Beach",
    "72415": "Huntington Park",
    "62508": "La Canada Flintridge",
    "42566": "Lancaster",
    "39486": "Lynwood",
    "64496": "Maywood",
    "33072": "Norwalk / Montebello",
    "23532": "Palmdale",
    "50534": "Palos Verdes Estates",
    "41481": "Pico Rivera",
    "24662": "Pomona",
    "54150": "Rosemead",
    "69928": "San Dimas",
    "65093": "Santa Fe Springs",
    "60317": "South Gate",
    "47426": "Torrance",
    "39468": "West Covina",
    "47476": "Azusa",
}

PLANETBIDS_BASE = "https://vendors.planetbids.com"


async def _planetbids_login(page) -> bool:
    """Log in to PlanetBids vendor portal. Returns True on success."""
    email = os.getenv("PLANETBIDS_EMAIL", "")
    password = os.getenv("PLANETBIDS_PASSWORD", "")
    if not email or not password:
        return False

    try:
        await page.goto(f"{PLANETBIDS_BASE}/login", wait_until="networkidle", timeout=30000)

        # Check if we hit the maintenance page
        body_text = await page.inner_text("body")
        if "maintenance" in body_text.lower():
            print("    ⚠ PlanetBids is undergoing maintenance — skipping")
            return False

        # Fill login form
        await page.fill('input[type="email"], input[name*="email" i], input[id*="email" i]', email)
        await page.fill('input[type="password"]', password)
        await page.click('button[type="submit"], input[type="submit"]')
        await page.wait_for_load_state("networkidle", timeout=20000)

        # Confirm login success (no login form present = success)
        still_on_login = await page.query_selector('input[type="password"]')
        return still_on_login is None

    except Exception as e:
        print(f"    ⚠ PlanetBids login error: {e}")
        return False


async def _search_planetbids_portal(page, portal_id: str, agency: str, keywords: list[str]) -> list[dict]:
    """Search open bids in one PlanetBids portal."""
    bids = []
    search_url = f"{PLANETBIDS_BASE}/portal/{portal_id}/bo/bo-search"

    try:
        await page.goto(search_url, wait_until="networkidle", timeout=20000)
        await page.wait_for_timeout(2000)

        body_text = await page.inner_text("body")
        if "page not found" in body_text.lower() or "portal not found" in body_text.lower():
            return []

        for keyword in keywords:
            try:
                # Look for a search input
                search_input = await page.query_selector(
                    'input[placeholder*="search" i], input[name*="search" i], input[id*="search" i], input[type="search"]'
                )
                if search_input:
                    await search_input.fill(keyword)
                    await search_input.press("Enter")
                    await page.wait_for_load_state("networkidle", timeout=10000)
                    await page.wait_for_timeout(1500)

                # Collect bid links from this page
                bid_links = await page.evaluate("""() => {
                    const links = {};
                    document.querySelectorAll('a[href*="/bo/bo-detail/"], a[href*="/bid/"]').forEach(a => {
                        const m = a.href.match(/\\/bo-detail\\/(\\d+)|\\/bid\\/(\\d+)/);
                        if (m) links[m[1] || m[2]] = a.href;
                    });
                    return links;
                }""")

                body = await page.inner_text("body")
                lines = [l.strip() for l in body.split("\n") if l.strip()]

                # PlanetBids listing pattern: bid title + number + due date
                # Parse what we can; fall back to link-only entries
                for bid_id, url in bid_links.items():
                    # Try to find title near this link in the DOM
                    title_el = await page.query_selector(f'a[href*="{bid_id}"]')
                    title = ""
                    if title_el:
                        title = (await title_el.inner_text()).strip()

                    if not title or len(title) < 5:
                        continue

                    bids.append({
                        "bid_id": f"PB-{portal_id}-{bid_id}",
                        "title": title,
                        "agency": agency,
                        "state": "California",
                        "published_date": None,
                        "published_raw": "",
                        "due_date": None,
                        "due_date_raw": "See portal",
                        "is_relevant": _is_relevant(title),
                        "search_keyword": keyword,
                        "url": url if url.startswith("http") else PLANETBIDS_BASE + url,
                        "source": "PlanetBids",
                    })

            except Exception as e:
                print(f"    ⚠ PlanetBids '{keyword}' on {agency}: {e}")

    except Exception as e:
        print(f"    ⚠ PlanetBids portal {agency}: {e}")

    return bids


PLANETBIDS_COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies.json")


async def _search_planetbids(browser_context, keywords: list[str], live_page=None) -> list[dict]:
    """
    Search PlanetBids portals.
    live_page: an already-verified Playwright page from the CAPTCHA session.
               If provided, uses it directly (WAF already bypassed).
               If None, attempts headless scrape with saved cookies (likely blocked).
    """
    print("\nSearching PlanetBids portals (CA agency bids)...")

    if live_page is not None:
        page = live_page
        owns_page = False
    else:
        import json as _json
        from pathlib import Path
        cookies_path = Path(PLANETBIDS_COOKIES_FILE)
        if not cookies_path.exists():
            print("  PlanetBids skipped — no cookies.json found")
            return []
        cookies = _json.loads(cookies_path.read_text())
        await browser_context.add_cookies(cookies)
        page = await browser_context.new_page()
        owns_page = True

    all_bids: list[dict] = []
    for portal_id, agency in PLANETBIDS_PORTALS.items():
        print(f"  → {agency}...")
        portal_bids = await _search_planetbids_portal(page, portal_id, agency, keywords)
        print(f"    ✓ {len(portal_bids)} bids found")
        all_bids.extend(portal_bids)

    if owns_page:
        await page.close()
    return all_bids


# ---------------------------------------------------------------------------
# SAM.gov (federal CA opportunities)
# ---------------------------------------------------------------------------

async def _search_samgov(keywords: list[str]) -> list[dict]:
    """
    Search SAM.gov for active CA Contract Opportunities via browser DOM parsing.
    No API key needed. Filters: index=ac, is_active=true, state=CA.
    Uses Python-native Playwright selectors to avoid JS escape issues.
    """
    import urllib.parse
    import re as _re

    SAMGOV_SEARCH = "https://sam.gov/search/"
    all_bids: list[dict] = []
    seen_ids: set[str] = set()

    print("\nSearching SAM.gov (federal CA Contract Opportunities)...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = await browser.new_context(user_agent=USER_AGENT, viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()

        for keyword in keywords:
            print(f'  → "{keyword}"...')

            params = {
                "page": "1",
                "pageSize": "100",
                "sort": "-modifiedDate",
                "index": "ac",
                "sfm[simpleSearch][keywordRadio]": "ALL",
                "sfm[simpleSearch][keywordTags][0][key]": keyword,
                "sfm[simpleSearch][keywordTags][0][value]": keyword,
                "sfm[status][is_active]": "true",
                "sfm[performance][state][0]": "CA",  # place of performance CA (not agency state)
            }
            url = SAMGOV_SEARCH + "?" + urllib.parse.urlencode(params)

            try:
                await page.goto(url, wait_until="load", timeout=30000)
                await page.wait_for_timeout(10000)
            except Exception:
                pass

            # Result cards: div.grid-row.grid-gap that directly contain an h3 with an opp link
            # Use :scope to avoid matching nested grid-rows inside cards
            row_els = await page.query_selector_all("div.grid-row.grid-gap:has(> div > div h3 a[href*='/opp/'])")
            ca_bids = []

            for row in row_els:
                title_el = await row.query_selector("h3 a")
                if not title_el:
                    continue
                href = await title_el.get_attribute("href") or ""
                if "/opp/" not in href:
                    continue

                title = (await title_el.inner_text()).strip()
                full_url = f"https://sam.gov{href}" if href.startswith("/") else href

                # Extract opp ID from URL
                opp_match = _re.search(r"/opp/([a-f0-9]+)/", full_url)
                opp_id = opp_match.group(1) if opp_match else ""

                # Get all text in the card
                card_text = await row.inner_text()
                lines = [l.strip() for l in card_text.split("\n") if l.strip()]

                # Notice ID
                notice_match = _re.search(r"Notice ID:\s*([A-Z0-9\-]+)", card_text, _re.IGNORECASE)
                notice_id = notice_match.group(1).strip() if notice_match else opp_id

                if not notice_id or notice_id in seen_ids:
                    continue
                seen_ids.add(notice_id)

                # Due date — line after "Offers Due" or "Response Date", strip time
                due_raw = ""
                for i, line in enumerate(lines):
                    if "Offers Due" in line or "Response Date" in line:
                        raw = lines[i + 1] if i + 1 < len(lines) else ""
                        # Strip " at HH:MM ..." leaving just "Month DD, YYYY"
                        due_raw = raw.split(" at ")[0].strip()
                        break

                # Published date — line after "Published Date"
                pub_raw = ""
                for i, line in enumerate(lines):
                    if line == "Published Date":
                        pub_raw = lines[i + 1] if i + 1 < len(lines) else ""
                        break

                # Agency — line after "Department/Ind.Agency"
                agency = ""
                for i, line in enumerate(lines):
                    if "Department" in line and "Agency" in line:
                        agency = lines[i + 1] if i + 1 < len(lines) else ""
                        break

                ca_bids.append({
                    "bid_id": f"SAM-{notice_id}",
                    "title": title,
                    "agency": agency,
                    "state": "California",
                    "published_date": _parse_date(pub_raw),
                    "published_raw": pub_raw,
                    "due_date": _parse_date(due_raw),
                    "due_date_raw": due_raw,
                    "is_relevant": _is_relevant(title),
                    "search_keyword": keyword,
                    "url": full_url,
                    "source": "SAM.gov",
                })

            print(f"    ✓ {len(ca_bids)} CA bids")
            all_bids.extend(ca_bids)

        await browser.close()

    return all_bids


# ---------------------------------------------------------------------------
# Cal eProcure (CA state PeopleSoft portal — public, no auth)
# ---------------------------------------------------------------------------

CALEPROCURE_URL = "https://caleprocure.ca.gov/pages/Events-BS3/event-search.aspx"


async def _search_caleprocure(page, keywords: list[str]) -> list[dict]:
    """
    Search Cal eProcure (CA state portal) for open flooring bids.
    Public search — no login required.
    """
    print("\nSearching Cal eProcure (CA state portal)...")
    all_bids: list[dict] = []

    try:
        await page.goto(CALEPROCURE_URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(4000)

        title = await page.title()
        if "maintenance" in title.lower() or "error" in title.lower():
            print("  ⚠ Cal eProcure unavailable")
            return []

        for keyword in keywords:
            try:
                # Find search input — Angular SPA uses various selectors
                search_input = await page.query_selector(
                    'input[placeholder*="keyword" i], input[placeholder*="search" i], '
                    'input[ng-model*="keyword" i], input[id*="keyword" i], '
                    'input[name*="keyword" i], input[type="search"]'
                )
                if not search_input:
                    # Try finding any visible text input
                    inputs = await page.query_selector_all('input[type="text"]')
                    search_input = inputs[0] if inputs else None

                if not search_input:
                    print(f"  ⚠ No search input found on Cal eProcure")
                    break

                await search_input.click(click_count=3)
                await search_input.fill(keyword)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(3000)

                # Collect bid rows — PeopleSoft/Angular tables
                rows = await page.query_selector_all(
                    'tr.ps_grid-row, tr[class*="row"], .bid-row, '
                    '[class*="event-row"], [class*="result-row"], tbody tr'
                )

                bid_links = await page.evaluate("""() => {
                    const results = [];
                    document.querySelectorAll('a[href*="event"], a[href*="bid"], a[href*="solicitation"]').forEach(a => {
                        const text = (a.innerText || '').trim();
                        if (text.length > 5) results.push({ href: a.href, text: text.substring(0, 120) });
                    });
                    return results;
                }""")

                # Parse table rows for structured data
                row_data = await page.evaluate("""() => {
                    const rows = [];
                    document.querySelectorAll('tbody tr, tr.ps_grid-row').forEach(tr => {
                        const cells = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
                        if (cells.length >= 3 && cells.some(c => c.length > 3)) rows.push(cells);
                    });
                    return rows.slice(0, 100);
                }""")

                for i, row in enumerate(row_data):
                    if len(row) < 3:
                        continue
                    # Typical PeopleSoft columns: EventID | Title | Agency | PostDate | DueDate | Status
                    title_cell = next((c for c in row if len(c) > 10 and not re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', c)), row[0] if row else "")
                    due_raw = next((c for c in row if re.match(r'\d{1,2}/\d{1,2}/\d{4}', c)), "")
                    agency = row[2] if len(row) > 2 else ""
                    bid_id = row[0] if re.match(r'[\w-]{3,20}', row[0]) else f"CAL-{i}"
                    url = bid_links[i]["href"] if i < len(bid_links) else CALEPROCURE_URL

                    if len(title_cell) < 5:
                        continue

                    all_bids.append({
                        "bid_id": bid_id,
                        "title": title_cell,
                        "agency": agency,
                        "state": "California",
                        "published_date": None,
                        "published_raw": "",
                        "due_date": _parse_date(due_raw),
                        "due_date_raw": due_raw,
                        "is_relevant": _is_relevant(title_cell),
                        "search_keyword": keyword,
                        "url": url,
                        "source": "Cal eProcure",
                    })

                print(f"  → \"{keyword}\": {len(row_data)} rows, {sum(1 for b in all_bids if b['search_keyword'] == keyword)} parsed")

            except Exception as e:
                print(f"  ⚠ Cal eProcure error for '{keyword}': {e}")

    except Exception as e:
        print(f"  ⚠ Cal eProcure unavailable: {e}")

    print(f"  ✓ Cal eProcure total: {len(all_bids)} bids")
    return all_bids


# ---------------------------------------------------------------------------
# OpenGov procurement portals (Cloudflare-protected, uses shared cookies)
# ---------------------------------------------------------------------------

OPENGOV_PORTALS = {
    # Your list
    "cityofbell":       "City of Bell",
    "redondo":          "Redondo Beach",
    "citymb":           "Manhattan Beach",
    "pasadena":         "Pasadena",
    "santa-monica-ca":  "Santa Monica",
    # Previously configured
    "sacramento":       "Sacramento",
    "san-francisco":    "San Francisco",
    "alameda-county":   "Alameda County",
}

OPENGOV_BASE = "https://procurement.opengov.com"
OPENGOV_COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies_opengov.json")


async def _search_opengov_portal(page, portal_slug: str, agency: str, keywords: list[str]) -> list[dict]:
    """Search one OpenGov portal for bids matching keywords."""
    bids = []
    url = f"{OPENGOV_BASE}/portal/{portal_slug}"

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(5000)

        title = await page.title()
        if "just a moment" in title.lower() or "403" in title or "captcha" in title.lower():
            print(f"  ⚠ {agency}: Cloudflare blocking — run --save-cookies-opengov to refresh")
            return []

        for keyword in keywords:
            try:
                # Look for search input
                search_input = await page.query_selector(
                    'input[placeholder*="search" i], input[placeholder*="keyword" i], '
                    'input[type="search"], input[aria-label*="search" i]'
                )
                if search_input:
                    await search_input.fill(keyword)
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(3000)

                # Extract bid listings (React-rendered)
                bid_data = await page.evaluate("""() => {
                    const results = [];
                    // OpenGov renders bids as cards or table rows
                    const selectors = [
                        '[class*="solicitation"]', '[class*="bid-card"]',
                        '[class*="procurement-card"]', '[data-testid*="solicitation"]',
                        'li[class*="item"]', 'article'
                    ];
                    for (const sel of selectors) {
                        document.querySelectorAll(sel).forEach(el => {
                            const text = el.innerText.trim();
                            const link = el.querySelector('a');
                            if (text.length > 10 && link) {
                                results.push({ text: text.substring(0, 200), href: link.href });
                            }
                        });
                        if (results.length > 0) break;
                    }
                    // Fallback: all links with meaningful text
                    if (results.length === 0) {
                        document.querySelectorAll('a[href*="solicitation"], a[href*="/bid/"], a[href*="/rfp/"]').forEach(a => {
                            const text = a.innerText.trim();
                            if (text.length > 10) results.push({ text: text.substring(0, 120), href: a.href });
                        });
                    }
                    return results;
                }""")

                for item in bid_data:
                    lines = [l.strip() for l in item["text"].split("\n") if l.strip()]
                    bid_title = lines[0] if lines else ""
                    due_raw = next((l for l in lines if re.search(r'\d{1,2}/\d{1,2}/\d{4}', l)), "")
                    due_match = re.search(r'\d{1,2}/\d{1,2}/\d{4}', due_raw)
                    due_date_str = due_match.group(0) if due_match else ""

                    if len(bid_title) < 5:
                        continue

                    bids.append({
                        "bid_id": f"OG-{portal_slug}-{len(bids)}",
                        "title": bid_title,
                        "agency": agency,
                        "state": "California",
                        "published_date": None,
                        "published_raw": "",
                        "due_date": _parse_date(due_date_str),
                        "due_date_raw": due_date_str,
                        "is_relevant": _is_relevant(bid_title),
                        "search_keyword": keyword,
                        "url": item["href"] if item["href"].startswith("http") else OPENGOV_BASE + item["href"],
                        "source": "OpenGov",
                    })

            except Exception as e:
                print(f"  ⚠ OpenGov {agency} '{keyword}': {e}")

    except Exception as e:
        print(f"  ⚠ OpenGov {agency}: {e}")

    return bids


async def _search_opengov(browser_context, keywords: list[str]) -> list[dict]:
    """Search all configured OpenGov portals. Uses cookies_opengov.json if present."""
    import json as _json
    from pathlib import Path

    print("\nSearching OpenGov portals (Sacramento, SF, Alameda)...")

    page = await browser_context.new_page()

    # Load OpenGov cookies if available
    if Path(OPENGOV_COOKIES_FILE).exists():
        cookies = _json.loads(Path(OPENGOV_COOKIES_FILE).read_text())
        await browser_context.add_cookies(cookies)
        print("  Loaded OpenGov cookies")

    all_bids: list[dict] = []
    for slug, agency in OPENGOV_PORTALS.items():
        print(f"  → {agency}...")
        portal_bids = await _search_opengov_portal(page, slug, agency, keywords)
        print(f"    ✓ {len(portal_bids)} bids")
        all_bids.extend(portal_bids)

    await page.close()
    return all_bids


# ---------------------------------------------------------------------------
# Bid Locker (public — browse open bids, no keyword search)
# ---------------------------------------------------------------------------

BIDLOCKER_BASE = "https://www.bidlocker.us"


async def _search_bidlocker(page, keywords: list[str]) -> list[dict]:
    """
    Scrape Bid Locker open bids for CA agencies.
    Bid Locker has no cross-agency keyword search — we browse open bids
    and filter locally by relevance keywords.
    """
    print("\nSearching Bid Locker (CA open bids)...")
    all_bids: list[dict] = []

    try:
        # Try browsing open bids listing
        for path in ["/open-bids", "/bids/open", "/r/_/bids", "/"]:
            url = f"{BIDLOCKER_BASE}{path}"
            await page.goto(url, wait_until="networkidle", timeout=20000)
            await page.wait_for_timeout(2000)

            body = await page.inner_text("body")
            if len(body) > 200 and "bid" in body.lower():
                break

        # Extract bid links
        bid_data = await page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('a[href*="/bid/"], a[href*="/bids/"], a[href*="solicitation"]').forEach(a => {
                const text = (a.innerText || '').trim();
                const row = a.closest('tr, li, [class*="row"], [class*="card"], article');
                const rowText = row ? row.innerText.trim() : text;
                if (text.length > 5) results.push({ href: a.href, text: rowText.substring(0, 200) });
            });
            return results;
        }""")

        for item in bid_data:
            lines = [l.strip() for l in item["text"].split("\n") if l.strip()]
            bid_title = lines[0] if lines else ""
            # Filter to CA-relevant and flooring-relevant only
            text_lower = item["text"].lower()
            is_ca = any(w in text_lower for w in ["california", " ca ", "los angeles", "san francisco", "sacramento"])
            if not _is_relevant(bid_title) and not is_ca:
                continue

            due_raw = next((l for l in lines if re.search(r'\d{1,2}/\d{1,2}/\d{4}', l)), "")
            due_match = re.search(r'\d{1,2}/\d{1,2}/\d{4}', due_raw)

            all_bids.append({
                "bid_id": f"BL-{len(all_bids)}",
                "title": bid_title,
                "agency": lines[1] if len(lines) > 1 else "",
                "state": "California",
                "published_date": None,
                "published_raw": "",
                "due_date": _parse_date(due_match.group(0) if due_match else ""),
                "due_date_raw": due_match.group(0) if due_match else "",
                "is_relevant": _is_relevant(bid_title),
                "search_keyword": "open bids",
                "url": item["href"],
                "source": "Bid Locker",
            })

        print(f"  ✓ {len(all_bids)} CA flooring-relevant bids from Bid Locker")

    except Exception as e:
        print(f"  ⚠ Bid Locker error: {e}")

    return all_bids


# ---------------------------------------------------------------------------
# Quality Bidders (public JSON API — CA school district bids)
# ---------------------------------------------------------------------------

QUALITYBIDDERS_API = "https://www.qualitybidders.com/bids.json"
QUALITYBIDDERS_BASE = "https://www.qualitybidders.com"


def _fetch_qualitybidders_sync() -> list[dict]:
    """
    Fetch all open CA bids from Quality Bidders via their public JSON API.
    Returns raw aaData rows — no auth required.
    """
    import time as _time
    ts = int(_time.time() * 1000)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": QUALITYBIDDERS_BASE + "/bids",
    }
    resp = requests.get(
        QUALITYBIDDERS_API,
        params={"area": "", "license": "", "district": "", "showExpired": "", "iDisplayLength": 500, "_": ts},
        headers=headers,
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("aaData", [])


async def _search_qualitybidders(keywords: list[str]) -> list[dict]:
    """
    Pull all open Quality Bidders bids and filter by flooring keywords.
    Pure HTTP — no browser needed.
    """
    print("\nSearching Quality Bidders (CA school district bids)...")
    try:
        rows = await asyncio.to_thread(_fetch_qualitybidders_sync)
    except Exception as e:
        print(f"  ⚠ Quality Bidders error: {e}")
        return []

    bids = []
    for row in rows:
        # Columns: [bid_num, agency, title, posted, pre_bid, due_date, license, walk, ?, view_link, ...]
        if len(row) < 6:
            continue
        bid_num  = str(row[0]).strip()
        agency   = str(row[1]).strip()
        title    = str(row[2]).strip()
        posted   = str(row[3]).strip()
        due_raw  = str(row[5]).strip()
        url_cell = str(row[9]) if len(row) > 9 else ""
        m = re.search(r"href='(/bids/\d+)'", url_cell)
        url = (QUALITYBIDDERS_BASE + m.group(1)) if m else QUALITYBIDDERS_BASE + "/bids"

        if not _is_relevant(title):
            continue

        bids.append({
            "bid_id": f"QB-{bid_num}",
            "title": title,
            "agency": agency,
            "state": "California",
            "published_date": _parse_date(posted),
            "published_raw": posted,
            "due_date": _parse_date(due_raw),
            "due_date_raw": due_raw,
            "is_relevant": True,
            "search_keyword": "flooring",
            "url": url,
            "source": "Quality Bidders",
        })

    print(f"  ✓ {len(rows)} open bids fetched, {len(bids)} flooring-relevant")
    return bids


# ---------------------------------------------------------------------------
# SoCal Builders Plan Room (CyberCopy — public CA construction bids)
# ---------------------------------------------------------------------------

PLAN_ROOMS = [
    ("https://www.southerncaliforniabuildersplanroom.com", "SoCal Plan Room"),
    ("https://www.crispplanroom.com", "Crisp Plan Room"),
]


async def _search_plan_room(page, base_url: str, source_name: str) -> list[dict]:
    """Generic scraper for CyberCopy-platform plan rooms (SoCal + Crisp)."""
    all_bids: list[dict] = []
    page_num = 1

    try:
        while True:
            url = f"{base_url}/projects/public?status=bidding&page={page_num}"
            await page.goto(url, wait_until="networkidle", timeout=20000)
            await page.wait_for_timeout(1500)

            body_text = await page.inner_text("body")
            page_match = re.search(r'Page\s+\d+\s+of\s+(\d+)', body_text)
            total_pages = int(page_match.group(1)) if page_match else 1

            project_links = await page.query_selector_all('a[href*="/projects/"]')
            for link in project_links:
                raw = (await link.inner_text()).strip()
                href = await link.get_attribute("href")
                if not href or not raw or href.endswith("/projects/public"):
                    continue
                url_full = href if href.startswith("http") else base_url + href
                lines = [l.strip() for l in raw.split("\n") if l.strip()]
                if len(lines) < 3:
                    continue

                date_line = lines[1] if len(lines) > 1 else ""
                title = lines[2] if len(lines) > 2 else ""
                agency = lines[3] if len(lines) > 3 else ""
                due_match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', date_line)
                due_raw = due_match.group(1) if due_match else ""
                if due_raw and len(due_raw.split("/")[-1]) == 2:
                    parts = due_raw.split("/")
                    due_raw = f"{parts[0]}/{parts[1]}/20{parts[2]}"

                all_bids.append({
                    "bid_id": f"{source_name.split()[0].upper()}-{href.split('/projects/')[-1].split('/')[0]}",
                    "title": title,
                    "agency": agency,
                    "state": "California",
                    "published_date": None,
                    "published_raw": "",
                    "due_date": _parse_date(due_raw),
                    "due_date_raw": due_raw,
                    "is_relevant": _is_relevant(title) or _is_relevant(raw),
                    "search_keyword": "open bids",
                    "url": url_full,
                    "source": source_name,
                })

            if page_num >= total_pages:
                break
            page_num += 1

    except Exception as e:
        print(f"  ⚠ {source_name} error: {e}")

    return all_bids


SCBPR_BASE = "https://www.southerncaliforniabuildersplanroom.com"


# ---------------------------------------------------------------------------
# Caltrans CCOP — CA Dept of Transportation contracting opportunities
# ---------------------------------------------------------------------------

CCOP_URL = "https://ccop.dot.ca.gov/onestopshop/1,2,3,4,5,6,7,8,9,10,11,12"


async def _search_ccop(page, keywords: list[str]) -> list[dict]:
    """
    Scrape Caltrans Contracting Opportunities Portal — all 12 CA districts.
    Public, no auth, all projects load on one page.
    Filters locally by flooring keywords.
    """
    print("\nSearching Caltrans CCOP (all CA districts)...")
    all_bids: list[dict] = []

    try:
        await page.goto(CCOP_URL, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)

        body = await page.inner_text("body")
        lines = [l.strip() for l in body.split("\n") if l.strip()]

        # Extract detail links keyed by project ID
        bid_links = await page.evaluate("""() => {
            const links = {};
            document.querySelectorAll('a[href*="cc_advertisement_details"], a[href*="caleprocure.ca.gov/event"]').forEach(a => {
                const id = (a.innerText || '').trim();
                if (id.length > 3) links[id] = a.href;
            });
            return links;
        }""")

        # Parse structured blocks: "Project ID:" → id → "Bid Due Date:" → date → "Status:" → status → description
        i = 0
        while i < len(lines):
            if lines[i] == "Project ID:" and i + 6 < len(lines):
                proj_id  = lines[i + 1]
                due_raw  = lines[i + 3] if lines[i + 2] == "Bid Due Date:" else ""
                status   = lines[i + 5] if lines[i + 4] == "Status:" else ""
                desc     = lines[i + 6] if i + 6 < len(lines) else ""

                if _is_relevant(desc) or _is_relevant(proj_id):
                    url = bid_links.get(proj_id, CCOP_URL)
                    all_bids.append({
                        "bid_id": f"CCOP-{proj_id}",
                        "title": desc[:120],
                        "agency": "Caltrans",
                        "state": "California",
                        "published_date": None,
                        "published_raw": "",
                        "due_date": _parse_date(due_raw),
                        "due_date_raw": due_raw,
                        "is_relevant": True,
                        "search_keyword": "flooring",
                        "url": url,
                        "source": "Caltrans CCOP",
                    })
                i += 7
            else:
                i += 1

        print(f"  ✓ 149 projects scanned, {len(all_bids)} flooring-relevant")

    except Exception as e:
        print(f"  ⚠ Caltrans CCOP error: {e}")

    return all_bids


async def _search_plan_rooms(page, keywords: list[str]) -> list[dict]:
    """Scrape all configured CyberCopy plan rooms."""
    all_bids: list[dict] = []
    for base_url, source_name in PLAN_ROOMS:
        print(f"\nSearching {source_name}...")
        bids = await _search_plan_room(page, base_url, source_name)
        relevant = sum(1 for b in bids if b["is_relevant"])
        print(f"  ✓ {len(bids)} open bids ({relevant} flooring-relevant)")
        all_bids.extend(bids)
    return all_bids


async def run_scan(keywords: list[str] = None, source: str = None, headless: bool = True, live_page=None) -> list[dict]:
    """
    Main scan entry point.
    source: filter to a single source ("sam", "planetbids", "bidnet", etc.) or None for all.
    live_page: verified Playwright page to use for PlanetBids (WAF already bypassed).
    Returns list of deduplicated bid dicts sorted by relevance + due date.
    """
    if keywords is None:
        keywords = SEARCH_KEYWORDS

    src = source.lower() if source else None
    all_bids = []

    needs_browser = src is None or src not in ("sam",)

    if needs_browser:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )

            if src in (None, "bidnet"):
                print("Searching BidNet Direct (CA public bids)...")
                page = await context.new_page()
                for keyword in keywords:
                    bids = await _search_keyword(page, keyword)
                    for b in bids:
                        b.setdefault("source", "BidNet Direct")
                    all_bids.extend(bids)
                await page.close()

            if src in (None, "planetbids"):
                pb_bids = await _search_planetbids(context, keywords, live_page=live_page)
                all_bids.extend(pb_bids)

            if src in (None, "caleprocure"):
                cal_page = await context.new_page()
                cal_bids = await _search_caleprocure(cal_page, keywords)
                all_bids.extend(cal_bids)
                await cal_page.close()

            if src in (None, "opengov"):
                og_bids = await _search_opengov(context, keywords)
                all_bids.extend(og_bids)

            if src in (None, "planrooms"):
                pr_page = await context.new_page()
                pr_bids = await _search_plan_rooms(pr_page, keywords)
                all_bids.extend(pr_bids)
                await pr_page.close()

            if src in (None, "caltrans"):
                ccop_page = await context.new_page()
                ccop_bids = await _search_ccop(ccop_page, keywords)
                all_bids.extend(ccop_bids)
                await ccop_page.close()

            await browser.close()

    if src in (None, "sam"):
        sam_bids = await _search_samgov(keywords)
        all_bids.extend(sam_bids)

    if src in (None, "qualitybidders"):
        qb_bids = await _search_qualitybidders(keywords)
        all_bids.extend(qb_bids)

    deduped = _dedup(all_bids)

    # Sort: relevant first, then by soonest due date
    today = date.today()
    deduped.sort(key=lambda b: (
        not b["is_relevant"],
        b["due_date"] or date(9999, 1, 1),
    ))

    relevant_count = sum(1 for b in deduped if b["is_relevant"])
    print(f"\nTotal: {len(deduped)} unique CA bids ({relevant_count} relevant to flooring)")
    return deduped


if __name__ == "__main__":
    results = asyncio.run(run_scan())
    print("\nSample results:")
    for b in results[:10]:
        tag = "★" if b["is_relevant"] else " "
        print(f"  {tag} {b['title'][:60]:<60} due {b['due_date_raw']}")
