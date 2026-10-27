"""
Tests for the Phase 2 keyword list (Ben 2026-10-21) and SecureBids title /
county helpers.

    python test_spec_keywords.py
"""

import os

os.environ["ANTHROPIC_API_KEY"] = ""   # rule-based checks only

from scanner import _is_relevant, securebids_county, securebids_title

RELEVANT = [
    "31 FSS Dragon Gym Floor Refurbishment",
    "FLOOR COATING APPLICATION",
    "Historic Wood Floor Replacement",
    "Sheet Vinyl Replacement - Nurses Station",
    "Cove Base and VCT Replacement",
    "Resilient Flooring",
    "Luxury Vinyl Tile Install - Library",
    "Vista Continuation High School Modernization: Floor Coverings",
]

NOT_RELEVANT = [
    "Climate Resilient Infrastructure Study",     # "resilient" alone no longer matches
    "Salton Sea West Flood Resilience Study.",
    "Vinyl Fence Replacement",
]


def test_keywords():
    for t in RELEVANT:
        assert _is_relevant(t), t
    for t in NOT_RELEVANT:
        assert not _is_relevant(t), t


def test_securebids_title():
    assert securebids_title("07-26/27", "Request for Proposal - Geotechnical Services") \
        == "07-26/27 — Request for Proposal - Geotechnical Services"
    assert securebids_title("Districtwide Flooring Phase 4", "anything") == "Districtwide Flooring Phase 4"
    assert securebids_title("", "Carpet Replacement") == "Carpet Replacement"


def test_securebids_county():
    assert securebids_county("CA - Los Angeles") == "Los Angeles"
    assert securebids_county("CA - Kern") == "Kern"
    assert securebids_county("CA - Sonoma") is None
    assert securebids_county(None) is None


if __name__ == "__main__":
    test_keywords()
    test_securebids_title()
    test_securebids_county()
    print("✓ spec keyword tests pass")
