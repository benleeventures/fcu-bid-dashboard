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
