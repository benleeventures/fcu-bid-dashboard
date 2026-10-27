"""
Tests for Phase 2 geo: Kern in scope, North/South region, school-district /
college / neighborhood lookups. Cases are real tracker rows, Oct 2026.

    python test_geo_region.py
"""

from geo import classify_location, enrich, region_for, school_district_county, drive_band

# (title, agency) -> (geo_status, county)
CASES = [
    # Kern now in scope (was "out")
    ("Vista Continuation High School Modernization: Floor Coverings", "Kern High School District", ("in", "Kern")),
    ("East Bakersfield High School: Building 200 Ceiling Abatement", "", ("in", "Kern")),
    ("Minor B - Kern County - Remove and replace radio vault", "", ("in", "Kern")),
    # school districts resolved through the CDE directory
    ("DW 2026-09-22 UNIT BID FLOORING SERVICES DISTRICTWIDE", "Sulphur Springs Union School District", ("in", "Los Angeles")),
    ("Lakeside MS - Paint & Flooring", "Little Lake City School District", ("in", "Los Angeles")),
    ("JUSD Rustic Lane ES Modernization", "Jurupa Unified School District", ("in", "Riverside")),
    ("OPUSD DISTRICTWIDE LANDSCAPING MAINTENANCE", "Oak Park Unified School District", ("in", "Ventura")),
    ("Districtwide Flooring Phase 4", "Rialto Unified School District", ("in", "San Bernardino")),
    # out-of-area districts now dropped instead of "unknown"
    ("NORTHLAKE TK-8 SCHOOL CONCRETE WALKWAY REPLACEMENT", "Twin Rivers Unified School District", ("out", None)),
    ("Locker Room Building", "Mt. Diablo Unified School District", ("out", None)),
    # district named only in the title (BidNet rows carry no agency)
    ("Carpet Replacement - El Monte Union High School District", "", ("in", "Los Angeles")),
    # colleges / universities
    ("RFQ - UNIVERSITY LIBRARY EGRESS STAIR, California State University, Northridge", "", ("in", "Los Angeles")),
    ("Ronald Reagan UCLA Medical Center 4th Floor Reconfiguration", "", ("in", "Los Angeles")),
    ("Roofing Replacement for Buildings 31, 54, & 70", "Victor Valley Community College District", ("in", "San Bernardino")),
    ("Miramar - W Building Carpet Replacement", "San Diego Community College District", ("in", "San Diego")),
    # still genuinely unknown
    ("UNIT PRICE FLOORING", "", ("unknown", None)),
    ("District-wide Flooring Replacement", "Springfield School District", ("unknown", None)),
    # existing behaviour unchanged
    ("Flooring Replacement at City Hall", "City of Los Angeles", ("in", "Los Angeles")),
    ("Carpet Install", "City of Sacramento", ("out", None)),
    ("Flooring", "City of Fresno", ("out", None)),
]


def test_cases():
    for title, agency, expected in CASES:
        loc = classify_location(title, agency, "California")
        assert (loc["geo_status"], loc["county"]) == expected, (title, agency, loc)


def test_region():
    assert [region_for(c) for c in ("Los Angeles", "Ventura", "Kern")] == ["North"] * 3
    assert [region_for(c) for c in ("Orange", "Riverside", "San Bernardino", "San Diego")] == ["South"] * 4
    assert region_for(None) is None and region_for("Fresno") is None
    assert enrich({"title": "Flooring", "agency": "Kern High School District"})["region"] == "North"
    assert enrich({"title": "Flooring", "agency": "Anaheim Union High School District"})["region"] == "South"
    assert enrich({"title": "UNIT PRICE FLOORING", "agency": ""})["region"] is None


def test_school_district_lookup():
    assert school_district_county("Bakersfield City School District") == "Kern"
    assert school_district_county("Delano Joint Union High School District") == "Kern"
    assert school_district_county("Pasadena USD") == "Los Angeles"
    assert school_district_county("Sacramento City Unified School District") == "Sacramento"
    assert school_district_county("City of Pasadena") is None


def test_kern_drive_band():
    assert drive_band(None, "Kern") == "D"


if __name__ == "__main__":
    test_cases()
    test_region()
    test_school_district_lookup()
    test_kern_drive_band()
    print("✓ geo region tests pass")
