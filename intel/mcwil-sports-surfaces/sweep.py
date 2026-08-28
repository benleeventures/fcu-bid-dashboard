"""
Ad-hoc intel sweep — McWil Sports Surfaces $/SF bid parameters.

One-off. NOT part of normal bid-scanner operations. Writes only to this folder,
never to the production Supabase / Airtable pipeline.

What it does
------------
1. Opens real Chrome, you solve one AWS-WAF CAPTCHA per PlanetBids tenant.
2. (optional) logs into the FCU PlanetBids vendor account and scrapes the list of
   agencies FCU is registered with -> portal IDs we can actually see tabs on.
3. For every portal: pulls the full /papi/bids list, keeps AWARDED bids whose
   title/description matches a sports-flooring keyword set.
4. For each hit: opens the award detail page, captures the bid tabulation
   (every bidder + amount) and the winner.
5. Writes:
     results_mcwil.csv       - rows where McWil bid or won
     results_context.csv     - every sports-flooring award (competitor context)
     results_raw.json        - full capture, resumable
     state.json              - per-portal progress (skip on re-run)

Usage
-----
    cd intel/mcwil-sports-surfaces
    python sweep.py                 # full sweep, curated portal list
    python sweep.py --discover      # also scrape FCU's registered-agency list first
    python sweep.py --resume        # skip portals already done in state.json
    python sweep.py --portals 23758,21372   # only these portal IDs
"""

import asyncio
import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
BID_SCANNER = HERE.parent.parent / "bid-scanner"
sys.path.insert(0, str(BID_SCANNER))

try:
    from dotenv import load_dotenv
    load_dotenv(BID_SCANNER / ".env")
except ImportError:
    pass

from intel_scanner import _fetch_bid_detail, _parse_amount  # noqa: E402
from scanner import PLANETBIDS_PORTALS as _PROD_PORTALS      # noqa: E402

PLANETBIDS_BASE = "https://vendors.planetbids.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# ---------------------------------------------------------------------------
# Portal list — curated K-12 / CCD / parks additions on top of the production
# city list. (agency, county, note). county "" = out of 4-county footprint.
# IDs verified as they are confirmed; unverified ones are skipped with a warning.
# ---------------------------------------------------------------------------
EXTRA_PORTALS = {
    "23758": ("Long Beach Unified School District", "Los Angeles", "verified web 2026-08"),
    "41631": ("El Camino Community College District", "Los Angeles", "verified web 2026-08"),
    # --- confirmed to USE PlanetBids, numeric ID still to resolve ---
    #   Santa Ana USD (Orange) · Garden Grove USD (Orange) · Orange USD (Orange)
    #   North OC CCD (Orange) · Coast CCD (Orange) · Rancho Santiago CCD (Orange)
    #   San Diego CCD (San Diego)
    # Add here as `"<id>": ("Name", "County", "note"),` — the sweep prints the
    # real agency name from the API on each run, so a wrong label self-corrects.
}

# Portals most likely to carry McWil gym-floor work — the "highest probability"
# first pass. Education + big parks-and-rec cities.
HIGH_PROB_IDS = [
    "23758",  # Long Beach USD          (K-12 — top prospect)
    "41631",  # El Camino CCD           (community college gyms)
    "21372",  # LA Community College District
    "61954",  # LA County Office of Education
    "25987",  # Cal State LA
    "19236",  # Port of Long Beach      (rec / field house)
    "15810",  # City of Long Beach      (parks gyms)
    "47426",  # Torrance                (parks gyms)
    "14210",  # Burbank
    "39503",  # Glendale
    "24662",  # Pomona
    "20137",  # City of Santa Ana
    "17950",  # City of San Diego
    "42566",  # Lancaster
    "23532",  # Palmdale
    "39470",  # Gardena                 (McWil's home city)
]

