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
import sys
import time
from datetime import datetime, date

import requests
from bs4 import BeautifulSoup
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

# Keywords to flag a bid as "relevant" (flooring-specific) — fast first pass
RELEVANT_KEYWORDS = [
    "flooring", "floor covering", "floor repair", "floor replacement",
    "floor install", "install floor", "new floor", "replace floor",
    "carpet", "resilient", "lvt", "vct", "vinyl tile", "vinyl plank",
    "hardwood", "laminate", "window covering", "blinds", "shades",
    "curtain", "linoleum", "epoxy floor", "rubber floor",
    "ceramic tile", "porcelain tile", "tile installation", "tile replacement",
]

# Materials-/supply-only solicitations — FCU is an installer, not a distributor.
# These buy product with no installation labor, so they're never a fit even when
# the title mentions flooring. Checked against title + description.
MATERIALS_ONLY_PATTERNS = [
    "materials only", "material only", "materials-only", "material-only",
    "furnish only", "furnish and deliver", "furnish & deliver",
    "supply only", "supply and deliver", "supply & deliver", "delivery only",
    "purchase and delivery", "no installation", "installation not included",
    "installation by others", "installation by owner", "material purchase",
    "carpet purchase", "purchase of carpet", "purchase of flooring",
    "product only", "supply of carpet", "supply of flooring", "no labor",
]

# Service contracts, not installation — cleaning, maintenance, pest, janitorial.
# The word "carpet" or "floor" makes these look relevant, but FCU installs floor
# covering; it doesn't hold recurring service contracts.
SERVICE_ONLY_PATTERNS = [
    "carpet cleaning", "floor cleaning", "cleaning service", "cleaning contract",
    "janitorial", "custodial", "housekeeping", "pest control", "extermination",
    "fumigation", "strip and wax", "stripping and waxing", "strip & wax",
    "floor waxing", "floor buffing", "carpet care", "carpet extraction",
    "steam cleaning", "carpet shampoo", "shampoo carpet", "spot cleaning",
    "grounds maintenance", "landscape maintenance", "window washing",
]

# If any of these also appear, it's an install job after all — keep it.
# Note: these are all *affirmative* install phrases; negated forms like
# "no installation" / "installation not included" stay in MATERIALS_ONLY_PATTERNS
# and never appear here, so they aren't accidentally rescued.
_INSTALL_OVERRIDE = [
    "furnish and install", "furnish & install", "furnish/install",
    "supply and install", "supply & install", "labor and material",
    "labor and materials", "turnkey", "install and furnish",
    "and installation", "& installation", "and install ", "install and",
    "including installation", "installation included", "installation of ",
    "installation for ", "install carpet", "install flooring", "installed by",
]

