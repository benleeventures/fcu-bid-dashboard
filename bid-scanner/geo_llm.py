"""
LLM fallback for bid location (Phase 2, PR 3d).

Structured sources come first — SAM.gov place of performance, BidNet's
Location field, VendorLine / RAMP / UCLA portal counties, the CDE school
district table. This only runs on what's left: bids that look relevant and
still have no county after geo.enrich(). Claude reads the listing text (title,
agency, description, contact email) — never documents — and returns
city / county / agency as JSON, leaving a field null rather than guessing
(Ben's rule). The answer still goes through geo's in/out check.

Each bid is asked once (cached by bid ID in output/geo_llm_cache.json).

Env:
  ANTHROPIC_API_KEY     required (already used by the relevance check)
  GEO_LLM               "off" disables the step
  GEO_LLM_MODEL         default claude-opus-5-5; claude-haiku-5-5 is cheaper
  GEO_LLM_MAX_PER_RUN   default 25
"""

import json
import os

from geo import FOUR_COUNTIES, classify_location, region_for

GEO_LLM_CACHE = os.path.join(os.path.dirname(__file__), "output", "geo_llm_cache.json")
GEO_LLM_MODEL = os.getenv("GEO_LLM_MODEL", "claude-opus-5-5")
GEO_LLM_MAX_PER_RUN = int(os.getenv("GEO_LLM_MAX_PER_RUN", "25"))

_SCHEMA = {
    "type": "object",
    "properties": {
        "city": {"type": ["string", "null"]},
        "county": {"type": ["string", "null"]},
        "agency": {"type": ["string", "null"]},
    },
    "required": ["city", "county", "agency"],
    "additionalProperties": False,
}

_PROMPT = """You locate public bid solicitations for a flooring contractor in Southern California.

From the listing below, give:
- city: the city where the work will be performed
- county: the California county where the work will be performed, without the word "County" (e.g. "San Diego"), or the US state name if it is outside California
- agency: the agency or owner issuing the bid

Use only what the listing states or what follows directly from a named agency or facility (e.g. "Grossmont Union High School District" is in San Diego County; a contact email at guhsd.net is Grossmont UHSD). If a field is not stated and cannot be pinned down that way, return null for it. Never guess. A statewide or multi-county contract with no single work location gets county null.

Listing:
{listing}"""


def _listing(bid: dict) -> str:
    parts = [f"Title: {bid.get('title') or ''}"]
    for label, key in (("Agency / department", "agency"), ("Location", "location_raw"),
                       ("Contact email", "contact_email"), ("Source", "source")):
        if bid.get(key):
            parts.append(f"{label}: {bid[key]}")
    if bid.get("description"):
        parts.append(f"Description: {bid['description'][:3000]}")
    return "\n".join(parts)


def ask_claude(bid: dict) -> dict | None:
    """One structured-output call. Returns {"city", "county", "agency"} or None."""
    import anthropic

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=GEO_LLM_MODEL,
        max_tokens=1024,
        betas=["server-side-fallback-2026-07-01"],
        extra_body={"fallbacks": "default"},
        output_config={"effort": "low",
                       "format": {"type": "json_schema", "schema": _SCHEMA}},
        messages=[{"role": "user", "content": _PROMPT.format(listing=_listing(bid))}],
    )
    if response.stop_reason == "refusal":
        return None
    text = next((b.text for b in response.content if b.type == "text"), "")
    return json.loads(text) if text else None


def apply_answer(bid: dict, answer: dict | None) -> bool:
    """
    Fold an answer into the bid. A county Claude names is checked against the
    in-scope list (in) or marked out; a city alone goes through geo's normal
    classifier. Returns True when geo_status changed from unknown.
    """
    if not answer:
        return False
    if answer.get("agency") and not bid.get("agency"):
        bid["agency"] = answer["agency"]
    county = (answer.get("county") or "").strip()
    county = county[:-7].strip() if county.lower().endswith(" county") else county
    city = (answer.get("city") or "").strip()

    if county:
        loc = ({"county": county, "geo_status": "in"} if county in FOUR_COUNTIES
               else {"county": None, "geo_status": "out"})
    elif city:
        loc = classify_location("", "", None, place_text=f"city of {city}")
    else:
        return False
    if loc["geo_status"] == "unknown":
        return False
    bid.update(loc)
    bid["region"] = region_for(bid["county"]) if loc["geo_status"] == "in" else None
    bid["geo_source"] = "llm"
    return True


def resolve_unknown_locations(bids: list[dict]) -> None:
    """Run the fallback over relevant bids still at geo_status 'unknown'."""
    if os.getenv("GEO_LLM", "").lower() == "off":
        return
    todo = [b for b in bids if b.get("is_relevant") and b.get("geo_status") == "unknown"
            and b.get("bid_id")]
    if not todo:
        return
    if not os.getenv("ANTHROPIC_API_KEY"):
        print(f"  ⚠ geo LLM fallback skipped — ANTHROPIC_API_KEY not set ({len(todo)} unknown)")
        return

    try:
        with open(GEO_LLM_CACHE) as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}

    asked = resolved = 0
    for b in todo:
        if b["bid_id"] not in cache:
            if asked >= GEO_LLM_MAX_PER_RUN:
                continue
            asked += 1
            try:
                cache[b["bid_id"]] = ask_claude(b)
            except Exception as e:
                print(f"    ⚠ geo LLM {b['bid_id']}: {str(e)[:100]}")
                continue
        if apply_answer(b, cache[b["bid_id"]]):
            resolved += 1
    print(f"  ✓ geo LLM fallback: {resolved}/{len(todo)} unknown relevant bids located "
          f"({asked} asked this run)")

    try:
        os.makedirs(os.path.dirname(GEO_LLM_CACHE), exist_ok=True)
        with open(GEO_LLM_CACHE, "w") as f:
            json.dump(cache, f)
    except OSError as e:
        print(f"    ⚠ could not write geo LLM cache: {e}")
