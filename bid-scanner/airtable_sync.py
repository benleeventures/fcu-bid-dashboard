"""
FCU Bid Scanner — Airtable sync.

Pushes newly-found, relevant bids into the "FCU Bid Tracker" Airtable base
(Opportunities table) so Robert's daily tracker fills itself in instead of
being hand-entered. Matches on the "Bid ID" field to avoid duplicates —
a bid already present in Airtable is left alone (Robert may have already
moved its Status/Owner/Notes).

Geographic scope (spec §1) is enforced upstream in scanner.py via geo.py:
any bid whose place of performance is outside the four in-scope counties
(LA, Orange, Ventura, San Diego) is dropped before it ever reaches here.
Federal (SAM.gov) bids that survive that filter — i.e. performed in one of
the four counties, or flagged geo_status="unknown" — are synced like any
other source. Bids with geo_status="unknown" carry a "Needs county check"
note so Robert confirms the county during qualification.

Estimated Value still needs a parsed spec doc that doesn't exist until
later in the pipeline, so it is left blank at discovery time.
"""

import os
from datetime import date

try:
    from pyairtable import Api
    _AIRTABLE_AVAILABLE = True
except ImportError:
    _AIRTABLE_AVAILABLE = False

_table = None

# Geographic scope is enforced in scanner.py (geo.py). Nothing is source-excluded
# here any more — federal bids performed in the four counties are wanted.
_EXCLUDED_SOURCES: set[str] = set()

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
    "SoCal Plan Room": "SoCal Plan Room",
    "SAM.gov": "SAM.gov (federal)",
    "UCLA Capital Programs": "UCLA Capital Programs",
    "Long Beach BuySpeed": "Long Beach BuySpeed",
    "LAUSD Facilities": "LAUSD Facilities",
    "SecureBids": "SecureBids (Colbi)",
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

    # Spec §5: every new opportunity defaults to Robert. Set
    # AIRTABLE_OWNER_EMAIL in .env once he's a collaborator on the base;
    # left unset, Owner stays blank for manual assignment.
    owner_email = os.getenv("AIRTABLE_OWNER_EMAIL", "").strip()

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
            "Bid Due Date": b.get("due_date").isoformat() if isinstance(b.get("due_date"), date) else (b.get("due_date") or None),
            "Status": "Surfaced",
            "Listing URL": b.get("url") or None,
        }
        if b.get("county"):
            fields["County"] = b["county"]
        if agency:
            fields["Agency or GC"] = agency
        if source in _CITY_BEARING_SOURCES and agency:
            fields["City / County / Area"] = agency
        if b.get("geo_status") == "unknown":
            fields["Notes"] = "Needs county check — place of performance not confirmed"
        if owner_email:
            fields["Owner"] = {"email": owner_email}
        est = b.get("est_value")
        if isinstance(est, (int, float)) and est > 0:
            fields["Estimated Value"] = est
        to_create.append(fields)

    if not to_create:
        return 0

    # typecast=True lets Airtable auto-create new single-select options
    # (e.g. a new Source Platform value) instead of 422-ing.
    # Newer optional fields ("County", "Agency or GC", "Notes") may still not
    # exist in the base — if Airtable rejects an unknown field, strip the
    # optional ones and retry with the core set so the sync still lands.
    _CORE_FIELDS = {
        "Project Name", "Bid ID", "Date Surfaced", "Source Platform",
        "Bid Due Date", "Status", "Listing URL", "City / County / Area",
    }
    created = 0
    for i in range(0, len(to_create), 10):
        batch = to_create[i:i + 10]
        try:
            table.batch_create(batch, typecast=True)
            created += len(batch)
        except Exception as e:
            # A missing field, a bad collaborator email, an un-typecastable
            # value — fall back to the always-present core columns so the
            # opportunity still lands on the tracker.
            print(f"  ⚠ Airtable create failed ({e}); retrying with core fields only")
            table.batch_create([
                {k: v for k, v in row.items() if k in _CORE_FIELDS}
                for row in batch
            ], typecast=True)
            created += len(batch)

    return created


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
