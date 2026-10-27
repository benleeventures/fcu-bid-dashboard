"""
Tests for scanner.scope_tier and the not_flooring_item reject. Real titles
from the tracker, Aug–Oct 2026.

    python test_scope_tier.py
"""

import os

os.environ["ANTHROPIC_API_KEY"] = ""   # rule-based checks only

from scanner import _relevance_reason, scope_tier

CASES = {
    "package": [
        "Vista Continuation High School Modernization: Floor Coverings",
        "Vista Continuation High School Modernization: Concrete Floor Finishing and Epoxy Flooring",
        "Cal Poly Building 26 Graphic Arts Renovation Project - flooring",
        "Clean Energy Campus - Electrified Heating and Cooling Plant - Flooring (CSLB C15)",
        "Gladstone Lab Tenant Improvement - Carpet & Wood Flooring",
    ],
    "mixed": [
        "Lakeside MS - Paint & Flooring",
        "9 CS B2445 Carpet/Furniture/Asbestos",
        "Locker Room and Bathroom Flooring and Locker Replacement",
        "Central Kitchen Floor Resurfacing Project - General Construction",
        "Administrative Office 2nd Floor Renovations",
    ],
    "prime": [
        "Districtwide Flooring Phase 4",
        "DUARTE COMMUNITY CENTER CARPET REPLACEMENT",
        "Miramar - W Building Carpet Replacement",
        "Fire Station 43 - Apparatus Bay Resinous Flooring",
        "Job Order Contract - HDAE Carpet and Flooring Services",
        "BLDG. 380 – Carpet Replacement Sustainment Project",
        "Construction Services - Floor Replacement at Tsaile Health Center Pharmacy Department",
        "Flooring Abatement and Replacement",
        "J083--BUILDING 143 DIETETICS FLOORING RENOVATIONS SERVICE",
        "COUNTYWIDE CARPET CLEANING SERVICES",
        "UNIT PRICE FLOORING",
    ],
}

NOT_FLOORING_ITEMS = [
    "SOLENOID ASM - LOW FLOOR, ELECTRIC WHEELCHAIR RAMP, 24 VDC",
    "RAMP ASM - WHEELCHAIR, SELF-CON, 30 X 48, W/O FLOORING",
    "Floor Care Equipment Preventative Maintenance and Repair Services",
    "Fabricated Components for the SR Embedded Floor Plates",
]


def test_tiers():
    for tier, titles in CASES.items():
        for t in titles:
            assert scope_tier(t) == tier, (t, scope_tier(t), tier)


def test_not_flooring_items():
    for t in NOT_FLOORING_ITEMS:
        assert _relevance_reason(t) == "not_flooring_item", t
    assert _relevance_reason("Districtwide Flooring Phase 4") is None


if __name__ == "__main__":
    test_tiers()
    test_not_flooring_items()
    print("✓ scope tier tests pass")
