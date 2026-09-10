"""Tests for intel_scanner._parse_award_line — the authoritative award-sentence
parser on the PlanetBids bid-detail page."""
from intel_scanner import _parse_award_line


def _subs(*pairs):
    return [{"raw_vendor_name": n, "bid_amount": a, "rank": None, "is_winner": False}
            for n, a in pairs]


def test_for_amount_form_names_winner_and_amount():
    body = ("Awarded on February 5, 2026\nThe project has been awarded to "
            "Bakersfield Floor Covering Inc. for $1,167,805.00 View\nSubmissions")
    subs = _subs(("Bakersfield Floor Covering Inc", 1167805.0), ("Other Co", 1300000.0))
    name, amt, out = _parse_award_line(body, subs, None, None)
    assert name == "Bakersfield Floor Covering Inc"
    assert amt == 1167805.0
    assert [s["is_winner"] for s in out] == [True, False]


def test_for_amount_form_adds_synthetic_row_when_missing():
    body = "The project has been awarded to Empire Interiors Inc for $445,000.00"
    subs = _subs(("Someone Else", 500000.0))
    name, amt, out = _parse_award_line(body, subs, None, None)
    assert name == "Empire Interiors Inc"
    assert amt == 445000.0
    assert any(s["raw_vendor_name"] == "Empire Interiors Inc" and s["is_winner"] for s in out)
    assert len(out) == 2


def test_bare_form_only_tags_existing_bidder():
    body = "This contract was awarded to ABC Flooring, LLC on 3/1/2026."
    subs = _subs(("ABC Flooring, LLC", 88000.0), ("XYZ Carpet", 91000.0))
    name, amt, out = _parse_award_line(body, subs, None, None)
    assert name == "ABC Flooring, LLC"
    assert amt == 88000.0
    assert [s["is_winner"] for s in out] == [True, False]


def test_bare_form_no_match_no_synthetic_row():
    body = "This contract was awarded to ABC Flooring, LLC."
    subs = _subs(("Totally Different Co", 88000.0))
    name, amt, out = _parse_award_line(body, subs, None, None)
    assert name is None
    assert len(out) == 1  # no junk row invented


def test_junk_phrase_awarded_to_date_ignored():
    body = "This bid has not been awarded to date. Check back later."
    subs = _subs(("Real Bidder Inc", 100.0))
    name, amt, out = _parse_award_line(body, subs, None, None)
    assert name is None
    assert not any(s["is_winner"] for s in out)
    assert len(out) == 1


def test_junk_phrase_lowest_bidder_ignored():
    body = "The contract will be awarded to the lowest responsible bidder for $0"
    subs = _subs(("Real Bidder Inc", 100.0))
    name, amt, out = _parse_award_line(body, subs, None, None)
    assert name is None


def test_no_submissions_and_bare_form_returns_unchanged():
    name, amt, out = _parse_award_line("awarded to Ghost Co", [], None, None)
    assert name is None and amt is None and out == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