# ---------------------------------------------------------------------------
# Sports-flooring relevance — replaces bid-scanner's carpet/VCT _is_relevant
# ---------------------------------------------------------------------------
SPORTS_KEYWORDS = [
    "gym floor", "gymnasium floor", "gym flooring", "gymnasium flooring",
    "wood floor", "wood athletic", "hardwood", "maple floor", "maple gym",
    "athletic floor", "athletic flooring", "athletic surface", "sports floor",
    "sports flooring", "sport surface", "sport court", "sports surface",
    "sport floor", "resilient athletic", "poured urethane", "synthetic sports",
    "synthetic athletic", "rubber floor", "rubberized", "weight room",
    "fitness floor", "multipurpose room floor", "mpr floor", "stage floor",
    "running track", "track resurfac", "track replacement", "track and field surface",
    "field house", "basketball court", "volleyball court", "bleacher",
    "floor refinish", "floor sanding", "sand and refinish", "recoat gym",
    "hoop", "backstop", "wall pad", "gym divider", "playing surface",
]
SPORTS_RE = re.compile("|".join(re.escape(k) for k in SPORTS_KEYWORDS), re.I)

# strong signal even if generic word missing
STRONG_RE = re.compile(r"\b(gym|gymnasium|athletic|natatorium|field ?house)\b", re.I)
FLOOR_RE = re.compile(r"\b(floor|flooring|surface|court|track)\b", re.I)


def is_sports_flooring(title: str, desc: str = "") -> bool:
    blob = f"{title}\n{desc}"
    if SPORTS_RE.search(blob):
        return True
    if STRONG_RE.search(blob) and FLOOR_RE.search(blob):
        return True
    return False


# ---------------------------------------------------------------------------
# McWil name matching
# ---------------------------------------------------------------------------
MCWIL_RE = re.compile(r"\bmc\s?wil?l?\b|mcwil\s*sports|mc\s*wil\s*sports", re.I)


def is_mcwil(name: str) -> bool:
    if not name:
        return False
    n = name.lower()
    return bool(MCWIL_RE.search(n)) or "mcwil" in n.replace(" ", "")


# ---------------------------------------------------------------------------
# State / output helpers
# ---------------------------------------------------------------------------
STATE_PATH = HERE / "state.json"
RAW_PATH = HERE / "results_raw.json"
AWARDED_LOG_PATH = HERE / "all_awarded.json"


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {"portals": {}, "started": datetime.now().isoformat(timespec="seconds")}


def save_state(state: dict):
    STATE_PATH.write_text(json.dumps(state, indent=2))


def load_raw() -> list:
    if RAW_PATH.exists():
        return json.loads(RAW_PATH.read_text())
    return []


def save_raw(rows: list):
    RAW_PATH.write_text(json.dumps(rows, indent=2, default=str))


def write_csvs(rows: list):
    """rows = list of award dicts with a 'submissions' list."""
    mcwil_rows, context_rows = [], []
    for a in rows:
        subs = a.get("submissions", [])
        mcwil_sub = next((s for s in subs if is_mcwil(s.get("raw_vendor_name", ""))), None)
        winner = a.get("winner_name") or ""
        mcwil_won = is_mcwil(winner)
        base = {
            "agency": a.get("agency"),
            "county": a.get("county") or "",
            "out_of_footprint": "yes" if not a.get("county") else "",
            "title": a.get("title"),
            "awarded_at": a.get("awarded_at") or "",
            "total_bidders": a.get("total_bidders") or len(subs),
            "winner": winner,
            "winner_amount": a.get("winner_amount") or "",
            "url": a.get("url") or "",
        }
        # context row (every sports-flooring award)
        context_rows.append({**base, "all_bids": "; ".join(
            f"{s.get('raw_vendor_name','?')}=${s.get('bid_amount')}" for s in subs
        )})
        if mcwil_sub or mcwil_won:
            mcwil_amt = (mcwil_sub or {}).get("bid_amount")
            mcwil_rank = (mcwil_sub or {}).get("rank")
            sorted_amts = sorted(s["bid_amount"] for s in subs if s.get("bid_amount"))
            spread_to_next = ""
            if mcwil_amt and sorted_amts:
                higher = [x for x in sorted_amts if x > mcwil_amt]
                lower = [x for x in sorted_amts if x < mcwil_amt]
                if mcwil_won and higher:
                    spread_to_next = round(higher[0] - mcwil_amt, 2)
                elif lower:
                    spread_to_next = round(mcwil_amt - lower[-1], 2)
            mcwil_rows.append({**base,
                               "mcwil_bid": mcwil_amt if mcwil_amt is not None else "",
                               "mcwil_rank": mcwil_rank if mcwil_rank is not None else "",
                               "mcwil_won": "yes" if mcwil_won else "no",
                               "spread_to_beat": spread_to_next,
                               "all_bids": "; ".join(
                                   f"{s.get('raw_vendor_name','?')}=${s.get('bid_amount')}"
                                   for s in subs)})

    if mcwil_rows:
        _dump_csv(HERE / "results_mcwil.csv", mcwil_rows)
    _dump_csv(HERE / "results_context.csv", context_rows)
    print(f"\n  -> {len(mcwil_rows)} McWil row(s) | {len(context_rows)} sports-flooring award(s)")


