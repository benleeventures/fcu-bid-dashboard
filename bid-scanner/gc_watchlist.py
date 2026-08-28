"""
FCU GC Watchlist — spec §7.

Everything else in the scanner surfaces work where FCU bids as prime. This
covers the other half: subcontract invitations from general contractors, which
arrive through completely different channels (GC plan rooms, not public portals).

This module does the "make sure invitations arrive" half only. Relationship
outreach to these GCs — the calls, the preconstruction meetings — stays with
Ben.

What it does:
  1. Seeds an Airtable "GC Watchlist" table with a starter target list
     (Tutor Perini first, per the spec).
  2. Harvests winning GC names from award data the intel scanner has already
     collected (`bid_intel`) — when a general-construction contract is awarded
     in the four counties, the winning GC needs flooring subs.

  python main.py --gc-watchlist        # seed + harvest + sync, no browser needed

Free channels only. Do not add anything that needs a paid subscription
(Dodge, ConstructConnect) — deliberately deferred.
"""

import os
import re
from datetime import date

try:
    from pyairtable import Api
    _AIRTABLE_AVAILABLE = True
except ImportError:
    _AIRTABLE_AVAILABLE = False

_TABLE_NAME = "GC Watchlist"
_table = None


# ---------------------------------------------------------------------------
# Seed list — GCs that do public / institutional work in the four counties.
# Plan room / contact left blank where unconfirmed; Robert verifies during
# registration. Counties are a best guess of where they're most active.
# ---------------------------------------------------------------------------

SEED_GCS = [
    {"name": "Tutor Perini Corporation",        "counties": ["Los Angeles", "Orange", "San Diego"], "plan_room": "Own portal"},
    {"name": "Balfour Beatty Construction",     "counties": ["Los Angeles", "San Diego"],           "plan_room": "iSqFt / BuildingConnected"},
    {"name": "McCarthy Building Companies",      "counties": ["Los Angeles", "Orange", "San Diego"], "plan_room": "iSqFt / BuildingConnected"},
    {"name": "Hensel Phelps",                   "counties": ["Los Angeles", "San Diego"],           "plan_room": "iSqFt / BuildingConnected"},
    {"name": "Bernards",                        "counties": ["Los Angeles", "Ventura"],             "plan_room": "iSqFt / BuildingConnected"},
    {"name": "PCL Construction Services",       "counties": ["Los Angeles", "San Diego"],           "plan_room": "SmartBid"},
    {"name": "Swinerton Builders",              "counties": ["Los Angeles", "Orange", "San Diego"], "plan_room": "iSqFt / BuildingConnected"},
    {"name": "Sundt Construction",              "counties": ["San Diego", "Los Angeles"],           "plan_room": "SmartBid"},
    {"name": "Turner Construction Company",     "counties": ["Los Angeles", "Orange", "San Diego"], "plan_room": "iSqFt / BuildingConnected"},
    {"name": "Clark Construction Group",        "counties": ["Los Angeles", "San Diego"],           "plan_room": "iSqFt / BuildingConnected"},
    {"name": "C.W. Driver Companies",           "counties": ["Los Angeles", "Orange"],              "plan_room": "iSqFt / BuildingConnected"},
    {"name": "Erickson-Hall Construction",      "counties": ["San Diego", "Orange"],                "plan_room": "SmartBid"},
    {"name": "Barnhart-Reese Construction",     "counties": ["San Diego"],                          "plan_room": "Unknown"},
    {"name": "Pinner Construction",             "counties": ["Los Angeles", "Orange"],              "plan_room": "Unknown"},
    {"name": "Lundgren Management",             "counties": ["Los Angeles", "Ventura"],             "plan_room": "Unknown"},
    {"name": "KPRS Construction Services",      "counties": ["Orange", "Los Angeles"],              "plan_room": "Unknown"},
    {"name": "2H Construction",                 "counties": ["Los Angeles"],                        "plan_room": "Unknown"},
    {"name": "USS Cal Builders",               "counties": ["Los Angeles"],                        "plan_room": "Unknown"},
    {"name": "Del Amo Construction",            "counties": ["Los Angeles"],                        "plan_room": "Unknown"},
    {"name": "FTR International",               "counties": ["Orange", "Los Angeles"],              "plan_room": "Unknown"},
]


# ---------------------------------------------------------------------------
# Is this award a general-construction package (→ the winner needs flooring subs)?
# ---------------------------------------------------------------------------

# Most building GCs don't have "construction" in their name (Tutor Perini,
# Bernards, Hensel Phelps, Swinerton…). So for award-notice harvesting the
# *title* does the filtering — the winner of a general-construction package is
# the GC by definition. We only screen out winners that are obviously a
# single-trade / civil contractor who won't be handing out flooring packages.
_NOT_A_BUILDING_GC = re.compile(
    r"\b(paving|asphalt|striping|seal ?coat|grading|excavat|landscap|"
    r"electric|roofing|plumbing|mechanical|\bHVAC\b|fenc(e|ing)|"
    r"demolition|abatement|concrete|masonry|glazing|painting|"
    r"tree service|irrigation|pipeline|utility|utilities|"
    r"engineering(?!.*\bconstruction\b))\b", re.I)

_GENERAL_CONSTRUCTION_TITLE = re.compile(
    r"\b(modernization|reconstruction|renovation|remodel|new (?:building|construction|campus)|"
    r"classroom building|gymnasium|multipurpose building|school building|"
    r"tenant improvement|\bTI\b|building improvement|facility improvement|"
    r"addition and renovation|whole[- ]site|campus improvement|"
    r"performing arts|science building|administration building|"
    r"aquatic center|community center|library building|fire station)\b", re.I)


