"""
Tests for the daily-email feed hardening and the missing-migration guard.

    python test_feed_hardening.py
"""

from datetime import date, datetime, timezone

import db
import notify
from notify import build_feed_digest, prepare_feed

NOW = datetime(2026, 10, 28, 14, 0, tzinfo=timezone.utc)


def _row(bid_id, title, **kw):
    return {"bid_id": bid_id, "title": title, "agency": "", "source": "BidNet Direct",
            "geo_status": "in", "region": "North", "county": "Los Angeles",
            "due_date": "2026-11-10", "bid_status": "active",
            "first_seen_at": "2026-10-20T13:00:00+00:00",
            "last_seen_at": "2026-10-28T13:00:00+00:00", **kw}


def test_same_bid_on_two_sources_collapses_to_richest():
    rows = [
        _row("BN-1", "DUARTE COMMUNITY CENTER CARPET REPLACEMENT", geo_status="unknown", region=None),
        _row("VL-1", "Duarte Community Center Carpet Replacement", source="VendorLine",
             agency="City of Duarte"),
    ]
    out = prepare_feed(rows, {}, NOW)
    assert [r["bid_id"] for r in out] == ["VL-1"]      # the in-area row wins


def test_stale_no_due_date_bid_dropped():
    rows = [
        _row("A", "Flooring A", due_date=None, last_seen_at="2026-10-20T13:00:00+00:00"),
        _row("B", "Flooring B", due_date=None, last_seen_at="2026-10-27T13:00:00+00:00"),
        _row("C", "Flooring C", last_seen_at="2026-10-01T13:00:00+00:00"),   # has a due date
    ]
    assert sorted(r["bid_id"] for r in prepare_feed(rows, {}, NOW)) == ["B", "C"]


def test_closed_and_out_of_area_dropped():
    rows = [_row("A", "Flooring A", bid_status="no_bid"), _row("B", "Flooring B", geo_status="out")]
    assert prepare_feed(rows, {}, NOW) == []


def test_walk_wording():
    rows = [
        _row("A", "Flooring A"),                                      # nothing read
        _row("B", "Flooring B", location_raw="Los Angeles County"),   # BidNet detail read, no walk
        _row("C", "Flooring C"),                                      # docs parsed, no walk
    ]
    specs = {"C": {"bid_id": "C", "walk_required": False, "walk_date": None}}
    feed = {r["bid_id"]: r for r in prepare_feed(rows, specs, NOW)}
    assert feed["A"]["walk_checked"] is False
    assert feed["B"]["walk_checked"] is True and feed["C"]["walk_checked"] is True
    _, html = build_feed_digest(list(feed.values()), set(), today=date(2026, 10, 28))
    assert html.count("Job walk: not checked yet") == 1
    assert html.count("No job walk listed") == 2     # B and C were checked, no walk found


def test_spec_walk_merged():
    rows = [_row("A", "Flooring A")]
    specs = {"A": {"bid_id": "A", "walk_required": True, "walk_date": "2026-10-30"}}
    r = prepare_feed(rows, specs, NOW)[0]
    assert (r["walk_date"], r["walk_mandatory"], r["walk_checked"]) == ("2026-10-30", True, True)


def test_missing_columns_skipped_on_write():
    db._missing_columns = {"walk_date", "walk_mandatory", "description"}
    row = {k: v for k, v in db._serialize_bid({"bid_id": "X", "title": "t", "walk_date": date(2026, 11, 1)}).items()
           if k not in db.missing_bid_columns()}
    assert "walk_date" not in row and "description" not in row and row["bid_id"] == "X"
    assert db.migration_warning() == "DB migration not applied: supabase/add_listing_details.sql"
    db._missing_columns = None


if __name__ == "__main__":
    test_same_bid_on_two_sources_collapses_to_richest()
    test_stale_no_due_date_bid_dropped()
    test_closed_and_out_of_area_dropped()
    test_walk_wording()
    test_spec_walk_merged()
    test_missing_columns_skipped_on_write()
    print("✓ feed hardening tests pass")
