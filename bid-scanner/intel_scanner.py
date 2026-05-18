"""
FCU Intel Scanner — scrapes PlanetBids awarded bids for competitive intelligence.

Collects submission tabulations (who bid + amounts) and award data (winner),
normalizes vendor names across bids using token matching + Ollama fuzzy resolution,
and persists to Supabase bid_intel + bid_intel_submissions tables.

Usage:
  python main.py --intel   (triggered on-demand, reuses live CAPTCHA session)
"""

import asyncio
import os
import re
from datetime import datetime

import requests

PLANETBIDS_BASE = "https://vendors.planetbids.com"

_NAME_STOP = frozenset([
    "inc", "llc", "corp", "co", "ltd", "the", "and", "&", "dba", "of", "a",
    "company", "services", "group", "solutions", "enterprises",
])


# ---------------------------------------------------------------------------
# Vendor name resolution
# ---------------------------------------------------------------------------

def _name_tokens(s: str) -> set[str]:
    """Significant tokens from a company name (strips legal suffixes, punctuation)."""
    return {
        t for t in re.sub(r"[^\w\s]", "", s.lower()).split()
        if t not in _NAME_STOP and len(t) > 1
    }


def _name_overlap(a: str, b: str) -> float:
    """Jaccard similarity between significant tokens of two company names."""
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _ollama_match(raw_name: str, candidates: list[str]) -> str:
    """
    Ask Ollama if raw_name matches any candidate.
    Returns the exact matching candidate string, or 'NEW'.
    """
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
                "prompt": (
                    "Match company names. Is this company the same legal entity "
                    "as any candidate below? Ignore suffixes like Inc, LLC, Corp.\n"
                    f"Company: {raw_name}\n"
                    "Candidates:\n" + "\n".join(f"- {c}" for c in candidates) + "\n"
                    "Reply with the exact matching candidate name, or 'NEW' if none match. "
                    "Only the name, nothing else."
                ),
                "stream": False,
                "options": {"temperature": 0, "num_predict": 60},
            },
            timeout=15,
        )
        return resp.json().get("response", "NEW").strip()
    except Exception:
        return "NEW"


def resolve_vendor(raw_name: str, existing: list[dict]) -> dict | None:
    """
    Match raw_name to an existing vendor. Returns vendor dict or None (→ create new).

    Three-tier matching (fast → heuristic → LLM):
    1. Exact or alias match
    2. Token Jaccard overlap ≥ 0.8
    3. Ollama fuzzy match (only if OLLAMA_RELEVANCE env var is set)
    """
    if not raw_name.strip():
        return None
    normalized = raw_name.lower().strip()

    for v in existing:
        if normalized == v["canonical_name"].lower():
            return v
        if any(normalized == a.lower() for a in (v.get("aliases") or [])):
            return v

    for v in existing:
        if _name_overlap(raw_name, v["canonical_name"]) >= 0.8:
            return v

    if existing and os.getenv("OLLAMA_RELEVANCE"):
        candidates = [v["canonical_name"] for v in existing[:30]]
        result = _ollama_match(raw_name, candidates)
        if result != "NEW":
            for v in existing:
                if v["canonical_name"].lower() == result.lower():
                    return v

    return None


# ---------------------------------------------------------------------------
# PlanetBids awarded bid scanning
# ---------------------------------------------------------------------------

async def _scan_awarded_portal(page, portal_id: str, agency: str) -> list[dict]:
    """
    Navigate to one PlanetBids portal and return all awarded bids via /papi/bids.
    Returns list of {portal_id, numeric_bid_id, title, agency}.
    """
    from urllib.parse import urlparse, parse_qs

    loop = asyncio.get_event_loop()
    captured: asyncio.Future = loop.create_future()

    async def on_response(response, cid=portal_id):
        if "/papi/bids" in response.url and not captured.done():
            params = parse_qs(urlparse(response.url).query)
            if params.get("cid", [""])[0] == cid:
                try:
                    data = await response.json()
                    captured.set_result(data)
                except Exception as exc:
                    if not captured.done():
                        captured.set_exception(exc)

    from scanner import _is_relevant

    portal_url = f"{PLANETBIDS_BASE}/portal/{portal_id}/bo/bo-search"
    page.on("response", on_response)

    try:
        await page.goto(portal_url, wait_until="domcontentloaded", timeout=30000)
        data = await asyncio.wait_for(captured, timeout=20)
        records = data.get("data", [])
    except asyncio.TimeoutError:
        print(f"      ⚠ Timed out waiting for /papi/bids — skipped")
        records = []
    except Exception as e:
        print(f"      ⚠ Portal error: {e}")
        records = []
    finally:
        page.remove_listener("response", on_response)

    total_awarded = 0
    awarded = []
    for rec in records:
        attrs = rec.get("attributes", {})
        if (attrs.get("stageStr") or "").lower() != "awarded":
            continue
        total_awarded += 1
        title = (attrs.get("title") or "").strip()
        if not title or not _is_relevant(title):
            continue
        awarded.append({
            "portal_id":      portal_id,
            "numeric_bid_id": str(rec.get("id", "")),
            "title":          title,
            "agency":         agency,
        })

    if total_awarded > 0:
        print(f"      {total_awarded} awarded total → {len(awarded)} flooring-relevant")

    return awarded


