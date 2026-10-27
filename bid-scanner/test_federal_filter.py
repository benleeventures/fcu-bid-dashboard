"""
Tests for the federal cut (Phase 2): geo.is_federal, the SAM.gov
place-of-performance mapping, and scanner.apply_federal_policy.

    python test_federal_filter.py
"""

from geo import is_federal, enrich
from scanner import samgov_pop_fields, apply_federal_policy

# (title, agency, bid_id) — real rows from the tracker, Oct 2026
FEDERAL = [
    ("Z2DA--612A4-27-018 | Replace B650 3rd and 2nd Flooring", "", "BN-1"),
    ("FY27 NRM Replace Flooring in McClellan VA Northern California Health Care System", "", ""),
    ("Request for Information: Multiple Projects at Vandenberg SFB", "", ""),
    ("Sole Source - Test Parachutist Program Edwards AFB FY27", "", ""),
    ("Replace Operating Room 5 Flooring", "VETERANS AFFAIRS, DEPARTMENT OF", "SAM-36C26327Q0019"),
    ("Install flooring", "DEPT OF DEFENSE", "SAM-W912HQ26PA083"),
    ("CONSTRUCTION - NUWCDIVNPT: Raised Flooring Replacement", "", "SAM-N6660427P0029"),
    ("Flooring IDR Pre-Solicitation Notice", "", "SAM-FA465926Q0003"),
    ("DHS HSI Schwartz 2nd Floor Carpet Replacement", "", "SAM-47PD5527Q0010"),
    ("UNITED STATES COAST GUARD KETCHIKAN ALASKA NEW CARPET INSTALLATION", "", ""),
    ("Carpet Replacement Building 12", "US Army Corps of Engineers", ""),
]

NOT_FEDERAL = [
    # Miramar College (San Diego CCD) — not MCAS Miramar
    ("Miramar - W Building Carpet Replacement", "San Diego Community College District", "VL-1"),
    ("DUARTE COMMUNITY CENTER CARPET REPLACEMENT", "City of Duarte", ""),
    ("Districtwide Flooring Phase 4", "Rialto Unified School District", ""),
    ("Flooring Replacement", "California Department of Transportation", ""),
    ("Carpet Replacement", "Department of General Services", ""),
    ("Janet Goeske Senior Center Floor Covering Replacement (CDBG)", "", ""),
    ("Job Order Contract - HDAE Carpet and Flooring Services", "", ""),
    ("Vista Continuation High School Modernization: Floor Coverings", "Kern High School District", ""),
    ("RFQ # R-27016 - 107TH STREET ELEMENTARY", "LAUSD", ""),
]


def test_is_federal():
    for title, agency, bid_id in FEDERAL:
        assert is_federal(title, agency, bid_id), f"should be federal: {title!r}"
    for title, agency, bid_id in NOT_FEDERAL:
        assert not is_federal(title, agency, bid_id), f"false positive: {title!r}"


def _sam_bid(title, pop):
    b = {"source": "SAM.gov", "title": title, "agency": "DEPT OF DEFENSE", "bid_id": "SAM-X"}
    b.update(samgov_pop_fields(pop))
    return enrich(b)


def test_samgov_pop_mapping():
    # out of state
    assert _sam_bid("Carpet", {"city": "Ketchikan", "state": "AK", "zip": "99901"})["geo_status"] == "out"
    # no state, non-CA ZIP (Maryland ANG — real case)
    assert _sam_bid("Epoxy", {"city": "", "state": "", "zip": "21220"})["geo_status"] == "out"
    # in-area city
    b = _sam_bid("Carpet", {"city": "San Diego", "state": "CA", "zip": "92101"})
    assert (b["geo_status"], b["county"]) == ("in", "San Diego")
    # in-area base whose PoP city isn't an incorporated city
    b = _sam_bid("Flooring", {"city": "Camp Pendleton", "state": "CA", "zip": "92055"})
    assert (b["geo_status"], b["county"]) == ("in", "San Diego")
    # CA but outside the area
    assert _sam_bid("Flooring", {"city": "Sacramento", "state": "CA", "zip": "95814"})["geo_status"] == "out"
    assert samgov_pop_fields(None) == {}


def test_apply_federal_policy():
    bids = [
        {"source": "SAM.gov", "title": "a", "agency": "", "geo_status": "in"},
        {"source": "SAM.gov", "title": "b", "agency": "", "geo_status": "unknown"},
        {"source": "BidNet Direct", "title": "Z2DA--612A4-27-018 Flooring", "agency": "", "geo_status": "unknown"},
        {"source": "BidNet Direct", "title": "UNIT PRICE FLOORING", "agency": "", "geo_status": "unknown"},
        {"source": "VendorLine", "title": "Miramar - W Building Carpet Replacement",
         "agency": "San Diego Community College District", "geo_status": "in"},
    ]
    apply_federal_policy(bids)
    assert [b["geo_status"] for b in bids] == ["in", "out", "out", "unknown", "in"]


if __name__ == "__main__":
    test_is_federal()
    test_samgov_pop_mapping()
    test_apply_federal_policy()
    print("✓ federal filter tests pass")