def _looks_like_general_construction(title: str) -> bool:
    from scanner import _is_relevant
    if _is_relevant(title):          # flooring-primary — not a GC package for us
        return False
    return bool(_GENERAL_CONSTRUCTION_TITLE.search(title or ""))


def _looks_like_gc(vendor_name: str) -> bool:
    """Winner of a general-construction package, unless it's an obvious
    single-trade / civil contractor."""
    name = (vendor_name or "").strip()
    if len(name) < 3:
        return False
    return not _NOT_A_BUILDING_GC.search(name)


# ---------------------------------------------------------------------------
# Airtable
# ---------------------------------------------------------------------------

def _get_table():
    global _table
    if _table is not None:
        return _table
    key = os.getenv("AIRTABLE_API_KEY", "").strip()
    base_id = os.getenv("AIRTABLE_BASE_ID", "").strip()
    if not key or not base_id:
        return None
    if not _AIRTABLE_AVAILABLE:
        print("  ⚠ pyairtable not installed — run: pip install pyairtable")
        return None
    _table = Api(key).table(base_id, _TABLE_NAME)
    return _table


def sync_gc_watchlist(gcs: list[dict]) -> int:
    """
    Upsert GCs into the watchlist. Matches on "GC Name" — a GC already in the
    table is left untouched (Robert may have set Registered / Contact / etc.).
    `gcs` items: {name, counties?, plan_room?, source?, notes?}
    Returns count of new rows added.
    """
    table = _get_table()
    if not table or not gcs:
        return 0

    existing = {
        (r["fields"].get("GC Name") or "").strip().lower()
        for r in table.all(fields=["GC Name"])
    }

    to_create = []
    for gc in gcs:
        name = (gc.get("name") or "").strip()
        if not name or name.lower() in existing:
            continue
        existing.add(name.lower())
        fields = {
            "GC Name": name,
            "Source": gc.get("source", "Seed list"),
            "First Seen": date.today().isoformat(),
            "Registered": "No",
            "ITB Emails Arriving": "Not yet",
        }
        if gc.get("counties"):
            fields["Counties"] = gc["counties"]
        if gc.get("plan_room"):
            fields["Plan Room"] = gc["plan_room"]
        if gc.get("prequal"):
            fields["Prequal Required"] = gc["prequal"]
        if gc.get("notes"):
            fields["Notes"] = gc["notes"]
        to_create.append(fields)

    if not to_create:
        return 0

    _CORE = {"GC Name", "Source", "First Seen", "Registered", "ITB Emails Arriving"}
    for i in range(0, len(to_create), 10):
        batch = to_create[i:i + 10]
        try:
            table.batch_create(batch, typecast=True)
        except Exception as e:
            print(f"  ⚠ GC watchlist create failed ({e}); retrying with core fields")
            table.batch_create(
                [{k: v for k, v in r.items() if k in _CORE} for r in batch],
                typecast=True,
            )
    return len(to_create)


# ---------------------------------------------------------------------------
# Harvest GC winners from already-collected award data
# ---------------------------------------------------------------------------

def harvest_from_intel() -> list[dict]:
    """
    Scan Supabase bid_intel for general-construction awards in the four counties
    and return the winning GCs as watchlist candidates. Works off data the
    `--intel` scans have already collected — grows as more awards accumulate.
    """
    from db import get_client
    from geo import classify_location, FOUR_COUNTIES

    sb = get_client()
    if not sb:
        return []

    try:
        awards = sb.table("bid_intel").select(
            "id, agency, title, winner_vendor_id, url"
        ).execute().data or []
        subs = sb.table("bid_intel_submissions").select(
            "intel_id, vendor_id, raw_vendor_name, is_winner"
        ).execute().data or []
        vendors = {
            v["id"]: v["canonical_name"]
            for v in (sb.table("vendors").select("id, canonical_name").execute().data or [])
        }
    except Exception as e:
        print(f"  ⚠ harvest query error: {e}")
        return []

    winner_by_intel = {}
    for s in subs:
        if s.get("is_winner"):
            winner_by_intel[s["intel_id"]] = s.get("raw_vendor_name") or vendors.get(s.get("vendor_id"), "")

    out = {}
    for a in awards:
        title = a.get("title") or ""
        if not _looks_like_general_construction(title):
            continue
        winner = (
            winner_by_intel.get(a["id"])
            or vendors.get(a.get("winner_vendor_id"), "")
        ).strip()
        if not winner or not _looks_like_gc(winner):
            continue
        loc = classify_location(title, a.get("agency") or "")
        if loc["geo_status"] == "out":
            continue
        key = winner.lower()
        if key not in out:
            out[key] = {
                "name": winner,
                "counties": [loc["county"]] if loc["county"] in FOUR_COUNTIES else [],
                "source": "Award notice",
                "notes": f"Won: {title[:120]} ({a.get('agency','')})",
            }
    return list(out.values())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run() -> dict:
    print("=" * 60)
    print("FCU GC WATCHLIST — seed + harvest")
    print("=" * 60)

    seeded = sync_gc_watchlist(SEED_GCS)
    print(f"\n  Seed list: {seeded} new GC(s) added ({len(SEED_GCS)} in list)")

    harvested = harvest_from_intel()
    added = sync_gc_watchlist(harvested)
    print(f"  Award notices: {len(harvested)} GC(s) found in intel data, {added} new")

    total = seeded + added
    print(f"\n  ✓ {total} new row(s) on the GC Watchlist")
    return {"seeded": seeded, "harvested": len(harvested), "added": added}


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    run()