# ---------------------------------------------------------------------------
# Bid detail: submissions + award data
# ---------------------------------------------------------------------------

async def _fetch_bid_detail(page, portal_id: str, numeric_bid_id: str) -> dict:
    """
    Navigate to an awarded bid's detail page and extract submission tabulation
    and award data. Returns:
      {submissions, winner_name, winner_amount, awarded_at, total_bidders}

    Strategy:
    1. Try /portal/{id}/bo/bo-detail/{bid_id} URL
    2. Listen for all /papi/ API responses (captures submissions + awards endpoints)
    3. Click Submissions tab → click Awards tab to trigger lazy-loaded data
    4. Fall back to DOM table scraping if no API data captured
    """
    captured_api: dict[str, any] = {}

    async def on_response(response):
        url = response.url
        if "/papi/" in url:
            try:
                data = await response.json()
                # Key by the path segment after /papi/ for inspection
                key = url.split("/papi/")[-1].split("?")[0].rstrip("/")
                captured_api[key] = data
            except Exception:
                pass

    detail_url = f"{PLANETBIDS_BASE}/portal/{portal_id}/bo/bo-detail/{numeric_bid_id}"
    page.on("response", on_response)

    loaded = False
    try:
        await page.goto(detail_url, wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(2000)
        body = await page.inner_text("body")
        # A real detail page will mention the bid or have tab-like content
        if len(body) > 200 and ("submission" in body.lower() or "award" in body.lower() or "vendor" in body.lower() or "bid" in body.lower()):
            loaded = True
    except Exception as e:
        print(f"      ⚠ Detail page load error: {e}")

    if loaded:
        # Click Submissions tab to trigger lazy load
        for selector in [
            'button:has-text("Submissions")', 'a:has-text("Submissions")',
            '[data-tab*="submission" i]', '[id*="submission" i]',
            'li:has-text("Submissions")',
        ]:
            try:
                el = await page.query_selector(selector)
                if el:
                    await el.click()
                    await page.wait_for_timeout(2000)
                    break
            except Exception:
                pass

        # Click Awards tab
        for selector in [
            'button:has-text("Awards")', 'a:has-text("Awards")',
            '[data-tab*="award" i]', '[id*="award" i]',
            'li:has-text("Awards")',
        ]:
            try:
                el = await page.query_selector(selector)
                if el:
                    await el.click()
                    await page.wait_for_timeout(2000)
                    break
            except Exception:
                pass

    page.remove_listener("response", on_response)

    # --- Parse captured API data ---
    submissions = []
    winner_name = None
    winner_amount = None
    awarded_at = None

    # Log discovered endpoints for debugging (first run especially)
    if captured_api:
        print(f"      → API endpoints captured: {list(captured_api.keys())}")

    for key, data in captured_api.items():
        if not isinstance(data, dict):
            continue
        records = data.get("data", [])
        if not isinstance(records, list) or not records:
            continue

        first_attrs = (records[0].get("attributes", {}) if isinstance(records[0], dict) else {})

        # Submissions endpoint: records have vendor + amount fields
        vendor_fields = {"vendorName", "companyName", "company_name", "name", "vendorId"}
        amount_fields = {"bidAmount", "amount", "totalBid", "bidTotal", "totalAmount"}

        if vendor_fields & set(first_attrs.keys()) or amount_fields & set(first_attrs.keys()):
            for i, rec in enumerate(records):
                a = rec.get("attributes", {})
                vendor = (
                    a.get("vendorName") or a.get("companyName") or
                    a.get("company_name") or a.get("name") or ""
                ).strip()
                amount_raw = (
                    a.get("bidAmount") or a.get("amount") or
                    a.get("totalBid") or a.get("bidTotal") or a.get("totalAmount")
                )
                amount = _parse_amount(amount_raw)
                if vendor:
                    submissions.append({
                        "raw_vendor_name": vendor,
                        "bid_amount": amount,
                        "rank": i + 1,
                        "is_winner": False,
                    })

        # Awards endpoint: check for award date / winner fields
        award_fields = {"awardedTo", "winnerName", "winner", "awardDate", "awardedDate", "awardedAt"}
        if award_fields & set(first_attrs.keys()):
            a = first_attrs
            winner_name = (a.get("awardedTo") or a.get("winnerName") or a.get("winner") or "").strip() or winner_name
            raw_date = a.get("awardDate") or a.get("awardedDate") or a.get("awardedAt")
            if raw_date:
                awarded_at = _parse_award_date(str(raw_date))

        # Some portals embed award data inside the bid detail record
        if "stageStr" in first_attrs and first_attrs.get("stageStr", "").lower() == "awarded":
            a = first_attrs
            if not winner_name:
                winner_name = (a.get("awardedVendorName") or a.get("awardVendor") or "").strip() or None
            if not awarded_at:
                raw_date = a.get("awardDate") or a.get("awardedAt")
                if raw_date:
                    awarded_at = _parse_award_date(str(raw_date))

    # --- DOM fallback if no API data ---
    if not submissions and loaded:
        submissions, winner_name_dom, awarded_at_dom = await _scrape_detail_dom(page)
        if not winner_name:
            winner_name = winner_name_dom
        if not awarded_at:
            awarded_at = awarded_at_dom

    # Sort by amount to assign rank
    if submissions:
        with_amount = sorted(
            [s for s in submissions if s["bid_amount"] is not None],
            key=lambda s: s["bid_amount"],
        )
        no_amount = [s for s in submissions if s["bid_amount"] is None]
        for i, s in enumerate(with_amount):
            s["rank"] = i + 1
        submissions = with_amount + no_amount

        if with_amount:
            winner_amount = with_amount[0]["bid_amount"]
            with_amount[0]["is_winner"] = True
            if not winner_name:
                winner_name = with_amount[0]["raw_vendor_name"]

    return {
        "submissions":    submissions,
        "winner_name":    winner_name,
        "winner_amount":  winner_amount,
        "awarded_at":     awarded_at,
        "total_bidders":  len(submissions),
    }


async def _scrape_detail_dom(page) -> tuple[list[dict], str | None, str | None]:
    """
    DOM fallback: parse submissions table and awards text from page body.
    Returns (submissions, winner_name, awarded_at_str).
    """
    submissions = []
    winner_name = None
    awarded_at = None

    try:
        rows = await page.evaluate("""() => {
            const results = [];
            const selectors = [
                'table tbody tr',
                '[class*="submission"] tr',
                '[class*="bid-result"] tr',
                '[class*="bidder"] tr',
            ];
            for (const sel of selectors) {
                document.querySelectorAll(sel).forEach(tr => {
                    const cells = Array.from(tr.querySelectorAll('td'))
                        .map(td => td.innerText.trim());
                    if (cells.length >= 2) results.push(cells);
                });
                if (results.length > 0) break;
            }
            return results;
        }""")

        for row in rows:
            if len(row) < 2:
                continue
            vendor = row[0].split("\n")[0].strip()
            if len(vendor) < 3:
                continue
            amount = None
            for cell in row:
                m = re.search(r"\$?([\d,]+\.?\d*)", cell)
                if m:
                    try:
                        v = float(m.group(1).replace(",", ""))
                        if v > 100:
                            amount = v
                            break
                    except ValueError:
                        pass
            submissions.append({
                "raw_vendor_name": vendor,
                "bid_amount":      amount,
                "rank":            None,
                "is_winner":       False,
            })
    except Exception:
        pass

    try:
        body_text = await page.inner_text("body")
        m = re.search(r"[Aa]warded\s+to\s+([^\n]+)", body_text)
        if m:
            winner_name = m.group(1).strip()
        m2 = re.search(
            r"[Aa]warded\s+on\s+(\w+ \d+,\s*\d{4}|\d{1,2}/\d{1,2}/\d{4})",
            body_text,
        )
        if m2:
            awarded_at = _parse_award_date(m2.group(1).strip())
    except Exception:
        pass

    return submissions, winner_name, awarded_at


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_amount(raw) -> float | None:
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", "").replace("$", "").strip())
    except (ValueError, TypeError):
        return None


def _parse_award_date(s: str) -> str | None:
    """Parse various date formats to ISO date string."""
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip()[:19], fmt).date().isoformat()
        except ValueError:
            continue
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def run_intel_scan(live_page) -> dict:
    """
    Scan all PlanetBids portals for awarded bids, fetch submission tabulations,
    resolve vendor names, and persist to Supabase.

    Designed to be called after CAPTCHA is solved (reuses live browser session).
    Only processes bids not already in bid_intel (idempotent).
    """
    from scanner import PLANETBIDS_PORTALS
    from db import (
        fetch_all_vendors, upsert_vendor, add_vendor_alias,
        fetch_existing_intel_keys, upsert_intel_award,
    )

    print("\n" + "=" * 60)
    print("PLANETBIDS INTEL SCAN — awarded bids + submission tabulations")
    print("=" * 60)

    existing_vendors = fetch_all_vendors()
    existing_keys    = fetch_existing_intel_keys()
    print(f"\n  {len(existing_vendors)} vendors in DB | {len(existing_keys)} awards already processed\n")

    page = live_page
    new_awards = 0
    vendors_resolved = 0
    vendors_created = 0

    for portal_id, agency in PLANETBIDS_PORTALS.items():
        print(f"  → {agency}...")
        awarded_bids = await _scan_awarded_portal(page, portal_id, agency)

        new_for_portal = [
            b for b in awarded_bids
            if (b["portal_id"], b["numeric_bid_id"]) not in existing_keys
        ]

        if not new_for_portal:
            continue  # portal already printed counts if relevant awards existed

        print(f"      {len(new_for_portal)} new → fetching detail pages...")

        for bid in new_for_portal:
            print(f"        ↳ {bid['title'][:60]}")
            detail = await _fetch_bid_detail(page, portal_id, bid["numeric_bid_id"])

            # Resolve vendor names for all submissions
            resolved_subs = []
            for sub in detail.get("submissions", []):
                raw = sub["raw_vendor_name"]
                vendor = resolve_vendor(raw, existing_vendors)
                if vendor:
                    vendors_resolved += 1
                    aliases = vendor.get("aliases") or []
                    if raw.lower() not in [a.lower() for a in aliases]:
                        add_vendor_alias(vendor["id"], raw)
                        vendor.setdefault("aliases", []).append(raw)
                    vendor_id = vendor["id"]
                else:
                    vendor_id = upsert_vendor(raw)
                    vendors_created += 1
                    existing_vendors.append({
                        "id": vendor_id, "canonical_name": raw, "aliases": [],
                    })
                resolved_subs.append({**sub, "vendor_id": vendor_id})

            # Resolve winner vendor
            winner_name = detail.get("winner_name") or ""
            winner_vendor = resolve_vendor(winner_name, existing_vendors) if winner_name else None
            if winner_vendor:
                winner_vendor_id = winner_vendor["id"]
            elif winner_name:
                winner_vendor_id = upsert_vendor(winner_name)
                vendors_created += 1
                existing_vendors.append({
                    "id": winner_vendor_id, "canonical_name": winner_name, "aliases": [],
                })
            else:
                # Derive winner from rank=1 submission
                winner_sub = next(
                    (s for s in resolved_subs if s.get("is_winner") or s.get("rank") == 1),
                    None,
                )
                winner_vendor_id = winner_sub["vendor_id"] if winner_sub else None

            award = {
                "portal_id":        portal_id,
                "numeric_bid_id":   bid["numeric_bid_id"],
                "agency":           agency,
                "title":            bid["title"],
                "awarded_at":       detail.get("awarded_at"),
                "winner_vendor_id": winner_vendor_id,
                "winner_amount":    detail.get("winner_amount"),
                "total_bidders":    detail.get("total_bidders") or len(resolved_subs),
            }

            upsert_intel_award(award, resolved_subs)
            existing_keys.add((portal_id, bid["numeric_bid_id"]))
            new_awards += 1

    print(f"\n  ✓ {new_awards} new awards processed")
    print(f"  ✓ {vendors_resolved} vendor names resolved to existing records")
    print(f"  ✓ {vendors_created} new vendors created")

    return {
        "new_awards":       new_awards,
        "vendors_resolved": vendors_resolved,
        "new_vendors":      vendors_created,
    }