# Construction bids that didn't match keywords → Ollama second-pass
# (set OLLAMA_RELEVANCE=true in .env to enable)
_CONSTRUCTION_TRIGGERS = [
    "renovation", "remodel", "rehabilitation", "modernization", "retrofit",
    "improvement", "upgrade", "repair", "replacement", "construction",
    "classroom", "restroom", "locker room", "gymnasium", "gym ",
    "dormitory", "barracks", "office space", "community center",
    "hospital", "clinic", "library", "school", "university", "college",
    "facility", "building interior", "interior ",
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _claude_relevance(title: str, description: str = "") -> bool:
    """
    Ask Claude Haiku whether flooring is the PRIMARY scope of this bid.
    Stricter than the old Ollama check — rejects bids where flooring is
    incidental (e.g. aquatic center with tile floors, street improvements).
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return False
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        context = f'Title: "{title}"'
        if description:
            context += f'\nDescription: "{description[:600]}"'
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5,
            temperature=0,
            messages=[{
                "role": "user",
                "content": (
                    "You are filtering bids for a commercial flooring contractor "
                    "(Floor Covering Unlimited). They ONLY bid on projects where "
                    "flooring installation (carpet, vinyl, LVT, VCT, tile, hardwood, "
                    "rubber, epoxy, window coverings, blinds) is the PRIMARY and "
                    "dominant scope of work — not a minor component of a larger project.\n\n"
                    "Examples that should be YES: 'Flooring Replacement at City Hall', "
                    "'Carpet Installation Gymnasium', 'VCT Tile Replacement School'.\n"
                    "Examples that should be NO: 'Aquatic Center Improvements', "
                    "'Street Improvements', 'Restroom Rehabilitation', "
                    "'Building Renovation' (flooring is incidental), "
                    "'Furnish and Deliver Carpet Tile', 'Flooring Materials — Supply Only' "
                    "(product purchase, no installation labor), "
                    "'Carpet Cleaning Services', 'Janitorial & Pest Control' "
                    "(recurring service, not installation).\n\n"
                    f"{context}\n\n"
                    "Is commercial flooring the PRIMARY scope? Answer YES or NO only."
                ),
            }],
        )
        return msg.content[0].text.strip().upper().startswith("YES")
    except Exception:
        return False


def _is_materials_only(title: str, description: str = "") -> bool:
    """True if the solicitation is for supplying flooring product with no
    installation labor. Overridden when the text also names install/turnkey work."""
    blob = f"{title} {description}".lower()
    if not any(p in blob for p in MATERIALS_ONLY_PATTERNS):
        return False
    return not any(p in blob for p in _INSTALL_OVERRIDE)


# Any of these means real flooring work is in scope — not just a service run.
_SERVICE_OVERRIDE = _INSTALL_OVERRIDE + [
    "install", "installation", "replace", "replacement", "demolition",
    "new carpet", "new flooring", "renovation", "tenant improvement",
]


def _is_service_only(title: str, description: str = "") -> bool:
    """True if the solicitation is a cleaning / maintenance / pest / janitorial
    service contract rather than a flooring installation."""
    blob = f"{title} {description}".lower()
    if not any(p in blob for p in SERVICE_ONLY_PATTERNS):
        return False
    return not any(p in blob for p in _SERVICE_OVERRIDE)


def _is_relevant(title: str, description: str = "") -> bool:
    # Materials-only or service-only jobs are never a fit — bail before any
    # keyword match
    if _is_materials_only(title, description) or _is_service_only(title, description):
        return False
    t = title.lower()
    # Fast keyword match — unambiguous flooring titles pass immediately
    if any(kw in t for kw in RELEVANT_KEYWORDS):
        return True
    # Claude second pass for construction-adjacent titles
    if any(kw in t for kw in _CONSTRUCTION_TRIGGERS):
        return _claude_relevance(title, description)
    return False


def _safe_bid_id(bid_id: str) -> str:
    """bid_id doubles as a filesystem path component downstream — parser.py
    builds output/specs/<bid_id>.pdf. Quality Bidders / Caltrans embed '/' and
    spaces, which silently broke document download. Mirrors parser._safe_id."""
    return re.sub(r"[^\w.\-]", "_", (bid_id or "").strip()) or "unknown"


def _parse_date(s: str) -> date | None:
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%b %d, %Y", "%B %d, %Y"):
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
# {portal_id: (agency name, county)}. County is stamped straight onto every
# bid from that portal so the spec §1 geo gate never has to guess for a
# portal-based source.
PLANETBIDS_PORTALS = {
    # --- Los Angeles County ---
    "21372": ("LA Community College District", "Los Angeles"),
    "19236": ("Port of Long Beach", "Los Angeles"),
    "25987": ("Cal State LA", "Los Angeles"),
    "61954": ("LA County Office of Education", "Los Angeles"),
    "39478": ("Agoura Hills", "Los Angeles"),
    "55389": ("Baldwin Park", "Los Angeles"),
    "39493": ("Beverly Hills", "Los Angeles"),
    "14210": ("Burbank", "Los Angeles"),
    "32461": ("Carson", "Los Angeles"),
    "32906": ("Commerce", "Los Angeles"),
    "39483": ("Culver City", "Los Angeles"),
    "24661": ("Downey", "Los Angeles"),
    "42035": ("Duarte", "Los Angeles"),
    "43375": ("El Monte", "Los Angeles"),
    "39470": ("Gardena", "Los Angeles"),
    "39503": ("Glendale", "Los Angeles"),
    "51313": ("Hermosa Beach", "Los Angeles"),
    "72415": ("Huntington Park", "Los Angeles"),
    "62508": ("La Canada Flintridge", "Los Angeles"),
    "42566": ("Lancaster", "Los Angeles"),
    "39486": ("Lynwood", "Los Angeles"),
    "64496": ("Maywood", "Los Angeles"),
    "33072": ("Norwalk / Montebello", "Los Angeles"),
    "23532": ("Palmdale", "Los Angeles"),
    "50534": ("Palos Verdes Estates", "Los Angeles"),
    "41481": ("Pico Rivera", "Los Angeles"),
    "24662": ("Pomona", "Los Angeles"),
    "54150": ("Rosemead", "Los Angeles"),
    "69928": ("San Dimas", "Los Angeles"),
    "65093": ("Santa Fe Springs", "Los Angeles"),
    "60317": ("South Gate", "Los Angeles"),
    "47426": ("Torrance", "Los Angeles"),
    "39468": ("West Covina", "Los Angeles"),
    "47476": ("Azusa", "Los Angeles"),
    "15810": ("City of Long Beach", "Los Angeles"),   # verified 2026-08
    # --- Orange County ---
    "20137": ("City of Santa Ana", "Orange"),         # verified 2026-08
    "14424": ("City of Anaheim (legacy)", "Orange"),  # verified 2026-08 — moved to OpenGov Dec 2024
    # --- San Diego County ---
    "17950": ("City of San Diego", "San Diego"),      # verified 2026-08
    # --- Ventura County ---
    # (none verified yet — see ROADMAP "PlanetBids portal expansion")
}

# Portal IDs to skip entirely — chronically blocked / broken tenants that only
# ever cost CAPTCHA solves and leave `--resume` stuck in a loop. They are left
# out of both full and resume scans (no "pending"/"blocked" entry is written, so
# resume treats the run as complete). Remove an ID here to bring a portal back.
PLANETBIDS_SKIP = {
    "15810",   # City of Long Beach — always bounces to its own /2001 challenge
}

PLANETBIDS_BASE = "https://vendors.planetbids.com"


def _scannable_portals() -> dict:
    """PLANETBIDS_PORTALS minus the PLANETBIDS_SKIP list."""
    return {pid: v for pid, v in PLANETBIDS_PORTALS.items() if pid not in PLANETBIDS_SKIP}


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


# Consecutive blocked portals after which we assume the whole browser session
# is WAF-poisoned (every portal serves a blank page) and stop early. The
# untried portals stay "pending" in the manifest for `--resume`.
PLANETBIDS_BLOCK_STREAK_LIMIT = 4

# Max times per run we'll pause and ask a human to clear a per-portal WAF
# challenge (the /2001 "Human Verification" page).
PLANETBIDS_MAX_RESOLVES = 3


def planetbids_scan_plan(resume: bool = False):
    """
    Work out which portals the next PlanetBids scan should hit, and prepare the
    run manifest.

      full run  -> fresh manifest, every portal.
      resume    -> existing manifest, only the unfinished portals. Falls back to
                   a full run if the manifest is missing or older than 48h.

    Returns (manifest, [(portal_id, agency, county), ...]). The portal list is
    empty only when a resume finds nothing left to do. Prints a one-line status.
    Callers that open the browser use plan[0] to decide which portal to land the
    CAPTCHA solve on — each PlanetBids tenant runs its own WAF challenge.
    """
    import pb_state

    manifest = pb_state.load() if resume else None
    if resume:
        if manifest is None:
            print("  ⚠ No previous run to resume — doing a full scan.")
            resume = False
        elif pb_state.is_stale(manifest):
            print(f"  ⚠ Last run started {manifest.get('run_started')} — too old to "
                  f"resume. Doing a full scan.")
            resume = False

    if resume:
        todo = set(pb_state.unfinished_portal_ids(manifest)) - PLANETBIDS_SKIP
        if not todo:
            print("  ✓ Nothing to resume — every portal is ok/empty already.")
            return manifest, []
        print(f"  Resuming {len(todo)} unfinished portal(s) from run "
              f"started {manifest.get('run_started')}.")
        portals = [(pid, a, c) for pid, (a, c) in _scannable_portals().items() if pid in todo]
    else:
        manifest = pb_state.new_manifest(_scannable_portals())
        portals = [(pid, a, c) for pid, (a, c) in _scannable_portals().items()]

    manifest["run_finished"] = None
    pb_state.save(manifest)
    return manifest, portals


def _looks_like_waf_challenge(url: str, body: str) -> bool:
    """True when a PlanetBids navigation landed on the AWS WAF challenge page."""
    u, b = (url or "").lower(), (body or "").lower()
    return (
        "/2001" in u
        or "human verification" in b
        or "awswafcookiedomainlist" in b
        or "gokuprops" in b
        or len(b.strip()) < 200
    )


async def _search_planetbids(browser_context, keywords: list[str], live_page=None,
                             resume: bool = False, plan=None) -> list[dict]:
    """
    Navigate to each PlanetBids portal and capture the /papi/bids JSON response
    from the browser's own request.

    Why navigate instead of calling the API directly:
      - The /papi/bids endpoint requires custom headers (em-version, company-id,
        visit-id, etc.) that are set by the page's JS — not easily replicated.
      - Navigating lets the browser handle all headers and WAF cookies automatically.
      - The initial CAPTCHA solve happens on the FIRST portal we'll scrape (see
        planetbids_scan_plan). Its aws-waf-token then covers most other portals,
        but some tenants (e.g. City of Long Beach) throw their own /2001 challenge
        — those pause for a manual solve, up to PLANETBIDS_MAX_RESOLVES times.

    Every portal's outcome (ok / empty / blocked / error / pending) is written to
    output/planetbids_state.json via pb_state. When resume=True, only portals left
    unfinished by the previous run are re-scraped. See pb_state.py.
    """
    from urllib.parse import urlparse, parse_qs
    import pb_state

    print("\nSearching PlanetBids portals (CA agency bids)...")

    manifest, portals = plan if plan is not None else planetbids_scan_plan(resume)
    if not portals:
        return []

    page = live_page
    kw_lower = [k.lower() for k in keywords]
    skip_stages = {"closed", "canceled", "cancelled", "awarded", "rejected"}
    all_bids: list[dict] = []
    block_streak = 0
    stopped_early = False

    resolves_left = PLANETBIDS_MAX_RESOLVES
    interactive = sys.stdin.isatty()

    async def _fetch_portal(pid):
        """One navigate + /papi/bids capture. Returns (outcome, records) where
        outcome is ok | challenge | timeout | error."""
        url = f"{PLANETBIDS_BASE}/portal/{pid}/bo/bo-search"
        loop = asyncio.get_event_loop()
        captured: asyncio.Future = loop.create_future()

        async def on_response(response, cid=pid):
            if "/papi/bids" in response.url and not captured.done():
                params = parse_qs(urlparse(response.url).query)
                if params.get("cid", [""])[0] == cid:
                    try:
                        captured.set_result(await response.json())
                    except Exception as exc:
                        if not captured.done():
                            captured.set_exception(exc)

        page.on("response", on_response)
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            data = await asyncio.wait_for(captured, timeout=20)
            return "ok", (data.get("data", []) if isinstance(data, dict) else [])
        except asyncio.TimeoutError:
            try:
                body = await page.inner_text("body")
            except Exception:
                body = ""
            return ("challenge" if _looks_like_waf_challenge(page.url, body)
                    else "timeout"), []
        except Exception as e:
            print(f"    ⚠ Error: {e}")
            return "error", []
        finally:
            page.remove_listener("response", on_response)

    for idx, (portal_id, agency, portal_county_) in enumerate(portals):
        print(f"  → {agency}...")
        portal_url = f"{PLANETBIDS_BASE}/portal/{portal_id}/bo/bo-search"

        outcome, records = await _fetch_portal(portal_id)

        # Per-portal WAF challenge (the /2001 page). Let a human clear it and
        # retry the portal once.
        if outcome == "challenge" and interactive and resolves_left > 0:
            resolves_left -= 1
            print(f"    ⚠ {agency} put up a PlanetBids verification challenge.")
            print(f"    → Solve it in the Chrome window, then press Enter here.")
            await asyncio.get_event_loop().run_in_executor(None, input, "")
            outcome, records = await _fetch_portal(portal_id)

        if outcome == "ok":
            status = "ok"
        elif outcome == "error":
            status = "error"
        else:
            status = "blocked"
            print(f"    ⚠ Blocked — "
                  + ("verification challenge not cleared" if outcome == "challenge"
                     else "timed out / blank page"))

        portal_bids = []
        for rec in records:
            attrs = rec.get("attributes", {})
            title = (attrs.get("title") or "").strip()
            if not title:
                continue
            stage = (attrs.get("stageStr") or "").lower()
            if stage in skip_stages:
                continue
            title_lower = title.lower()
            if not any(kw in title_lower for kw in kw_lower):
                continue

            bid_id     = rec.get("id", "")
            due_raw    = attrs.get("bidDueDate", "")
            posted_raw = attrs.get("issueDate", "")
            due_date   = _parse_date(str(due_raw)[:10]) if due_raw else None
            published  = _parse_date(str(posted_raw)[:10]) if posted_raw else None

            portal_bids.append({
                "bid_id": f"PB-{portal_id}-{bid_id}",
                "title": title,
                "agency": agency,
                "state": "California",
                "published_date": published.isoformat() if published else None,
                "published_raw": str(posted_raw),
                "due_date": due_date.isoformat() if due_date else None,
                "due_date_raw": str(due_raw),
                "is_relevant": _is_relevant(title, (
                    attrs.get("description") or attrs.get("scope") or
                    attrs.get("bidDescription") or ""
                ).strip()),
                "search_keyword": next((kw for kw in keywords if kw.lower() in title_lower), keywords[0]),
                "url": portal_url,
                "source": "PlanetBids",
                "county": portal_county_,
            })

        if status == "ok" and not portal_bids:
            status = "empty"

        if status in ("blocked", "error"):
            block_streak += 1
        else:
            block_streak = 0
            print(f"    ✓ {len(portal_bids)} relevant bids")

        pb_state.record(manifest, portal_id, agency, status, len(portal_bids))
        all_bids.extend(portal_bids)

        # Whole session looks WAF-poisoned — stop and leave the rest "pending".
        if block_streak >= PLANETBIDS_BLOCK_STREAK_LIMIT and idx < len(portals) - 1:
            remaining = len(portals) - idx - 1
            print(f"\n  ⚠ {block_streak} portals blocked in a row — session looks "
                  f"blocked. Stopping; {remaining} portal(s) left as pending.")
            stopped_early = True
            break

    if not stopped_early:
        manifest["run_finished"] = datetime.now().isoformat(timespec="seconds")
    pb_state.save(manifest)

    print()
    print(pb_state.format_summary(manifest))

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
                # Spec §3: cut DoD/GSA noise — restrict to the flooring NAICS.
                "sfm[naics][0][code]": "238330",     # Flooring Contractors
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

                # Place of performance — used by geo.py to keep only 4-county
                # federal work. SAM cards sometimes show a "City, CALIFORNIA ZIP"
                # line; capture whatever we can.
                pop_raw = ""
                for i, line in enumerate(lines):
                    if "Place of Performance" in line:
                        pop_raw = lines[i + 1] if i + 1 < len(lines) else ""
                        break
                if not pop_raw:
                    m = _re.search(
                        r"([A-Z][A-Za-z .'-]+,\s*(?:CALIFORNIA|CA)\b[^\n]*)", card_text)
                    if m:
                        pop_raw = m.group(1).strip()

                ca_bids.append({
                    "bid_id": f"SAM-{notice_id}",
                    "title": title,
                    "agency": agency,
                    "state": "California",
                    "pop_raw": pop_raw,
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

    Fail-fast: this PeopleSoft/Angular portal is slow and frequently unavailable,
    and it has yet to surface a flooring-relevant bid. Give it one short attempt
    (~15s to load, 2s per keyword) and bail the moment it stops cooperating —
    never let it stall the whole nightly scan.
    """
    print("\nSearching Cal eProcure (CA state portal)...")
    all_bids: list[dict] = []

    try:
        await page.goto(CALEPROCURE_URL, wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(5000)  # Angular SPA needs a beat to render the search form

        title = await page.title()
        if "maintenance" in title.lower() or "error" in title.lower():
            print("  ⚠ Cal eProcure unavailable (maintenance)")
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
                    print("  ⚠ Cal eProcure search UI not present — skipping")
                    break

                await search_input.click(click_count=3, timeout=5000)
                await search_input.fill(keyword, timeout=5000)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(2000)

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
                # Portal is not cooperating — stop hammering it, don't burn
                # ~30s per remaining keyword.
                print(f"  ⚠ Cal eProcure stopped after '{keyword}': {str(e)[:80]}")
                break

    except Exception as e:
        print(f"  ⚠ Cal eProcure unavailable: {str(e)[:80]}")

    print(f"  ✓ Cal eProcure total: {len(all_bids)} bids")
    return all_bids


# ---------------------------------------------------------------------------
# OpenGov procurement portals (Cloudflare-protected, uses shared cookies)
# ---------------------------------------------------------------------------

OPENGOV_PORTALS = {
    # Four-county municipalities only (spec §1). NorCal portals removed
    # 2026-08 — Sacramento / San Francisco / Alameda County are out of area.
    "cityofbell":       "City of Bell",
    "redondo":          "Redondo Beach",
    "citymb":           "Manhattan Beach",
    "pasadena":         "Pasadena",
    "santa-monica-ca":  "Santa Monica",
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
# UCLA Capital Programs — public "Projects Currently Bidding" page
# ---------------------------------------------------------------------------
# Server-rendered HTML, no auth (the UCLA Online Planroom behind it needs a
# login, but this index page lists every advertised project). Westwood campus,
# so every bid is Los Angeles County — stamped directly for the geo gate.
# The page carries no bid due date (it lives in the "Ad for Bids" PDF); the
# parser pulls it later. `est_value` shown on-page is not persisted here.

UCLA_BASE = "https://www.capitalprograms.ucla.edu"
UCLA_BIDDING_URL = UCLA_BASE + "/Contracts/Bidding"

# Section headers on the page. Rows under "Announcement to PQ Bidders" are
# addenda/notices to already-prequalified bidders, not new opportunities —
# everything else (open bids, sub-bid ads, prequalification ads) is kept.
UCLA_SKIP_SECTIONS = {"announcement to pq bidders"}


def _fetch_ucla_sync() -> list[dict]:
    """Scrape the UCLA bidding index. Pure HTTP + BeautifulSoup, no browser."""
    resp = requests.get(UCLA_BIDDING_URL, headers={"User-Agent": USER_AGENT}, timeout=25)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", id="cptable-leftlabels")
    if not table or not table.find("tbody"):
        return []

    projects: list[dict] = []
    section: str | None = None
    cur: dict | None = None

    def _flush():
        nonlocal cur
        if cur and cur.get("title") and section not in UCLA_SKIP_SECTIONS:
            projects.append(cur)
        cur = None

    for tr in table.find("tbody").find_all("tr", recursive=False):
        th = tr.find("th")
        if th and th.get("scope") == "colgroup":
            _flush()
            section = th.get_text(strip=True).lower()
            continue
        if "project-divider" in (tr.get("class") or []):
            _flush()
            continue
        rid = tr.get("id")
        if rid and rid.isdigit():
            _flush()
            a = tr.find("a")
            td = tr.find("td")
            cur = {
                "id": rid,
                "section": section,
                "title": (a.get_text(" ", strip=True) if a else td.get_text(" ", strip=True)).strip(),
                "url": (requests.compat.urljoin(UCLA_BASE, a["href"])
                        if a and a.get("href") else UCLA_BIDDING_URL),
                "number": "",
                "desc": "",
            }
            continue
        if cur is None:
            continue
        label = th.get_text(strip=True).lower() if th else ""
        td = tr.find("td")
        val = td.get_text(" ", strip=True) if td else ""
        if label.startswith("project number"):
            cur["number"] = val
        elif label.startswith("project description"):
            cur["desc"] = val
    _flush()
    return projects


async def _search_ucla(keywords: list[str]) -> list[dict]:
    """Pull UCLA Capital Programs advertised projects; flag flooring-relevant ones."""
    print("\nSearching UCLA Capital Programs (Westwood — LA County)...")
    try:
        projects = await asyncio.to_thread(_fetch_ucla_sync)
    except Exception as e:
        print(f"  ⚠ UCLA Capital Programs error: {e}")
        return []

    bids = []
    for p in projects:
        title = p["title"].replace("(opens in new tab, PDF)", "").strip()
        bids.append({
            "bid_id": f"UCLA-{p['id']}",
            "title": title,
            "agency": "UCLA Capital Programs",
            "state": "California",
            "county": "Los Angeles",
            "published_date": None,
            "published_raw": "",
            "due_date": None,
            "due_date_raw": "",
            "is_relevant": _is_relevant(title, f"{title} {p.get('desc', '')}"),
            "search_keyword": "open bids",
            "url": p["url"],
            "source": "UCLA Capital Programs",
        })

    relevant = sum(1 for b in bids if b["is_relevant"])
    print(f"  ✓ {len(bids)} advertised projects, {relevant} flooring-relevant")
    return bids


# ---------------------------------------------------------------------------
# City of Long Beach — "Long Beach Buys" (BuySpeed / Periscope S2G)
# ---------------------------------------------------------------------------
# Public advanced bid search, no login. Filter to Status = "Sent" (advertised)
# and drop rows whose bid-opening date is already past — BuySpeed leaves some
# dead solicitations in "Sent" for years. Every Long Beach agency is LA County.
# Replaces the PlanetBids Long Beach portal (15810), which is in PLANETBIDS_SKIP
# because its AWS WAF challenge could never be solved reliably.

LONGBEACH_SEARCH_URL = (
    "https://longbeachbuys.buyspeed.com/bso/view/search/external/advancedSearchBid.xhtml"
)

_LONGBEACH_ROW_JS = """() => {
  const tbl = [...document.querySelectorAll('table')].find(t => /Bid Opening Date/.test(t.innerText));
  if (!tbl) return [];
  return [...tbl.querySelectorAll('tbody tr')].map(tr => {
    const rec = {};
    tr.querySelectorAll('td').forEach(td => {
      const lbl = td.querySelector('.ui-column-title')?.innerText.trim();
      if (!lbl) return;
      if (!(lbl in rec)) rec[lbl] = td.innerText.replace(lbl, '').trim();
      const a = td.querySelector('a[href*="bidDetail"]');
      if (a) rec.href = a.href;
    });
    return rec;
  }).filter(r => r.href);
}"""


async def _search_longbeach(page, keywords: list[str]) -> list[dict]:
    """Scrape Long Beach Buys (BuySpeed) advertised bids. Browser required (JSF)."""
    print("\nSearching Long Beach BuySpeed (City of Long Beach — LA County)...")
    rows: list[dict] = []
    try:
        await page.goto(LONGBEACH_SEARCH_URL, wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(1000)
        await page.select_option("#advancedSearchForm\\:documentTypeSelect", label="Bid Solicitations")
        await page.wait_for_timeout(2500)
        await page.select_option("#bidSearchForm\\:status", label="Sent")
        await page.wait_for_timeout(400)
        await page.click("#bidSearchForm\\:btnBidSearch")
        await page.wait_for_timeout(5000)

        seen_first: set[str] = set()
        for _ in range(20):
            page_rows = await page.evaluate(_LONGBEACH_ROW_JS)
            if not page_rows:
                break
            key = page_rows[0].get("href")
            if key in seen_first:
                break
            seen_first.add(key)
            rows.extend(page_rows)

            nxt = page.locator(".ui-paginator-bottom .ui-paginator-next").first
            if not await nxt.count():
                break
            if "ui-state-disabled" in (await nxt.get_attribute("class") or ""):
                break
            await nxt.click()
            await page.wait_for_timeout(3500)
    except Exception as e:
        print(f"  ⚠ Long Beach BuySpeed error: {e}")

    today = date.today()
    bids: list[dict] = []
    for r in rows:
        sol = (r.get("Bid Solicitation #") or "").strip()
        if not sol:
            continue
        desc = (r.get("Description") or "").strip()
        opening_raw = (r.get("Bid Opening Date") or "").strip()
        due = _parse_date(opening_raw.split()[0]) if opening_raw else None
        if due and due < today:
            continue  # stale "Sent" solicitation
        bids.append({
            "bid_id": f"LB-{sol}",
            "title": desc or sol,
            "agency": (r.get("Organization Name") or "City of Long Beach").strip(),
            "state": "California",
            "county": "Los Angeles",
            "published_date": None,
            "published_raw": "",
            "due_date": due,
            "due_date_raw": opening_raw,
            "is_relevant": _is_relevant(desc, desc),
            "search_keyword": "open bids",
            "url": r.get("href") or LONGBEACH_SEARCH_URL,
            "source": "Long Beach BuySpeed",
        })

    relevant = sum(1 for b in bids if b["is_relevant"])
    print(f"  ✓ {len(bids)} advertised bids, {relevant} flooring-relevant")
    return bids


# ---------------------------------------------------------------------------
# LAUSD Facilities — "Updated Bid Information Report (Sorted by Bid Date)"
# ---------------------------------------------------------------------------
# LAUSD FSD publishes every advertised facilities project in one public PDF
# ("Bid Report.pdf") linked from procurement.lausd.org. No login, and the
# edlio CDN that hosts the PDF is reachable where laschools.org itself is not.
# The report is regenerated in place, so resolve the current URL from the CMS
# page each run rather than hardcoding the media hash. Every LAUSD project is
# LA County / K-12. FCU's flooring licence is C-15, so a required licence that
# names C-15 is treated as relevant even when the description is generic.

LAUSD_BIDDOCS_URL = "https://procurement.lausd.org/apps/pages/Bid_Documents"
LAUSD_SOURCE_LINK = "https://www.laschools.org/new-site/bidding-opportunities/bid-documents"

_LAUSD_NOISE_RE = re.compile(
    r"\n(?:Updated Bid Information Report Sorted by Bid Date"
    r"|B E S T V A L U E|C O N S T R U C T I O N|I N F O R M A L|M A I N T E N A N C E"
    r"|J O C|A / E|BOE District = .*|Total Bids for .*"
    r"|LOS ANGELES UNIFIED SCHOOL DISTRICT|FACILITIES CONTRACTS)\n"
)


def _lausd_field(pattern: str, text: str, default: str = "") -> str:
    m = re.search(pattern, text, re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else default


def _fetch_lausd_fsd_sync() -> list[dict]:
    """Download + parse the LAUSD FSD bid-date report PDF. Pure HTTP + pdfplumber."""
    import pdfplumber

    headers = {"User-Agent": USER_AGENT}
    page = requests.get(LAUSD_BIDDOCS_URL, headers=headers, timeout=25)
    page.raise_for_status()
    m = re.search(r'href="(https://media\.edlio\.net/[^"]+Bid%20Report\.pdf)"', page.text, re.I) \
        or re.search(r'href="([^"]+)"[^>]*>\s*Updated Bid Report', page.text, re.I)
    if not m:
        raise RuntimeError("could not find the Bid Report PDF link on the LAUSD page")
    pdf_url = m.group(1).replace("&amp;", "&")

    pdf_resp = requests.get(pdf_url, headers=headers, timeout=45)
    pdf_resp.raise_for_status()
    tmp = os.path.join(os.path.dirname(__file__), "output", "lausd_bidreport.pdf")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    with open(tmp, "wb") as fh:
        fh.write(pdf_resp.content)

    with pdfplumber.open(tmp) as pdf:
        full = "\n".join(pg.extract_text() or "" for pg in pdf.pages)
    full = _LAUSD_NOISE_RE.sub("\n", full)

    entries = [e for e in re.split(r"(?=Bid/RFQ No\s+\d+)", full) if e.startswith("Bid/RFQ No")]
    rows = []
    for raw in entries:
        e = re.sub(r"\s+", " ", raw)
        rows.append({
            "no":     _lausd_field(r"Bid/RFQ No\s+(\d+)", e),
            "open":   _lausd_field(r"Bid Open:\s*([\d/]+)", e),
            "prebid": _lausd_field(r"Pre-Bid:\s*([\d/]+)", e),
            "name":   _lausd_field(r"Project Name:\s*(.+?)\s*Description:", e),
            "desc":   _lausd_field(r"Description:\s*(.+?)\s*(?:License Type Required:|Prequalification is Required)", e),
            "lic":    _lausd_field(r"License Type Required:\s*(.+?)\s*Contract Bond Estimate:", e),
        })
    return rows


async def _search_lausd_fsd(keywords: list[str]) -> list[dict]:
    """Pull LAUSD Facilities advertised projects from the public bid-date report."""
    print("\nSearching LAUSD Facilities (FSD bid-date report)...")
    try:
        rows = await asyncio.to_thread(_fetch_lausd_fsd_sync)
    except Exception as e:
        print(f"  ⚠ LAUSD Facilities error: {e}")
        return []

    today = date.today()
    bids = []
    for r in rows:
        if not r["no"]:
            continue
        due = _parse_date(r["open"]) if r["open"] else None
        if due and due < today:
            continue
        name = re.sub(r"\s*(?:Pre-Bid is Mandatory|Prequalification is Required)\s*", " ",
                      r["name"], flags=re.I).strip()
        if name.count("(") > name.count(")"):
            name += ")"
        title = f"{name} — {r['desc']}".strip(" —") if r["desc"] else name
        haystack = f"{title} {r['lic']}"
        relevant = _is_relevant(title, haystack) or bool(re.search(r"\bC-?15\b", r["lic"], re.I))
        bids.append({
            "bid_id": f"LAUSD-{r['no']}",
            "title": title[:480],
            "agency": "Los Angeles Unified School District",
            "state": "California",
            "county": "Los Angeles",
            "published_date": None,
            "published_raw": "",
            "due_date": due,
            "due_date_raw": r["open"],
            "is_relevant": relevant,
            "search_keyword": "C-15" if re.search(r"\bC-?15\b", r["lic"], re.I) else "open bids",
            "url": LAUSD_SOURCE_LINK,
            "source": "LAUSD Facilities",
        })

    relevant = sum(1 for b in bids if b["is_relevant"])
    print(f"  ✓ {len(bids)} advertised projects, {relevant} flooring-relevant")
    return bids


# ---------------------------------------------------------------------------
# SoCal Builders Plan Room (CyberCopy — public CA construction bids)
# ---------------------------------------------------------------------------

PLAN_ROOMS = [
    ("https://www.southerncaliforniabuildersplanroom.com", "SoCal Plan Room"),
    # CyberCopy-platform SoCal plan room from FCU's login sheet (row 30). Same
    # scraper contract as Crisp — /projects/public?status=bidding.
    ("https://www.cybercopyplanroom.com", "CyberCopy Plan Room"),
]
CRISP_BASE = "https://www.crispplanroom.com"


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
                    "is_relevant": _is_relevant(title, raw),
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

# Spec §1: only the SoCal districts covering the four counties —
# D7 (LA + Ventura), D12 (Orange), D11 (San Diego + Imperial).
# Imperial-County projects in D11 are dropped later by geo.classify_location.
CCOP_URL = "https://ccop.dot.ca.gov/onestopshop/7,11,12"


async def _search_ccop(page, keywords: list[str]) -> list[dict]:
    """
    Scrape Caltrans Contracting Opportunities Portal — SoCal districts only
    (D7 / D11 / D12). Public, no auth, all projects load on one page.
    Filters locally by flooring keywords.
    """
    print("\nSearching Caltrans CCOP (SoCal districts 7/11/12)...")
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

                if _is_relevant(desc):
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


async def _search_crisp(page) -> list[dict]:
    """Scrape Crisp Plan Room — server-rendered, fully public listing."""
    all_bids: list[dict] = []
    page_num = 1
    _urgency_re = re.compile(r'^bids due|\d{1,2}/\d{1,2}/\d{2,4}', re.I)

    print("\nSearching Crisp Plan Room...")
    try:
        while True:
            url = f"{CRISP_BASE}/projects/public?status=bidding&page={page_num}"
            await page.goto(url, wait_until="networkidle", timeout=20000)
            await page.wait_for_timeout(1000)

            body_text = await page.inner_text("body")
            page_match = re.search(r'Page\s+\d+\s+of\s+(\d+)', body_text)
            total_pages = int(page_match.group(1)) if page_match else 1

            rows = await page.query_selector_all('a.row[href*="/projects/"]')
            for row in rows:
                href = await row.get_attribute("href") or ""
                m = re.search(r'/projects/(\d+)/details/', href)
                if not m:
                    continue
                proj_id = m.group(1)

                # Title = actual project description (always last meaningful line)
                desc_el = await row.query_selector('.description')
                title = (await desc_el.inner_text()).strip() if desc_el else ""
                if not title:
                    continue

                # Due date from dedicated element
                bid_date_el = await row.query_selector('.bid-date')
                due_raw = (await bid_date_el.inner_text()).strip() if bid_date_el else ""

                # Agency: Playwright inner_text structure is always:
                # [0] "Bids due in N days"  [1] date  [2] short_name  [3] AGENCY  [...] description
                raw_lines = [l.strip() for l in (await row.inner_text()).split("\n") if l.strip()]
                agency = raw_lines[3] if len(raw_lines) >= 5 else ""

                # Normalize "5/14/26 10:00am" → "5/14/2026"
                date_m = re.search(r'(\d{1,2}/\d{1,2}/(\d{2,4}))', due_raw)
                if date_m:
                    due_str = date_m.group(1)
                    if len(date_m.group(2)) == 2:
                        p = due_str.split("/")
                        due_str = f"{p[0]}/{p[1]}/20{p[2]}"
                else:
                    due_str = ""

                url_full = href if href.startswith("http") else CRISP_BASE + href
                all_bids.append({
                    "bid_id":         f"CRISP-{proj_id}",
                    "title":          title,
                    "agency":         agency,
                    "state":          "California",
                    "published_date": None,
                    "published_raw":  "",
                    "due_date":       _parse_date(due_str),
                    "due_date_raw":   due_str,
                    "is_relevant":    _is_relevant(title),
                    "search_keyword": "open bids",
                    "url":            url_full,
                    "source":         "Crisp Plan Room",
                })

            if page_num >= total_pages:
                break
            page_num += 1

    except Exception as e:
        print(f"  ⚠ Crisp Plan Room error: {e}")

    relevant = sum(1 for b in all_bids if b["is_relevant"])
    print(f"  ✓ {len(all_bids)} open bids fetched, {relevant} flooring-relevant")
    return all_bids


async def _search_plan_rooms(page, keywords: list[str]) -> list[dict]:
    """Scrape all configured CyberCopy plan rooms + Crisp."""
    all_bids: list[dict] = []
    for base_url, source_name in PLAN_ROOMS:
        print(f"\nSearching {source_name}...")
        bids = await _search_plan_room(page, base_url, source_name)
        relevant = sum(1 for b in bids if b["is_relevant"])
        print(f"  ✓ {len(bids)} open bids ({relevant} flooring-relevant)")
        all_bids.extend(bids)
    all_bids.extend(await _search_crisp(page))
    return all_bids


async def run_scan(keywords: list[str] = None, source: str = None, headless: bool = True,
                   live_page=None, funnel=None) -> list[dict]:
    """
    Main scan entry point.
    source: filter to a single source ("sam", "planetbids", "bidnet", etc.) or None for all.
    live_page: verified Playwright page to use for PlanetBids (WAF already bypassed).
    funnel: optional ScanFunnel — populated in place with per-stage / per-source
            telemetry for the /scanner dashboard. See funnel.py.
    Returns list of deduplicated bid dicts sorted by relevance + due date.
    """
    if keywords is None:
        keywords = SEARCH_KEYWORDS

    if funnel is None:
        from funnel import ScanFunnel
        funnel = ScanFunnel(mode=source or "full")

    src = source.lower() if source else None
    all_bids = []

    needs_browser = src is None or src not in ("sam", "qualitybidders", "ucla", "lausd")

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
                with funnel.guard("BidNet Direct"):
                    page = await context.new_page()
                    for keyword in keywords:
                        bids = await _search_keyword(page, keyword)
                        for b in bids:
                            b.setdefault("source", "BidNet Direct")
                        all_bids.extend(bids)
                    await page.close()

            if src == "planetbids" or (src is None and live_page is not None):
                with funnel.guard("PlanetBids"):
                    pb_bids = await _search_planetbids(context, keywords, live_page=live_page)
                    all_bids.extend(pb_bids)
                try:
                    import pb_state
                    funnel.apply_planetbids_manifest(pb_state.load(), PLANETBIDS_PORTALS)
                except Exception as e:
                    print(f"    ⚠ PlanetBids manifest fold failed: {e}")

            if src in (None, "caleprocure"):
                with funnel.guard("Cal eProcure"):
                    cal_page = await context.new_page()
                    cal_bids = await _search_caleprocure(cal_page, keywords)
                    all_bids.extend(cal_bids)
                    await cal_page.close()

            if src == "opengov":
                with funnel.guard("OpenGov"):
                    og_bids = await _search_opengov(context, keywords)
                    all_bids.extend(og_bids)

            if src in (None, "planrooms"):
                with funnel.guard("Plan Rooms"):
                    pr_page = await context.new_page()
                    pr_bids = await _search_plan_rooms(pr_page, keywords)
                    all_bids.extend(pr_bids)
                    await pr_page.close()

            if src in (None, "caltrans"):
                with funnel.guard("Caltrans CCOP"):
                    ccop_page = await context.new_page()
                    ccop_bids = await _search_ccop(ccop_page, keywords)
                    all_bids.extend(ccop_bids)
                    await ccop_page.close()

            if src in (None, "longbeach"):
                with funnel.guard("Long Beach BuySpeed"):
                    lb_page = await context.new_page()
                    lb_bids = await _search_longbeach(lb_page, keywords)
                    all_bids.extend(lb_bids)
                    await lb_page.close()

            await browser.close()

    if src in (None, "sam"):
        with funnel.guard("SAM.gov"):
            sam_bids = await _search_samgov(keywords)
            all_bids.extend(sam_bids)

    if src in (None, "qualitybidders"):
        with funnel.guard("Quality Bidders"):
            qb_bids = await _search_qualitybidders(keywords)
            all_bids.extend(qb_bids)

    if src in (None, "ucla"):
        with funnel.guard("UCLA Capital Programs"):
            ucla_bids = await _search_ucla(keywords)
            all_bids.extend(ucla_bids)

    if src in (None, "lausd"):
        with funnel.guard("LAUSD Facilities"):
            lausd_bids = await _search_lausd_fsd(keywords)
            all_bids.extend(lausd_bids)

    funnel.note_raw(all_bids)

    # Normalise bid IDs before dedup / persistence — they're used as filesystem
    # paths downstream (parser.py: output/specs/<bid_id>.pdf).
    for b in all_bids:
        b["bid_id"] = _safe_bid_id(b.get("bid_id", ""))

    # --- Geographic + agency-type gate (spec §1 / §2) ---------------------
    # Enrich every bid with county / geo_status / agency_type / is_k12, then
    # drop anything whose place of performance is outside the four in-scope
    # counties (LA, Orange, Ventura, San Diego). "unknown" is kept and flagged
    # for Robert to confirm during qualification — never silently dropped.
    from geo import enrich
    for b in all_bids:
        enrich(b)
    funnel.note_geo(all_bids)
    before_geo = len(all_bids)
    all_bids = [b for b in all_bids if b.get("geo_status") != "out"]
    funnel.note_kept(all_bids)
    dropped = before_geo - len(all_bids)
    if dropped:
        print(f"\nGeo filter: dropped {dropped} out-of-area bid(s); "
              f"{sum(1 for b in all_bids if b.get('geo_status') == 'unknown')} flagged unknown")

    pre_dedup = len(all_bids)
    deduped = _dedup(all_bids)
    funnel.note_final(deduped, pre_dedup)

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
