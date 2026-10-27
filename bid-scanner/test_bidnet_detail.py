"""
Tests for scanner.parse_bidnet_detail — text of real logged-in BidNet detail
pages (2026-10-27), trimmed to the parts the parser reads.

    python test_bidnet_detail.py
"""

from datetime import date

from geo import enrich
from scanner import parse_bidnet_detail

# UCSB job-order contract: mandatory prebid, Santa Barbara County (out of area)
HDAE = """Job Order Contract - HDAE Carpet and Flooring Services
Source ID
SCRIBE
Details
Location
Santa Barbara County
Purchase Type
Not Stated
Dates
Publication
10/26/2026 06:42 AM PDT
Closing Date
11/17/2026 03:30 PM PST
Prebid Conference
10/29/2026 01:30 PM PDT
Contact Information
Ashley Cohen Gray
ashleycohen@ucsb.edu
Description
The JOC Agreement is an indefinite quantity/indefinite delivery contract.
See more
For more information on this solicitation, please click on the following link:
Buyer Preferences, Guidelines & Requirements
General Requirements
-Bid Bond Required
Pre-Bidding Events
Event Type
Prebid Conference
Attendance
Mandatory
Event date
10/29/2026 01:30 PM PDT
Disclaimer""".split("\n")

# Grossmont UHSD unit-price flooring: San Diego County, no pre-bid event
UNIT_PRICE = """UNIT PRICE FLOORING
Source ID
SCRIBE
Details
Location
San Diego County
Purchase Type
Not Stated
Dates
Publication
10/27/2026 04:23 AM PDT
Closing Date
11/18/2026 02:00 PM PST
Contact Information
Rian Pinson
619-644-8051
rpinson@guhsd.net
Description
SCOPE: Scope will be on an as needed for Districtwide Flooring for approximately one year.
Buyer Preferences, Guidelines & Requirements
Disclaimer""".split("\n")


def test_hdae():
    d = parse_bidnet_detail(HDAE)
    assert d["location"] == "Santa Barbara County"
    assert d["walk_date"] == date(2026, 10, 29)
    assert d["walk_mandatory"] is True
    assert d["contact_email"] == "ashleycohen@ucsb.edu"
    assert d["description"].startswith("The JOC Agreement")
    b = enrich({"title": "Job Order Contract - HDAE Carpet and Flooring Services",
                "agency": "", "pop_raw": d["location"]})
    assert b["geo_status"] == "out"


def test_unit_price():
    d = parse_bidnet_detail(UNIT_PRICE)
    assert d["location"] == "San Diego County"
    assert d["walk_date"] is None and d["walk_mandatory"] is None
    assert d["contact_email"] == "rpinson@guhsd.net"
    assert "Districtwide Flooring" in d["description"]
    b = enrich({"title": "UNIT PRICE FLOORING", "agency": "", "pop_raw": d["location"]})
    assert (b["geo_status"], b["county"], b["region"]) == ("in", "San Diego", "South")


def test_statewide_location_stays_unknown():
    d = parse_bidnet_detail(["Location", "California", "Description", "Carpet"])
    b = enrich({"title": "Carpet Replacement", "agency": "", "pop_raw": d["location"]})
    assert b["geo_status"] == "unknown"


if __name__ == "__main__":
    test_hdae()
    test_unit_price()
    test_statewide_location_stays_unknown()
    print("✓ BidNet detail tests pass")
