"""
FCU Bid Scanner — Supabase persistence layer.

Writes scan results to Supabase. Handles upserts (new bids inserted,
existing bids get last_seen_at updated). Logs each scan run.
"""

import os
import time
from datetime import date, datetime

try:
    from supabase import create_client, Client
    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False

_client = None


def get_client():
    global _client
    if _client:
        return _client
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        return None
    if not _SUPABASE_AVAILABLE:
        print("  ⚠ supabase package not installed — run: pip install supabase")
        return None
    _client = create_client(url, key)
    return _client


def _serialize_bid(bid: dict) -> dict:
    """Convert scanner bid dict to Supabase row format."""
    def _date_str(d):
        if isinstance(d, date):
            return d.isoformat()
        return d or None

    return {
        "bid_id":         bid.get("bid_id", ""),
        "title":          bid.get("title", "")[:500],
        "agency":         (bid.get("agency") or "")[:200],
        "state":          bid.get("state", "California"),
        "source":         bid.get("source", ""),
        "published_date": _date_str(bid.get("published_date")),
        "due_date":       _date_str(bid.get("due_date")),
        "due_date_raw":   (bid.get("due_date_raw") or "")[:100],
        "published_raw":  (bid.get("published_raw") or "")[:100],
        "url":            (bid.get("url") or "")[:1000],
        "is_relevant":    bool(bid.get("is_relevant", False)),
        "search_keyword": (bid.get("search_keyword") or "")[:100],
    }


def upsert_bids(bids: list[dict]) -> tuple[int, int]:
    """
    Upsert bids into Supabase.
    Returns (new_count, updated_count).
    """
    sb = get_client()
    if not sb:
        return 0, 0

    if not bids:
        return 0, 0

    rows = [_serialize_bid(b) for b in bids if b.get("bid_id")]

    # Fetch existing bid_ids to distinguish new vs updated
    existing_ids = set()
    try:
        chunk_size = 200
        for i in range(0, len(rows), chunk_size):
            chunk_ids = [r["bid_id"] for r in rows[i:i+chunk_size]]
            resp = sb.table("bids").select("bid_id").in_("bid_id", chunk_ids).execute()
            existing_ids.update(r["bid_id"] for r in (resp.data or []))
    except Exception as e:
        print(f"  ⚠ DB fetch error: {e}")

    new_ids = {r["bid_id"] for r in rows if r["bid_id"] not in existing_ids}
    new_rows = [r for r in rows if r["bid_id"] in new_ids]
    updated_rows = [r for r in rows if r["bid_id"] in existing_ids]

    # Tag originals with _is_new so main.py can filter them for notifications
    for b in bids:
        b["_is_new"] = b.get("bid_id") in new_ids

    # Insert new bids
    new_count = 0
    if new_rows:
        try:
            chunk_size = 100
            for i in range(0, len(new_rows), chunk_size):
                sb.table("bids").insert(new_rows[i:i+chunk_size]).execute()
            new_count = len(new_rows)
        except Exception as e:
            print(f"  ⚠ DB insert error: {e}")

    # Update last_seen_at for existing bids
    updated_count = 0
    if updated_rows:
        try:
            now = datetime.utcnow().isoformat()
            chunk_size = 100
            for i in range(0, len(updated_rows), chunk_size):
                ids = [r["bid_id"] for r in updated_rows[i:i+chunk_size]]
                sb.table("bids").update({"last_seen_at": now}).in_("bid_id", ids).execute()
            updated_count = len(updated_rows)
        except Exception as e:
            print(f"  ⚠ DB update error: {e}")

    return new_count, updated_count


def fetch_undigested_opengov() -> list[dict]:
    """
    Return OpenGov bids saved during a manual run that haven't been
    included in a scheduled digest yet (digested_at IS NULL).
    """
    sb = get_client()
    if not sb:
        return []
    try:
        resp = (
            sb.table("bids")
            .select("*")
            .eq("source", "OpenGov")
            .is_("digested_at", "null")
            .execute()
        )
        return resp.data or []
    except Exception as e:
        print(f"  ⚠ DB fetch undigested OpenGov error: {e}")
        return []


def fetch_undigested_planetbids() -> list[dict]:
    """
    Return PlanetBids bids saved during a manual run that haven't been
    included in a scheduled digest yet (digested_at IS NULL).
    """
    sb = get_client()
    if not sb:
        return []
    try:
        resp = (
            sb.table("bids")
            .select("*")
            .eq("source", "PlanetBids")
            .is_("digested_at", "null")
            .execute()
        )
        return resp.data or []
    except Exception as e:
        print(f"  ⚠ DB fetch undigested error: {e}")
        return []


