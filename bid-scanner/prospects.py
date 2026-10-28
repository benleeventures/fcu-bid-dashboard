"""
Robert's prospect list — Phase 2 Priority 3.

Two tables in the same Airtable base as the bid tracker:

  Prospects   one row per senior living / care center / hotel Robert works.
              Status, next step and last visit are kept current by the
              "Log a visit" automation (see docs/prospects-tab.md).
  Visits      one row per visit, created from the phone form. Visit Date is
              the record's created time, so the form never asks for it.

  python prospects.py --setup                  create both tables / missing fields (idempotent)
  python prospects.py --seed data/prospects_seed.csv   add rows whose Property Name isn't there yet
  python prospects.py --seed robert_list.csv --dry-run  preview an import (e.g. Robert's own list)

The seed CSV columns are Prospects field names; blank cells are skipped, so a
row never overwrites anything. Forms, views and the automation can't be made
through the Airtable API — docs/prospects-tab.md has the 10-minute UI steps.
"""

import argparse
import csv
import os
import sys

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

API = "https://api.airtable.com/v0"

PROSPECTS = "Prospects"
VISITS = "Visits"

STATUSES = ["New", "Visited", "Quoted", "Monthly contract signed", "Not a fit"]
NEXT_STEPS = ["Send quote", "Call back", "Schedule walk", "Visit again", "Nothing — not a fit"]
_US_DATE = {"dateFormat": {"name": "us"}}


def _choices(names):
    return {"choices": [{"name": n} for n in names]}


# Primary field first. Spec: Ben's Phase 2 scope, "Priority 3: Robert's prospect list".
PROSPECT_FIELDS = [
    {"name": "Property Name", "type": "singleLineText"},
    {"name": "Type", "type": "singleSelect",
     "options": _choices(["Senior living", "Care or treatment center", "Hotel", "Other"])},
    {"name": "Status", "type": "singleSelect", "options": _choices(STATUSES)},
    {"name": "City", "type": "singleLineText"},
    {"name": "Address", "type": "singleLineText"},
    {"name": "Region", "type": "singleSelect", "options": _choices(["North", "South"])},
    {"name": "Contact Name", "type": "singleLineText"},
    {"name": "Contact Title", "type": "singleLineText"},
    {"name": "Contact Phone", "type": "phoneNumber"},
    {"name": "Contact Email", "type": "email"},
    {"name": "Last Visit Date", "type": "date", "options": _US_DATE},
    {"name": "Next Step", "type": "singleSelect", "options": _choices(NEXT_STEPS)},
    {"name": "Next Step Date", "type": "date", "options": _US_DATE},
    {"name": "Notes", "type": "multilineText"},
    # Friday scoreboard #4 ("new steady contracts signed") counts by this date.
    {"name": "Contract Signed Date", "type": "date", "options": _US_DATE},
    {"name": "Source", "type": "singleSelect",
     "options": _choices(["Robert's list", "Email contact", "Research", "Found in the field"])},
]

FOLLOW_UP_FORMULA = (
    "IF(AND({Next Step Date}, "
    "OR({Status} = BLANK(), AND({Status} != 'Not a fit', {Status} != 'Monthly contract signed')), "
    "IS_BEFORE({Next Step Date}, DATEADD(TODAY(), 1, 'days'))), '⏰ Follow up', '')"
)

VISIT_FIELDS = [
    {"name": "What They Said", "type": "multilineText"},   # primary
    {"name": "Visit Date", "type": "createdTime"},   # API rejects any options here
    {"name": "Status Now", "type": "singleSelect", "options": _choices(STATUSES[1:])},
    {"name": "Next Step", "type": "singleSelect", "options": _choices(NEXT_STEPS)},
    {"name": "Next Step Date", "type": "date", "options": _US_DATE},
    {"name": "Contact Met", "type": "singleLineText"},
    {"name": "Photo", "type": "multipleAttachments"},
]


def _session():
    key, base = os.environ.get("AIRTABLE_API_KEY"), os.environ.get("AIRTABLE_BASE_ID")
    if not key or not base:
        sys.exit("AIRTABLE_API_KEY / AIRTABLE_BASE_ID not set")
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {key}"
    return s, base


def _tables(s, base):
    r = s.get(f"{API}/meta/bases/{base}/tables", timeout=30)
    r.raise_for_status()
    return {t["name"]: t for t in r.json()["tables"]}


