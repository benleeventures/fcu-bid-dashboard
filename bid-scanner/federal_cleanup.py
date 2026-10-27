"""
One-time cleanup for the federal cut (Phase 2): re-check every bid currently
marked relevant with the new federal rules and flip the ones that fail to
is_relevant=False / geo_status='out', so they leave the dashboard and digest.

  - SAM.gov bids: fetch the real place of performance, keep only in-area.
  - Other sources: drop federal work (VA, military, federal agencies).

    python federal_cleanup.py            # dry run — prints what would change
    python federal_cleanup.py --apply    # write the changes to Supabase

Also lists which of the flipped bids already have an Airtable record; those
are left for a human to close out (nothing is deleted from Airtable).
"""

import re
import sys

from dotenv import load_dotenv

load_dotenv()

from db import get_client
from geo import enrich
from scanner import _apply_samgov_pop, apply_federal_policy


def main(apply: bool) -> None:
    sb = get_client()
    if not sb:
        sys.exit("Supabase not configured")

    rows = (sb.table("bids")
            .select("bid_id,title,agency,source,url,state,county,geo_status,is_relevant")
            .eq("is_relevant", True).execute().data or [])
    print(f"{len(rows)} relevant bids to re-check")

    bids = []
    for r in rows:
        b = dict(r)
        b["agency"] = b.get("agency") or ""
        if b["source"] == "SAM.gov":
            m = re.search(r"/opp/([a-f0-9]+)/", b.get("url") or "")
            b["_opp_id"] = m.group(1) if m else ""
            b["county"] = None   # re-derive from the real place of performance
        bids.append(b)

    _apply_samgov_pop([b for b in bids if b["source"] == "SAM.gov"])
    for b in bids:
        if b["source"] == "SAM.gov":
            enrich(b)
    apply_federal_policy(bids)

    flipped = [b for b in bids if b["geo_status"] == "out"]
    print(f"\n{len(flipped)} bid(s) to drop:")
    for b in flipped:
        print(f"  {b['source'][:14]:14} | {(b.get('pop_raw') or '')[:32]:32} | {b['title'][:70]}")

    _report_airtable([b["bid_id"] for b in flipped])

    if not apply:
        print("\nDry run — re-run with --apply to write these changes.")
        return
    for b in flipped:
        sb.table("bids").update({
            "is_relevant": False,
            "geo_status": "out",
            "state": b.get("state") or None,
        }).eq("bid_id", b["bid_id"]).execute()
    print(f"\n✓ {len(flipped)} bid(s) marked out of scope")


def _report_airtable(bid_ids: list[str]) -> None:
    from airtable_sync import _get_table
    table = _get_table()
    if not table or not bid_ids:
        return
    found = []
    for i in range(0, len(bid_ids), 50):
        chunk = bid_ids[i:i + 50]
        formula = "OR(" + ",".join(f"{{Bid ID}}='{bid_id}'" for bid_id in chunk) + ")"
        found += [rec["fields"].get("Bid ID") for rec in
                  table.all(formula=formula, fields=["Bid ID", "Status"])]
    print(f"\n{len(found)} of these are in Airtable (not touched): {', '.join(found) or '—'}")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