def _dump_csv(path: Path, rows: list):
    if not rows:
        return
    keys = list({k for r in rows for k in r})
    order = ["agency", "county", "out_of_footprint", "title", "awarded_at",
             "mcwil_bid", "mcwil_rank", "mcwil_won", "spread_to_beat",
             "winner", "winner_amount", "total_bidders", "all_bids", "url"]
    keys = [k for k in order if k in keys] + [k for k in keys if k not in order]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


# ---------------------------------------------------------------------------
# PlanetBids scraping
#
# The bo-search page lazy-loads /papi/bids 30 rows at a time. Passively grabbing
# the first response only ever saw page 1 (~15 awarded of 412 bids / 14 pages).
# We capture the app's own /papi/bids responses and scroll the list to force it
# to load every page.
#
#   api-external.prod.planetbids.com/papi/bids?cid=<CID>&page=<N>&per_page=30&stage_id=0
#   meta: { totalBids, totalPages }        stageStr "Awarded" == stageId 6
# ---------------------------------------------------------------------------


async def capture_portal_bids(page, portal_id: str) -> tuple[str, list]:
    """
    Navigate the portal and let the app's OWN /papi/bids calls do the work — we
    just capture every response and scroll the results list to force it to
    lazy-load page after page until meta.totalPages is covered.

    (Replaying the call ourselves hits CORS / WAF on the api-external host; using
    the app's requests sidesteps all of that.)
    """
    from urllib.parse import urlparse, parse_qs

    seen: dict[int, list] = {}
    meta: dict = {}

    async def on_response(resp):
        if "/papi/bids?" not in resp.url:
            return
        q = parse_qs(urlparse(resp.url).query)
        if q.get("cid", [""])[0] != portal_id:
            return
        try:
            j = await resp.json()
        except Exception:
            return
        pg = int((q.get("page") or ["1"])[0])
        data = j.get("data", []) if isinstance(j, dict) else []
        if data or pg not in seen:
            seen[pg] = data
        if isinstance(j, dict) and j.get("meta"):
            meta.update(j["meta"])

    page.on("response", on_response)
    try:
        await page.goto(f"{PLANETBIDS_BASE}/portal/{portal_id}/bo/bo-search",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(4500)
    except Exception as e:
        page.remove_listener("response", on_response)
        print(f"    ! nav error: {e}")
        return "error", []

    try:
        body = await page.inner_text("body")
    except Exception:
        body = ""
    if "/2001" in page.url or "human verification" in body.lower():
        page.remove_listener("response", on_response)
        return "blocked", []

    if not seen:
        page.remove_listener("response", on_response)
        return ("blocked" if len(body.strip()) < 200 else "empty"), []

    total_pages = int(meta.get("totalPages") or 1)
    total_bids = int(meta.get("totalBids") or 0)
    print(f"    {total_bids or '?'} bids across {total_pages} page(s) — scrolling...")

    scroll_js = """() => {
        const cands = [document.scrollingElement].concat(
            Array.from(document.querySelectorAll('*')).filter(
                e => e.scrollHeight > e.clientHeight + 80 && e.clientHeight > 120));
        cands.forEach(e => { if (e) e.scrollTop = e.scrollHeight; });
    }"""
    stagnant = 0
    for _ in range(total_pages * 3 + 10):
        if len(seen) >= total_pages:
            break
        before = len(seen)
        try:
            await page.evaluate(scroll_js)
            await page.mouse.wheel(0, 8000)
        except Exception:
            pass
        await page.wait_for_timeout(1400)
        stagnant = stagnant + 1 if len(seen) == before else 0
        if stagnant >= 5:
            print(f"    ! stalled at {len(seen)}/{total_pages} pages")
            break

    page.remove_listener("response", on_response)
    records = [r for pg in sorted(seen) for r in seen[pg]]
    return "ok", records


async def scrape_portal_links(page) -> dict:
    """
    Manual portal-ID harvest. PlanetBids retired the global vendor login
    (vendors.planetbids.com/login -> "not a valid agency portal"), and there is
    no cross-agency search. So: you browse PlanetBids in the open Chrome window —
    Google an agency's bid page, open any /portal/<id>/... URL — and this scoops
    every /portal/<id>/ link + visible agency name off whatever page you land on.
    Press Enter with nothing to finish.
    """
    found = {}
    print("\n  Portal harvest — browse to agency bid pages in Chrome.")
    while True:
        print("  Press Enter to scrape the current page (or 'q' + Enter to stop).")
        ans = await asyncio.get_event_loop().run_in_executor(None, input, "")
        if ans.strip().lower() == "q":
            break
        try:
            html = await page.content()
            for m in re.finditer(r"/portal/(\d+)/", html):
                found.setdefault(m.group(1), "")
            title = await page.title()
            links = await page.evaluate("""() => Array.from(document.querySelectorAll('a'))
                .map(a => ({href: a.href, text: (a.innerText||'').trim()}))
                .filter(x => /\\/portal\\/\\d+\\//.test(x.href))""")
            for lk in links:
                mm = re.search(r"/portal/(\d+)/", lk["href"])
                if mm and lk["text"]:
                    found[mm.group(1)] = lk["text"][:80]
            cur = re.search(r"/portal/(\d+)/", page.url)
            if cur and title and "Human Verification" not in title:
                found[cur.group(1)] = title[:80]
            print(f"    have {len(found)} portal id(s) so far")
        except Exception as e:
            print(f"    ! {e}")
    return found


def build_portal_list(args) -> list[tuple]:
    """Return [(portal_id, agency, county), ...]."""
    merged = {}
    for pid, (agency, county) in _PROD_PORTALS.items():
        merged[pid] = (agency, county)
    for pid, (agency, county, _note) in EXTRA_PORTALS.items():
        if not pid.isdigit():
            continue
        merged[pid] = (agency, county)

    if args.get("portals"):
        want = set(args["portals"].split(","))
        return [(pid, *merged.get(pid, ("(unknown)", "")))
                for pid in want]

    if args.get("high_prob", True) and not args.get("all"):
        return [(pid, *merged.get(pid, ("(unknown)", "")))
                for pid in HIGH_PROB_IDS if pid in merged or True]

    return [(pid, a, c) for pid, (a, c) in merged.items()]


async def run(args):
    from playwright.async_api import async_playwright

    portals = build_portal_list(args)
    state = load_state()
    raw = load_raw()
    done = {r["key"] for r in raw}

    if args.get("resume"):
        portals = [p for p in portals if state["portals"].get(p[0]) not in ("ok", "empty")]
    print(f"Sweeping {len(portals)} portal(s):")
    for pid, a, c in portals:
        print(f"  {pid:>6}  {a} ({c or 'out-of-footprint'})")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(channel="chrome", headless=False)
        except Exception:
            browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()

        if args.get("discover"):
            disc = await scrape_portal_links(page)
            (HERE / "discovered_portals.json").write_text(json.dumps(disc, indent=2))
            print(f"\n  wrote {len(disc)} portal id(s) -> discovered_portals.json")

        first = portals[0][0] if portals else "39470"
        await page.goto(f"{PLANETBIDS_BASE}/portal/{first}/bo/bo-search",
                        wait_until="domcontentloaded", timeout=30000)
        print("\n-> Solve the CAPTCHA in Chrome, wait for the bid list, press Enter here.")
        await asyncio.get_event_loop().run_in_executor(None, input, "")

        for pid, agency, county in portals:
            print(f"\n  -> {agency} [{pid}]")
            outcome, records = await capture_portal_bids(page, pid)
            if outcome == "blocked":
                print("    blocked — solve the challenge in Chrome + press Enter (or just Enter to skip)")
                await asyncio.get_event_loop().run_in_executor(None, input, "")
                outcome, records = await capture_portal_bids(page, pid)

            state["portals"][pid] = outcome
            save_state(state)
            if outcome not in ("ok", "empty"):
                print(f"    {outcome} — skipping")
                continue

            awarded = [r for r in records
                       if (r.get("attributes", {}).get("stageStr") or "").lower()
                       in ("awarded", "award pending")]
            # dump every awarded title for review (keyword filter QA)
            all_titles = AWARDED_LOG_PATH.exists() and json.loads(AWARDED_LOG_PATH.read_text()) or {}
            all_titles[pid] = {"agency": agency, "titles": sorted(
                (r.get("attributes", {}).get("title") or "").strip() for r in awarded)}
            AWARDED_LOG_PATH.write_text(json.dumps(all_titles, indent=2))

            hits = []
            for r in awarded:
                at = r.get("attributes", {})
                title = (at.get("title") or "").strip()
                desc = (at.get("description") or at.get("scope") or
                        at.get("bidDescription") or "").strip()
                if title and is_sports_flooring(title, desc):
                    hits.append((str(r.get("id", "")), title))
            print(f"    {len(awarded)} awarded | {len(hits)} sports-flooring")

            for bid_id, title in hits:
                key = f"{pid}:{bid_id}"
                if key in done:
                    continue
                print(f"      . {title[:70]}")
                try:
                    detail = await _fetch_bid_detail(page, pid, bid_id)
                except Exception as e:
                    print(f"        ! detail error: {e}")
                    detail = {}
                row = {
                    "key": key, "portal_id": pid, "agency": agency, "county": county,
                    "numeric_bid_id": bid_id, "title": title,
                    "awarded_at": detail.get("awarded_at"),
                    "winner_name": detail.get("winner_name"),
                    "winner_amount": detail.get("winner_amount"),
                    "total_bidders": detail.get("total_bidders"),
                    "submissions": detail.get("submissions", []),
                    "url": detail.get("url"),
                }
                raw.append(row)
                done.add(key)
                save_raw(raw)
                if any(is_mcwil(s.get("raw_vendor_name", "")) for s in row["submissions"]) \
                        or is_mcwil(row["winner_name"] or ""):
                    print(f"        *** McWil found ***")

        await browser.close()

    write_csvs(raw)
    print("\nDone. See results_mcwil.csv / results_context.csv / results_raw.json")


def parse_args(argv):
    a = {"resume": "--resume" in argv, "discover": "--discover" in argv,
         "all": "--all" in argv, "high_prob": True}
    for i, tok in enumerate(argv):
        if tok == "--portals" and i + 1 < len(argv):
            a["portals"] = argv[i + 1]
    return a


if __name__ == "__main__":
    asyncio.run(run(parse_args(sys.argv[1:])))