def mark_digested(bid_ids: list[str]):
    """Mark bids as included in a digest so they aren't re-sent."""
    sb = get_client()
    if not sb or not bid_ids:
        return
    try:
        now = datetime.utcnow().isoformat()
        chunk_size = 100
        for i in range(0, len(bid_ids), chunk_size):
            sb.table("bids").update({"digested_at": now}).in_(
                "bid_id", bid_ids[i:i + chunk_size]
            ).execute()
    except Exception as e:
        print(f"  ⚠ DB mark digested error: {e}")


def log_scan(total: int, relevant: int, new_bids: int, sources: dict, duration_secs: float):
    """Write a scan run record to scan_log."""
    sb = get_client()
    if not sb:
        return
    try:
        sb.table("scan_log").insert({
            "total_found":    total,
            "relevant_found": relevant,
            "new_bids":       new_bids,
            "sources":        sources,
            "duration_secs":  round(duration_secs, 1),
        }).execute()
    except Exception as e:
        print(f"  ⚠ DB scan log error: {e}")


# ---------------------------------------------------------------------------
# Competitive Intelligence — vendors + bid_intel + bid_intel_submissions
# ---------------------------------------------------------------------------

def fetch_all_vendors() -> list[dict]:
    """Return all vendor records for name resolution."""
    sb = get_client()
    if not sb:
        return []
    try:
        resp = sb.table("vendors").select("id, canonical_name, aliases").execute()
        return resp.data or []
    except Exception as e:
        print(f"  ⚠ DB fetch vendors error: {e}")
        return []


def upsert_vendor(canonical_name: str) -> str:
    """
    Insert a new vendor (or return existing on conflict).
    Returns the vendor's UUID.
    """
    sb = get_client()
    if not sb:
        return ""
    try:
        resp = (
            sb.table("vendors")
            .upsert({"canonical_name": canonical_name}, on_conflict="canonical_name")
            .execute()
        )
        return (resp.data or [{}])[0].get("id", "")
    except Exception as e:
        print(f"  ⚠ DB upsert vendor error: {e}")
        return ""


def add_vendor_alias(vendor_id: str, alias: str):
    """Append a new raw name variant to vendors.aliases[]."""
    sb = get_client()
    if not sb or not vendor_id:
        return
    try:
        # Fetch current aliases first to avoid duplicates
        resp = sb.table("vendors").select("aliases").eq("id", vendor_id).single().execute()
        current = resp.data.get("aliases") or []
        if alias.lower() not in [a.lower() for a in current]:
            current.append(alias)
            sb.table("vendors").update({"aliases": current}).eq("id", vendor_id).execute()
    except Exception as e:
        print(f"  ⚠ DB add vendor alias error: {e}")


def fetch_existing_intel_keys() -> set[tuple[str, str]]:
    """Return set of (portal_id, numeric_bid_id) already in bid_intel."""
    sb = get_client()
    if not sb:
        return set()
    try:
        resp = sb.table("bid_intel").select("portal_id, numeric_bid_id").execute()
        return {(r["portal_id"], r["numeric_bid_id"]) for r in (resp.data or [])}
    except Exception as e:
        print(f"  ⚠ DB fetch intel keys error: {e}")
        return set()


def upsert_intel_award(award: dict, submissions: list[dict]):
    """
    Upsert one bid_intel row and replace its bid_intel_submissions.
    award keys: portal_id, numeric_bid_id, agency, title, awarded_at,
                winner_vendor_id, winner_amount, total_bidders
    submission keys: vendor_id, raw_vendor_name, bid_amount, is_winner, rank
    """
    sb = get_client()
    if not sb:
        return

    try:
        now = datetime.utcnow().isoformat()
        resp = (
            sb.table("bid_intel")
            .upsert(
                {**award, "last_synced_at": now},
                on_conflict="portal_id,numeric_bid_id",
            )
            .execute()
        )
        intel_id = (resp.data or [{}])[0].get("id")
        if not intel_id:
            return

        if submissions:
            # Replace existing submissions for this bid
            sb.table("bid_intel_submissions").delete().eq("intel_id", intel_id).execute()
            rows = [
                {
                    "intel_id":        intel_id,
                    "vendor_id":       s.get("vendor_id"),
                    "raw_vendor_name": s.get("raw_vendor_name", "")[:300],
                    "bid_amount":      s.get("bid_amount"),
                    "is_winner":       bool(s.get("is_winner", False)),
                    "rank":            s.get("rank"),
                }
                for s in submissions
            ]
            sb.table("bid_intel_submissions").insert(rows).execute()

    except Exception as e:
        print(f"  ⚠ DB upsert intel award error: {e}")
