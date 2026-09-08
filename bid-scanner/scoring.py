"""
FCU winnability score (scoring v2) — Python port of app/lib/scoring.ts.
Single source of truth for score computation used by parser.py and jobwalk.py.

Full write-up: bid-scanner/docs/scoring.md

    score = geography(0–60) + lead_time(0–30) + award_adj(−6…+10)  → clamp 0–100
    verdict:  >= 58 GO   ·   33–57 MAYBE   ·   < 33 NO-GO

Hard NO-GO (score 0): flooring is a minor part of a larger multi-trade scope.
(Past-due archiving is handled by expirer.py, not here.)

NEEDS MANUAL REVIEW (no score) when a scoring input is missing — see REVIEW_LABELS.
"""

from geo import drive_band

REVIEW_LABELS = {
    "no_docs":       "Bid documents not downloaded / parsed",
    "no_location":   "Job location not identified",
    "no_due_date":   "No bid due date on file",
    "no_scope_read": "Scope not assessed by parser",
}

_GEO_BAND_SCORE = {"A": 60, "B": 48, "C": 32, "D": 16}


def _lead_time_score(due_date, today):
    """due_date: datetime.date or ISO string. Returns 0–30, or None when there
    is no usable due date (caller flags no_due_date)."""
    from datetime import date as _date
    if not due_date:
        return None
    if isinstance(due_date, str):
        try:
            due_date = _date.fromisoformat(due_date[:10])
        except ValueError:
            return None
    if today is None:
        today = _date.today()
    days = (due_date - today).days
    if days >= 21:
        return 30
    if days >= 14:
        return 24
    if days >= 10:
        return 15
    if days >= 7:
        return 8
    if days >= 4:
        return 3
    return 0


def _award_adj(award_method):
    if award_method in ("best_value", "qualifications"):
        return 10
    if award_method == "low_bid":
        return -6
    return 0


def score_go_no_go(bid: dict, spec: dict | None, today=None) -> dict:
    """
    Returns {"score": int|None, "verdict": str|None,
             "needs_review": bool, "review_reasons": list[str]}.

    bid  — needs: due_date, county, geo_status
    spec — needs: flooring_is_primary, award_method, project_city
                  (falls back to spec["raw_extract"] for the parsed fields)
    """
    raw = (spec.get("raw_extract") or {}) if spec else {}

    def field(key):
        if spec and spec.get(key) is not None:
            return spec.get(key)
        return raw.get(key)

    # ── Not parsed at all ───────────────────────────────────────────────────
    if not spec:
        return {"score": None, "verdict": None, "needs_review": True,
                "review_reasons": ["no_docs"]}

    # ── Hard NO-GO: flooring is a minor slice of a bigger multi-trade scope ──
    if field("flooring_is_primary") is False:
        return {"score": 0, "verdict": "no_go", "needs_review": False,
                "review_reasons": []}

    # ── Missing-input checks → NEEDS MANUAL REVIEW ──────────────────────────
    reasons = []

    project_city = (field("project_city") or "").strip()
    band = drive_band(project_city or None, bid.get("county"))
    if band is None or (bid.get("geo_status") == "unknown" and not project_city):
        reasons.append("no_location")

    lead = _lead_time_score(bid.get("due_date"), today)
    if lead is None:
        reasons.append("no_due_date")

    if field("flooring_is_primary") is None:
        reasons.append("no_scope_read")

    if reasons:
        return {"score": None, "verdict": None, "needs_review": True,
                "review_reasons": reasons}

    # ── Score ──────────────────────────────────────────────────────────────
    score = _GEO_BAND_SCORE[band] + lead + _award_adj(field("award_method"))
    clamped = min(100, max(0, round(score)))
    if clamped >= 58:
        verdict = "go"
    elif clamped >= 33:
        verdict = "maybe"
    else:
        verdict = "no_go"

    return {"score": clamped, "verdict": verdict,
            "needs_review": False, "review_reasons": []}
