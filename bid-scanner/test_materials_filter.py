"""
Unit tests for the materials-/supply-only filter.

    python test_materials_filter.py
"""

from scanner import _is_materials_only, _is_relevant
from scoring import score_go_no_go

MATERIALS_ONLY = [
    ("Furnish and Deliver Carpet Tile", ""),
    ("Flooring Materials - Supply Only", ""),
    ("Carpet Replacement - Materials Only, installation by others", ""),
    ("Supply and deliver resilient flooring; no labor", ""),
    ("Purchase of flooring; installation not included", ""),
    ("Furnish carpet only, no installation", ""),
    ("Annual Carpet Supply Contract", "Vendor to furnish and deliver carpet; installation by owner."),
]

INSTALL_JOBS = [
    ("Gymnasium Floor Replacement", ""),
    ("Furnish and Install VCT Flooring", ""),
    ("Carpet purchase and installation for City Hall", ""),
    ("VCT material purchase and installation of same", ""),
    ("District-wide Flooring Replacement (turnkey)", ""),
]


def run():
    fails = 0
    for title, desc in MATERIALS_ONLY:
        if not _is_materials_only(title, desc):
            print(f"FAIL (expected materials-only): {title!r}")
            fails += 1
        if _is_relevant(title, desc):
            print(f"FAIL (_is_relevant should be False): {title!r}")
            fails += 1
    for title, desc in INSTALL_JOBS:
        if _is_materials_only(title, desc):
            print(f"FAIL (expected install job): {title!r}")
            fails += 1

    # Scoring: materials_only is a hard no-go regardless of other factors
    for spec in ({"total_sqft": 30000, "materials_only": True},
                 {"raw_extract": {"materials_only": True}}):
        r = score_go_no_go({"is_relevant": True}, spec)
        if r != {"score": 0, "verdict": "no_go"}:
            print(f"FAIL scoring: {spec} -> {r}")
            fails += 1

    r = score_go_no_go({"is_relevant": True}, {"total_sqft": 30000, "materials_only": False})
    if r["verdict"] != "go":
        print(f"FAIL scoring (install job should score go): {r}")
        fails += 1

    if fails:
        print(f"\n{fails} failure(s)")
        raise SystemExit(1)
    print("all materials-filter tests passed")


if __name__ == "__main__":
    run()
