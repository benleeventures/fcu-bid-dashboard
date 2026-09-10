"""Tests for the VendorLine competitive-intel discovery filter.

`_vl_awarded_row` is the pure mapping/skip logic behind `_vendorline_awarded`.
Fixture rows match the real `POST /api/search` shape (stages [4,5,6,7], CA)
captured from live probes.
"""
from scanner import _vl_awarded_row, _parse_date

CUTOFF = _parse_date("2025-09-10")


def _row(**over):
    base = {
        "bid_id": "139164", "bid_source": 0, "company_id": 25796,
        "posted_date": "2026-03-25T00:00:00", "due_date": "2026-04-29",
        "project": "Campus-Wide Carpet Replacement",
        "agency": "San Diego State University", "invitation": "7076", "stage_id": 5,
    }
    base.update(over)
    return base


def test_keeps_planetbids_native_flooring():
    b = _vl_awarded_row(_row(), CUTOFF)
    assert b is not None
    assert b["portal_id"] == "25796"
    assert b["numeric_bid_id"] == "139164"
    assert b["stage_id"] == 5
    assert b["url"].endswith("/portal/25796/bo/bo-detail/139164")
    assert b["posted_date"] == "2026-03-25"


def test_drops_external_aggregate():
    # bid_source 1 rows have no company_id and no PlanetBids detail page
    assert _vl_awarded_row(_row(bid_source=1, company_id=None, invitation=None), CUTOFF) is None


def test_drops_missing_company_id():
    assert _vl_awarded_row(_row(company_id=None), CUTOFF) is None


def test_drops_before_cutoff():
    assert _vl_awarded_row(_row(posted_date="2019-03-11T00:00:00"), CUTOFF) is None


def test_drops_non_flooring():
    assert _vl_awarded_row(_row(project="HVAC Rooftop Unit Replacement"), CUTOFF) is None


def test_drops_blank_title():
    assert _vl_awarded_row(_row(project="   "), CUTOFF) is None


def test_no_cutoff_keeps_old():
    assert _vl_awarded_row(_row(posted_date="2019-03-11T00:00:00"), None) is not None


def test_dedup_in_vendorline_awarded_shape():
    # two keyword hits for the same bid collapse on (portal_id, numeric_bid_id)
    rows = [_row(), _row(project="Carpet & Resilient Flooring Replacement")]
    seen = {}
    for r in rows:
        b = _vl_awarded_row(r, CUTOFF)
        seen.setdefault(f"{b['portal_id']}-{b['numeric_bid_id']}", b)
    assert len(seen) == 1


if __name__ == "__main__":
    import sys
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
