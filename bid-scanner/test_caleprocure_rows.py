"""
Tests for scanner.caleprocure_row_to_bid and the Cal eProcure federal
exemption. Rows are real (2026-10-27).

    python test_caleprocure_rows.py
"""

from datetime import date

from scanner import apply_federal_policy, caleprocure_row_to_bid


def test_row_mapping():
    b = caleprocure_row_to_bid({
        "id": "0000040520", "name": "CR25-300826.FMD.UPS",
        "dept": "Department of General Services", "end": "10/27/2026\n2:00PM PDT",
        "status": "Posted"})
    assert b["bid_id"] == "CEP-0000040520"
    assert b["title"] == "CR25-300826.FMD.UPS"
    assert b["agency"] == "Department of General Services"   # was the event name
    assert b["due_date"] == date(2026, 10, 27)                 # was never parsed


def test_skips_blank_and_non_posted():
    assert caleprocure_row_to_bid({"id": "", "name": ""}) is None
    assert caleprocure_row_to_bid({"id": "1", "name": "Flooring", "status": "Canceled"}) is None


def test_calvet_is_not_federal():
    b = caleprocure_row_to_bid({
        "id": "0000039999", "name": "25HS0024 - NCVC Flooring Replacement Service",
        "dept": "Dept of Veterans Affairs", "end": "11/20/2026", "status": "Posted"})
    b["geo_status"] = "unknown"
    apply_federal_policy([b])
    assert b["geo_status"] == "unknown"   # CalVet (state), not the federal VA


if __name__ == "__main__":
    test_row_mapping()
    test_skips_blank_and_non_posted()
    test_calvet_is_not_federal()
    print("✓ Cal eProcure row tests pass")
