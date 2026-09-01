"""
Tests for the out-of-state geo gate (geo.classify_location -> geo_status="out").

    python test_geo_out_of_state.py
"""

from geo import classify_location, _is_out_of_state

# (title, agency, state, place_text) -> expected geo_status
OUT_OF_STATE = [
    ("USCG Base Honolulu Carpet Tiles", "Homeland Security, Department of", "California", ""),
    ("B515 Carpet and Vinyl Installation", "Dept of Defense", "California", "Pearl Harbor, HI 96860"),
    ("Flooring Replacement", "State of Nevada", None, ""),
    ("Carpet Install", "", "California", "Phoenix, AZ 85004"),
    ("Gymnasium Flooring", "", None, "Reno, NV"),
    ("Barracks Renovation Flooring", "US Army", "California", "Fort Bragg, North Carolina"),
    ("Resilient Flooring", "", "TX", ""),
    ("VCT Replacement", "", "California", "Seattle, Washington 98101"),
]

IN_OR_UNKNOWN = [
    # in-scope — must NOT be dropped
    ("Flooring Replacement at City Hall", "City of Los Angeles", "California", ""),
    ("Carpet — Washington Preparatory HS", "Los Angeles Unified School District", "California", ""),
    ("Gym Floor", "City of San Diego", "California", "San Diego, CA 92101"),
    ("VCT Install", "City of Orange", "California", ""),
    ("Flooring", "Ventura County Community College District", "California", ""),
    # genuinely ambiguous CA — stays "unknown", not "out"
    ("District-wide Flooring Replacement", "Springfield School District", "California", ""),
]


def run():
    fails = 0
    for title, agency, state, pop in OUT_OF_STATE:
        r = classify_location(title, agency, state, None, place_text=pop)
        if r["geo_status"] != "out":
            print(f"FAIL (expected out): {title!r} / {agency!r} / {pop!r} -> {r}")
            fails += 1
    for title, agency, state, pop in IN_OR_UNKNOWN:
        r = classify_location(title, agency, state, None, place_text=pop)
        if r["geo_status"] == "out":
            print(f"FAIL (should not be out): {title!r} / {agency!r} -> {r}")
            fails += 1

    # direct unit checks on the helper
    assert _is_out_of_state("homeland security — uscg base honolulu carpet tiles")
    assert _is_out_of_state("dept of defense pearl harbor, hi 96860 — b515 carpet")
    assert not _is_out_of_state("city of los angeles — flooring replacement at city hall")
    assert not _is_out_of_state("los angeles unified school district — washington prep hs carpet")

    if fails:
        print(f"\n{fails} failure(s)")
        raise SystemExit(1)
    print("all out-of-state geo tests passed")


if __name__ == "__main__":
    run()
