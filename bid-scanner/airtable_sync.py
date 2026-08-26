"""
FCU Bid Scanner — Airtable sync.

Pushes newly-found, relevant bids into the "FCU Bid Tracker" Airtable base
(Opportunities table) so Robert's daily tracker fills itself in instead of
being hand-entered. Matches on the "Bid ID" field to avoid duplicates —
a bid already present in Airtable is left alone (Robert may have already
moved its Status/Owner/Notes).

Federal listings (SAM.gov) are excluded here — the spec's hard rule is
no federal work, and SAM.gov is the one federal source the scanner has
today. This is the only quality filter available at discovery time; there
is no bid value or county data on `bids` yet, and go/no-go scoring needs a
parsed spec doc that doesn't exist until later in the pipeline. Estimated
Value and City/County/Area for non-PlanetBids/OpenGov sources are left
blank for Robert/Joanne to fill in during qualification.
"""

import os
from datetime import date

try:
    from pyairtable import Api
    _AIRTABLE_AVAILABLE = True
except ImportError:
    _AIRTABLE_AVAILABLE = False

_table = None

_EXCLUDED_SOURCES = {"SAM.gov"}

# Scanner source strings -> Airtable "Source Platform" select options
_SOURCE_MAP = {
    "PlanetBids": "PlanetBids",
    "Cal eProcure": "Cal eProcure",
    "Caltrans CCOP": "Caltrans CCOP",
    "OpenGov": "OpenGov Procurement",
    "Quality Bidders": "Quality Bidders (Colbi)",
    "BidNet Direct": "BidNet Direct",
    "Bid Locker": "Bid Locker",
    "Crisp Plan Room": "Crisp Plan Room",
}

# Sources whose `agency` field is already a specific city name
# (see PLANETBIDS_PORTALS / OPENGOV_PORTALS in scanner.py)
_CITY_BEARING_SOURCES = {"PlanetBids", "OpenGov"}


def _get_table():
    global _table
    if _table is not None:
        return _table
    key = os.getenv("AIRTABLE_API_KEY", "").strip()
    base_id = os.getenv("AIRTABLE_BASE_ID", "").strip()
    if not key or not base_id:
        return None
    if not _AIRTABLE_AVAILABLE:
        print("  ⚠ pyairtable not installed — run: pip install pyairtable")
        return None
    _table = Api(key).table(base_id, "Opportunities")
    return _table


def sync_new_bids(bids: list[dict]) -> int:
    """
    Push bids not already in the Opportunities table. Returns count added.
    Only call with bids you want on the tracker (e.g. is_relevant + new).
    Federal (SAM.gov) bids are dropped here regardless of relevance.
    """
    table = _get_table()
    if not table or not bids:
        return 0

    bids = [b for b in bids if b.get("source") not in _EXCLUDED_SOURCES]
    candidate_ids = {b["bid_id"] for b in bids if b.get("bid_id")}
    if not candidate_ids:
        return 0

    # Airtable formula OR() has practical limits — chunk lookups.
    existing_ids = set()
    ids_list = list(candidate_ids)
    chunk_size = 50
    for i in range(0, len(ids_list), chunk_size):
        chunk = ids_list[i:i + chunk_size]
        formula = "OR(" + ",".join(f"{{Bid ID}}='{bid_id}'" for bid_id in chunk) + ")"
        for rec in table.all(formula=formula, fields=["Bid ID"]):
            existing_ids.add(rec["fields"].get("Bid ID"))

    to_create = []
    for b in bids:
        bid_id = b.get("bid_id")
        if not bid_id or bid_id in existing_ids:
            continue
        source = b.get("source", "")
        agency = (b.get("agency") or "")[:200]
        fields = {
            "Project Name": (b.get("title") or "")[:500],
            "Bid ID": bid_id,
            "Date Surfaced": date.today().isoformat(),
            "Source Platform": _SOURCE_MAP.get(source, "Other"),
            "Agency or GC": agency,
            "Bid Due Date": b.get("due_date").isoformat() if isinstance(b.get("due_date"), date) else (b.get("due_date") or None),
            "Status": "Surfaced",
            "Listing URL": b.get("url") or None,
        }
        if source in _CITY_BEARING_SOURCES and agency:
            fields["City / County / Area"] = agency
        to_create.append(fields)

    if not to_create:
        return 0

    for i in range(0, len(to_create), 10):
        table.batch_create(to_create[i:i + 10])

    return len(to_create)


def update_job_walk(bid_id: str, walk_required, walk_date: str | None) -> bool:
    """
    Update Job Walk Mandatory / Job Walk Date on an existing Opportunities
    record once parser.py has extracted this from the bid's spec doc.
    Job walk info isn't known at discovery time — only after a PDF is
    parsed — so this updates a record sync_new_bids already created rather
    than creating a new one. Returns True if a matching record was updated.
    """
    table = _get_table()
    if not table or not bid_id:
        return False

    matches = table.all(formula=f"{{Bid ID}}='{bid_id}'", fields=["Bid ID"])
    if not matches:
        return False

    fields = {}
    if walk_required is not None:
        fields["Job Walk Mandatory"] = bool(walk_required)
    if walk_date:
        fields["Job Walk Date"] = walk_date

    if not fields:
        return False

    table.update(matches[0]["id"], fields)
    return True
