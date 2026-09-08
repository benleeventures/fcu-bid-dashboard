"""
Unit tests for the relevance filter after Ben's 2026-09 correction:
FCU wholesales flooring/window product (with or without install) AND takes
floor-care maintenance contracts. Only services with no floor-covering
component (janitorial / pest / landscaping / glass washing) are filtered out.

    python test_relevance_filter.py
"""

from scanner import _is_non_flooring_service, _is_relevant

# Wholesale supply / furnish-only — now legitimate FCU work.
SUPPLY_ONLY = [
    ("Furnish and Deliver Carpet Tile", ""),
    ("Flooring Materials - Supply Only", ""),
    ("Carpet Replacement - Materials Only, installation by others", ""),
    ("Supply and deliver resilient flooring; no labor", ""),
    ("Purchase of flooring; installation not included", ""),
]

# Floor / window-covering maintenance — now legitimate FCU work.
FLOORING_SERVICE = [
    ("Strip and Wax VCT Floors - Quarterly", ""),
    ("Carpet Cleaning Services, NPS-CRLA", ""),
    ("Carpet Extraction and Steam Cleaning", ""),
    ("Floor Refinishing - Gymnasium Wood Floor", ""),
    ("On-Call Flooring Repair Services", ""),
    ("Blind Cleaning and Repair - District Wide", ""),
]

# Real install jobs — always were relevant.
INSTALL_JOBS = [
    ("Gymnasium Floor Replacement", ""),
    ("Furnish and Install VCT Flooring", ""),
    ("Carpet purchase and installation for City Hall", ""),
    ("District-wide Flooring Replacement (turnkey)", ""),
]

# Services with no floor-covering component — still filtered out.
NON_FLOORING_SERVICE = [
    ("Janitorial and Custodial Services", ""),
    ("Det. 218 OSI B5710 Carpet/Furniture/Pest Control", ""),
    ("Pest Control and Extermination Contract", ""),
    ("Landscape Maintenance - Parks Division", ""),
    ("Exterior Window Washing Services", ""),
]

# "steam" / "spot cleaning" without a carpet anchor — pavement / kitchen / HVAC
# work, not floor covering. Must NOT be relevant.
NOT_RELEVANT_NO_ANCHOR = [
    ("Parking Lot Steam Cleaning", ""),
    ("Kitchen Hood Steam Cleaning Services", ""),
    ("Parking Spot Cleaning and Restriping", ""),
]

# Flooring incidental to a larger multi-trade scope — not a keyword match, and
# the Claude second pass (when enabled) should say NO. Without an API key the
# fast path returns False anyway.
NOT_PRIMARY = [
    ("Aquatic Center Improvements", ""),
    ("Restroom Rehabilitation - Building 4", ""),
]


def run():
    fails = 0

    for title, desc in SUPPLY_ONLY + FLOORING_SERVICE + INSTALL_JOBS:
        if not _is_relevant(title, desc):
            print(f"FAIL (should be relevant): {title!r}")
            fails += 1
        if _is_non_flooring_service(title, desc):
            print(f"FAIL (should NOT be non-flooring-service): {title!r}")
            fails += 1

    for title, desc in NON_FLOORING_SERVICE:
        if _is_relevant(title, desc):
            print(f"FAIL (should NOT be relevant): {title!r}")
            fails += 1
        if not _is_non_flooring_service(title, desc):
            print(f"FAIL (should be non-flooring-service): {title!r}")
            fails += 1

    for title, desc in NOT_RELEVANT_NO_ANCHOR:
        if _is_relevant(title, desc):
            print(f"FAIL (should NOT be relevant — no carpet anchor): {title!r}")
            fails += 1

    # The fast path never keyword-matches these; the Claude second pass decides.
    # Only assert when no API key is configured (fast path returns False).
    import os
    if not os.getenv("ANTHROPIC_API_KEY"):
        for title, desc in NOT_PRIMARY:
            if _is_relevant(title, desc):
                print(f"FAIL (should NOT be relevant on fast path): {title!r}")
                fails += 1

    if fails:
        print(f"\n{fails} failure(s)")
        raise SystemExit(1)
    print("all relevance filter tests passed")


if __name__ == "__main__":
    run()
