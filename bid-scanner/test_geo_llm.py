"""
Tests for geo_llm.apply_answer and the fallback's gating — no API calls.
Answers are real responses from the 2026-10-27 live check.

    python test_geo_llm.py
"""

import os

import geo_llm
from geo_llm import apply_answer, resolve_unknown_locations


def _bid(**kw):
    return {"bid_id": "X", "title": "Flooring", "agency": "", "is_relevant": True,
            "geo_status": "unknown", "county": None, **kw}


def test_in_scope_county():
    b = _bid()
    assert apply_answer(b, {"city": None, "county": "San Diego",
                            "agency": "Grossmont Union High School District"})
    assert (b["geo_status"], b["county"], b["region"]) == ("in", "San Diego", "South")
    assert b["agency"] == "Grossmont Union High School District"


def test_out_of_scope_county():
    b = _bid()
    assert apply_answer(b, {"city": "Santa Barbara", "county": "Santa Barbara", "agency": "UCSB"})
    assert (b["geo_status"], b["county"], b["region"]) == ("out", None, None)


def test_county_suffix_and_city_only():
    b = _bid()
    assert apply_answer(b, {"city": None, "county": "Kern County", "agency": None})
    assert (b["county"], b["region"]) == ("Kern", "North")
    b = _bid()
    assert apply_answer(b, {"city": "Pasadena", "county": None, "agency": None})
    assert b["county"] == "Los Angeles"


def test_blank_answer_changes_nothing():
    b = _bid(agency="CAL FIRE")
    assert not apply_answer(b, {"city": None, "county": None, "agency": "CAL FIRE"})
    assert b["geo_status"] == "unknown"
    assert not apply_answer(b, None)


def test_only_relevant_unknown_bids_are_asked():
    asked = []
    geo_llm.ask_claude = lambda bid: asked.append(bid["bid_id"]) or None
    os.environ["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY") or "test"
    geo_llm.GEO_LLM_CACHE = "/dev/null/nope.json"   # unwritable: cache stays in memory
    resolve_unknown_locations([
        _bid(bid_id="A"),
        _bid(bid_id="B", is_relevant=False),
        _bid(bid_id="C", geo_status="in", county="Orange"),
    ])
    assert asked == ["A"]


if __name__ == "__main__":
    test_in_scope_county()
    test_out_of_scope_county()
    test_county_suffix_and_city_only()
    test_blank_answer_changes_nothing()
    test_only_relevant_unknown_bids_are_asked()
    print("✓ geo LLM tests pass")
