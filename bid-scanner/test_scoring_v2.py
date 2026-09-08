"""
Unit tests for scoring v2 (bid-scanner/scoring.py).

    python test_scoring_v2.py
"""

from datetime import date, timedelta

from scoring import score_go_no_go

TODAY = date(2026, 9, 8)


def _bid(due_in_days=None, county=None, geo_status="in"):
    due = (TODAY + timedelta(days=due_in_days)).isoformat() if due_in_days is not None else None
    return {"due_date": due, "county": county, "geo_status": geo_status}


def _spec(city="", award=None, primary=True):
    return {"project_city": city, "award_method": award, "flooring_is_primary": primary}


CASES = [
    # (name, bid, spec, expect)
    ("Chatsworth + 25d + unknown award → strong GO",
     _bid(25, "Los Angeles"), _spec("Chatsworth"),
     dict(verdict="go", score=90, needs_review=False)),

    ("Long Beach + 15d + low_bid → MAYBE",
     _bid(15, "Los Angeles"), _spec("Long Beach", "low_bid"),
     dict(verdict="maybe", score=50, needs_review=False)),

    ("San Diego county default + 6d → NO-GO",
     _bid(6, "San Diego"), _spec("", None),
     dict(verdict="no_go", score=19, needs_review=False)),

    ("San Diego + 30d + best_value → MAYBE",
     _bid(30, "San Diego"), _spec("", "best_value"),
     dict(verdict="maybe", score=56, needs_review=False)),

    ("Ventura county default + 20d → GO",
     _bid(20, "Ventura"), _spec("", None),
     dict(verdict="go", score=72, needs_review=False)),

    ("no spec → review(no_docs)",
     _bid(20, "Los Angeles"), None,
     dict(needs_review=True, reasons=["no_docs"])),

    ("geo unknown, no city → review(no_location)",
     _bid(20, None, "unknown"), _spec(""),
     dict(needs_review=True, reasons=["no_location"])),

    ("no due date → review(no_due_date)",
     _bid(None, "Los Angeles"), _spec("Van Nuys"),
     dict(needs_review=True, reasons=["no_due_date"])),

    ("scope not read → review(no_scope_read)",
     _bid(20, "Los Angeles"), _spec("Van Nuys", None, primary=None),
     dict(needs_review=True, reasons=["no_scope_read"])),

    ("flooring not primary → hard NO-GO",
     _bid(20, "Los Angeles"), _spec("Van Nuys", None, primary=False),
     dict(verdict="no_go", score=0, needs_review=False)),
]


def run():
    fails = 0
    for name, bid, spec, expect in CASES:
        r = score_go_no_go(bid, spec, today=TODAY)
        for k, v in expect.items():
            if k == "reasons":
                if sorted(r["review_reasons"]) != sorted(v):
                    print(f"FAIL {name}: reasons {r['review_reasons']} != {v}")
                    fails += 1
            elif k == "needs_review":
                if r["needs_review"] != v:
                    print(f"FAIL {name}: needs_review {r['needs_review']} != {v}")
                    fails += 1
            elif k == "verdict":
                if r["verdict"] != v:
                    print(f"FAIL {name}: verdict {r['verdict']} != {v}  (full: {r})")
                    fails += 1
            elif k == "score":
                if r["score"] != v:
                    print(f"FAIL {name}: score {r['score']} != {v}")
                    fails += 1

    if fails:
        print(f"\n{fails} failure(s)")
        raise SystemExit(1)
    print(f"all {len(CASES)} scoring v2 tests passed")


if __name__ == "__main__":
    run()
