"""
FCU Go/No-Go Scorer — Python port of dashboard/app/lib/scoring.ts

Shared by digest.py and jobwalk.py.

Usage:
  from scoring import score_bid
  result = score_bid(bid_row, spec_row_or_None)
  # result = {"score": 72, "verdict": "go", "factors": [...]}
"""

from datetime import date
import math


def score_bid(bid: dict, spec: dict | None) -> dict:
    """
    Mirror of scoring.ts scoreGoNoGo().
    bid  — bids table row
    spec — bid_specs table row, or None if not yet parsed
    Returns {"score": int, "verdict": "go"|"maybe"|"no_go", "factors": list[str]}
    """
    score = 55
    factors = []

    # Relevance
    if bid.get("is_relevant"):
        score += 20
        factors.append("+20 flooring relevant")
    else:
        score -= 25
        factors.append("-25 not flooring relevant")

    # Hard block: past due
    if bid.get("due_date"):
        try:
            due = date.fromisoformat(bid["due_date"])
            days_out = (due - date.today()).days
            if days_out < 0:
                factors.append("-100 past due")
                return {"score": 0, "verdict": "no_go", "factors": factors}
        except (ValueError, TypeError):
            pass

    if spec:
        # Square footage
        sqft = spec.get("total_sqft") or 0
        if sqft >= 20_000:
            score += 15; factors.append("+15 large scope (>20k SF)")
        elif sqft >= 5_000:
            score += 10; factors.append("+10 mid scope (>5k SF)")
        elif sqft >= 1_000:
            score += 3;  factors.append("+3 small scope (>1k SF)")
        else:
            score -= 10; factors.append("-10 very small scope (<1k SF)")

        # Prevailing wage
        pw = spec.get("prevailing_wage")
        if pw is True:
            score -= 8; factors.append("-8 prevailing wage required")
        elif pw is False:
            score += 5; factors.append("+5 no prevailing wage")

        # Bid bond
        if spec.get("bid_bond") is True:
            score -= 5; factors.append("-5 bid bond required")

        # Mandatory job walk
        if spec.get("walk_required") is True:
            score -= 5; factors.append("-5 mandatory job walk")

        # DVBE (FCU is certified)
        if spec.get("dvbe_required") is True:
            score += 12; factors.append("+12 DVBE required (FCU certified)")

        # DBE goal
        dbe = spec.get("dbe_goal_pct") or 0
        if dbe > 0:
            score -= 10; factors.append(f"-10 DBE goal {dbe}%")

        score += 5; factors.append("+5 spec parsed")
    else:
        score -= 5; factors.append("-5 no spec yet")

    score = max(0, min(100, round(score)))
    verdict = "go" if score >= 65 else ("maybe" if score >= 40 else "no_go")
    return {"score": score, "verdict": verdict, "factors": factors}