def _ensure_table(s, base, name, fields, description):
    tables = _tables(s, base)
    if name not in tables:
        # createdTime / formula fields can't be part of table creation — added below.
        basic = [f for f in fields if f["type"] not in ("createdTime", "formula")]
        r = s.post(f"{API}/meta/bases/{base}/tables", timeout=30,
                   json={"name": name, "description": description, "fields": basic})
        if not r.ok:
            sys.exit(f"✗ create table {name}: {r.text[:300]}")
        print(f"+ table {name}")
        tables[name] = r.json()
    table = tables[name]
    have = {f["name"] for f in table["fields"]}
    for spec in fields:
        _ensure_field(s, base, table, have, spec)
    return table


def _ensure_field(s, base, table, have, spec):
    if spec["name"] in have:
        print(f"  = {table['name']}.{spec['name']}")
        return
    r = s.post(f"{API}/meta/bases/{base}/tables/{table['id']}/fields", json=spec, timeout=30)
    print(f"  {'+' if r.ok else '✗'} {table['name']}.{spec['name']}"
          + ("" if r.ok else f" — {r.text[:200]}"))
    if r.ok:
        have.add(spec["name"])


def setup():
    s, base = _session()
    prospects = _ensure_table(s, base, PROSPECTS, PROSPECT_FIELDS,
                              "Robert's senior living / care / hotel prospects (Phase 2 Priority 3).")
    _ensure_table(s, base, VISITS, VISIT_FIELDS,
                  "One row per visit, logged from the phone form.")

    # Fields that need the other table to exist first.
    tables = _tables(s, base)
    prospects, visits = tables[PROSPECTS], tables[VISITS]
    vhave = {f["name"] for f in visits["fields"]}
    _ensure_field(s, base, visits, vhave, {
        "name": "Property", "type": "multipleRecordLinks",
        "options": {"linkedTableId": prospects["id"]}})

    tables = _tables(s, base)
    prospects = tables[PROSPECTS]
    phave = {f["name"] for f in prospects["fields"]}
    _ensure_field(s, base, prospects, phave,
                  {"name": "Follow-up Due", "type": "formula",
                   "options": {"formula": FOLLOW_UP_FORMULA}})
    print("Done. Next: the form, views and automation in docs/prospects-tab.md.")


def seed(path, dry_run=False):
    s, base = _session()
    url = f"{API}/{base}/{requests.utils.quote(PROSPECTS)}"
    existing, offset = set(), None
    while True:
        r = s.get(url, params={"fields[]": "Property Name", **({"offset": offset} if offset else {})},
                  timeout=30)
        r.raise_for_status()
        body = r.json()
        existing |= {(rec["fields"].get("Property Name") or "").strip().lower() for rec in body["records"]}
        offset = body.get("offset")
        if not offset:
            break

    allowed = {f["name"] for f in PROSPECT_FIELDS}
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            fields = {k.strip(): v.strip() for k, v in row.items()
                      if k and k.strip() in allowed and v and v.strip()}
            name = fields.get("Property Name", "")
            if not name or name.lower() in existing:
                continue
            fields.setdefault("Status", "New")
            existing.add(name.lower())
            rows.append(fields)

    print(f"{len(rows)} new prospect(s) from {path}" + (" (dry run)" if dry_run else ""))
    for f in rows:
        print(f"  + {f['Property Name']} — {f.get('City', '')}")
    if dry_run:
        return
    for i in range(0, len(rows), 10):
        r = s.post(url, json={"records": [{"fields": f} for f in rows[i:i + 10]], "typecast": True},
                   timeout=30)
        if not r.ok:
            sys.exit(f"✗ batch {i // 10 + 1}: {r.text[:300]}")
    print(f"✓ created {len(rows)}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--setup", action="store_true", help="create Prospects + Visits tables / missing fields")
    p.add_argument("--seed", metavar="CSV", help="add prospects from a CSV (skips names already in Airtable)")
    p.add_argument("--dry-run", action="store_true", help="with --seed: print, write nothing")
    a = p.parse_args()
    if not (a.setup or a.seed):
        p.print_help()
    if a.setup:
        setup()
    if a.seed:
        seed(a.seed, a.dry_run)
