"""
FCU Go/No-Go scoring — Python port of app/lib/scoring.ts.
Single source of truth for score computation used by parser.py and jobwalk.py.
"""


def score_go_no_go(bid: dict, spec: dict | None) -> dict:
    """
    Returns {"score": int, "verdict": "go"|"maybe"|"no_go"}.
    bid  — needs: is_relevant
    spec — needs: total_sqft, prevailing_wage, bid_bond, walk_required,
                  raw_extract.dvbe_required, raw_extract.dbe_goal_pct
    Due date is not a scoring factor — expirer handles archiving past-due bids.
    """
    score = 55

    # 1. Flooring scope match
    if bid.get("is_relevant"):
        score += 20
    else:
        score -= 25

    # 2. Square footage
    sqft = spec.get("total_sqft") if spec else None
    if sqft:
        if sqft >= 20_000:
            score += 15
        elif sqft >= 5_000:
            score += 10
        elif sqft >= 1_000:
            score += 3
        else:
            score -= 10

    # 3. Prevailing wage
    if spec:
        if spec.get("prevailing_wage") is True:
            score -= 8
        elif spec.get("prevailing_wage") is False:
            score += 5

    # 4. Bid bond
    if spec and spec.get("bid_bond") is True:
        score -= 5

    # 5. Mandatory job walk
    if spec and spec.get("walk_required") is True:
        score -= 5

    # 6. DVBE (FCU is certified — competitive edge)
    raw = (spec.get("raw_extract") or {}) if spec else {}
    if raw.get("dvbe_required") is True:
        score += 12

    # 7. DBE goal
    dbe = raw.get("dbe_goal_pct")
    if dbe and dbe > 0:
        score -= 10

    # 8. Spec parsed
    if spec:
        score += 5
    else:
        score -= 5

    clamped = min(100, max(0, round(score)))
    if clamped >= 65:
        verdict = "go"
    elif clamped >= 40:
        verdict = "maybe"
    else:
        verdict = "no_go"

    return {"score": clamped, "verdict": verdict}
