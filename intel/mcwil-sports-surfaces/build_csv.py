"""
Consolidate results_raw.json -> one flat CSV (mcwil_intel_results.csv).

    python build_csv.py

Run after sweep.py. Collapses each awarded bid to one row: agency, project,
winner, winning amount, every bidder + amount, and whether the target vendor
was involved. Bid amounts over $50M are treated as data-entry errors and
written as DATA-ERROR rather than dropped silently.
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).parent
TARGET = "mcwil"  # substring match, case/space-insensitive


def is_target(name: str) -> bool:
    return bool(name) and TARGET in name.lower().replace(" ", "")


def money(a):
    if a is None:
        return ""
    return int(a) if float(a).is_integer() else a


def main():
    rows = json.loads((HERE / "results_raw.json").read_text())
    out = []
    for r in rows:
        subs = r.get("submissions") or []
        parts = []
        for s in subs:
            amt = s.get("bid_amount")
            bad = amt is not None and amt > 50_000_000
            parts.append(f"{s.get('raw_vendor_name', '?')}="
                         f"{'DATA-ERROR' if bad else money(amt)}")
        hit = [s for s in subs if is_target(s.get("raw_vendor_name", ""))]
        out.append({
            "agency": r["agency"],
            "county": r.get("county") or "",
            "portal_id": r["portal_id"],
            "title": r["title"],
            "awarded_date": r.get("awarded_at") or "",
            "total_bidders": r.get("total_bidders")
            or len([s for s in subs if s.get("bid_amount") is not None]),
            "winner": r.get("winner_name") or "",
            "winner_amount": money(r.get("winner_amount")),
            "all_bidders_amounts": "; ".join(parts),
            f"{TARGET}_involved": "YES" if hit else "no",
            f"{TARGET}_bid": money(hit[0].get("bid_amount")) if hit else "",
            "bid_detail_url": r.get("url") or "",
        })
    out.sort(key=lambda x: (x["agency"], x["title"]))
    path = HERE / "mcwil_intel_results.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)
    print(f"wrote {path.name} — {len(out)} rows, "
          f"{sum(1 for o in out if o[f'{TARGET}_involved'] == 'YES')} with {TARGET}")


if __name__ == "__main__":
    main()
