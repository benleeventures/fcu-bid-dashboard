"""
Re-run the geo + federal gates over bids already in Supabase, so rule changes
reach rows the scanner saw before them (the scanner only re-stamps geo on rows
it sees again). Covers every open bid (due today or later, or no due date):

  - county already confirmed (geo_status='in')  -> keep it, set region
  - county unknown / never classified           -> re-classify with geo.py
                                                   (Kern, school districts,
                                                   colleges, neighborhoods)
  - SAM.gov                                     -> real place of performance
  - federal work from other sources             -> out

Rows that end up out of scope are also set is_relevant=False so they leave the
dashboard and digest.

    python geo_backfill.py            # dry run — prints what would change
    python geo_backfill.py --apply    # write the changes to Supabase

Lists any flipped bid that already has an Airtable record; Airtable itself is
not touched.
"""

import collections
import re
import sys
from datetime import date

from dotenv import load_dotenv

load_dotenv()

from db import get_client
from geo import FOUR_COUNTIES, enrich, region_for
from scanner import _apply_samgov_pop, apply_federal_policy

_FIELDS = "bid_id,title,agency,source,url,county,geo_status,region,is_relevant,due_date"


def _open_bids(sb) -> list[dict]:
    today = date.today().isoformat()
    rows, off = [], 0
    while True:
        page = (sb.table("bids").select(_FIELDS)
                .or_(f"due_date.gte.{today},due_date.is.null")
                .range(off, off + 999).execute().data or [])
        rows += page
        if len(page) < 1000:
            return rows
        off += 1000


def main(apply: bool) -> None:
    sb = get_client()
    if not sb:
        sys.exit("Supabase not configured")

    rows = _open_bids(sb)
    print(f"{len(rows)} open bids to re-check")

    bids = []
    for r in rows:
        b = {**r, "agency": r.get("agency") or "", "_before": (r["county"], r["geo_status"], r["region"])}
        confirmed = r["geo_status"] == "in" and r["county"] in FOUR_COUNTIES
        if b["source"] == "SAM.gov":
            m = re.search(r"/opp/([a-f0-9]+)/", b.get("url") or "")
            b["_opp_id"] = m.group(1) if m else ""
            b["county"] = None
        elif not confirmed:
            b["county"] = None
        bids.append(b)

    _apply_samgov_pop([b for b in bids if b["source"] == "SAM.gov"])
    for b in bids:
        if b["source"] == "SAM.gov" or b["county"] is None:
            enrich(b)
        else:
            b["region"] = region_for(b["county"])
    apply_federal_policy(bids)
    for b in bids:
        if b["geo_status"] != "in":
            b["county"], b["region"] = None, None

    changed = [b for b in bids if (b["county"], b["geo_status"], b["region"]) != b["_before"]]
    dropped = [b for b in changed if b["geo_status"] == "out" and b["is_relevant"]]

    trans = collections.Counter((b["_before"][1], b["geo_status"]) for b in changed)
    print(f"\n{len(changed)} bid(s) change:")
    for (old, new), n in trans.most_common():
        print(f"  {old or 'null'} -> {new}: {n}")
    print(f"\n{len(dropped)} relevant bid(s) leave the feed:")
    for b in dropped:
        print(f"  {b['source'][:14]:14} | {(b.get('pop_raw') or b['agency'])[:30]:30} | {b['title'][:70]}")
    gained = [b for b in changed if b["is_relevant"] and b["geo_status"] == "in" and b["_before"][1] != "in"]
    print(f"\n{len(gained)} relevant bid(s) now confirmed in-area:")
    for b in gained:
        print(f"  {b['region']:5} {b['county']:15} | {b['title'][:70]}")

    _report_airtable([b["bid_id"] for b in dropped])

    if not apply:
        print("\nDry run — re-run with --apply to write these changes.")
        return
    for b in changed:
        update = {"county": b["county"], "geo_status": b["geo_status"], "region": b["region"]}
        if b in dropped:
            update["is_relevant"] = False
        sb.table("bids").update(update).eq("bid_id", b["bid_id"]).execute()
    print(f"\n✓ {len(changed)} bid(s) updated, {len(dropped)} removed from the feed")


def _report_airtable(bid_ids: list[str]) -> None:
    from airtable_sync import _get_table
    table = _get_table()
    if not table or not bid_ids:
        return
    found = []
    for i in range(0, len(bid_ids), 50):
        chunk = bid_ids[i:i + 50]
        formula = "OR(" + ",".join(f"{{Bid ID}}='{bid_id}'" for bid_id in chunk) + ")"
        found += [rec["fields"].get("Bid ID") for rec in table.all(formula=formula, fields=["Bid ID"])]
    print(f"\n{len(found)} of the removed bids are in Airtable (not touched): {', '.join(found) or '—'}")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
