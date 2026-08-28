"""
PlanetBids run manifest — tracks per-portal outcome so a blocked / incomplete
run can be resumed with `python main.py --source planetbids --resume`.

The scraper walks ~40 portals in one browser session. When PlanetBids' WAF
trips, every portal after it serves a blank page, so a single run can leave
most portals unchecked while `main.py` still reports "0 bids". This manifest
records what actually happened:

  ok       — /papi/bids response captured, portal loaded fine
  empty    — portal loaded but no keyword-matched open bids
  blocked  — data never loaded (WAF / blank page / timeout)
  error    — unexpected failure while scraping the portal
  pending  — not attempted yet (fresh run) or skipped after an early stop

`--resume` re-scrapes only portals whose status is blocked / error / pending.
"""

import json
from datetime import datetime
from pathlib import Path

STATE_FILE = Path(__file__).parent / "output" / "planetbids_state.json"

# Statuses that a resume run should retry.
UNFINISHED = {"blocked", "error", "pending"}

# A manifest older than this (hours, based on run_started) is considered stale;
# `--resume` falls back to a full run rather than resuming yesterday's portals.
STALE_AFTER_HOURS = 48


def new_manifest(portals: dict) -> dict:
    """Fresh manifest with every portal marked pending.

    `portals` is {portal_id: (agency, county)} — same shape as
    scanner.PLANETBIDS_PORTALS.
    """
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "run_started": now,
        "run_finished": None,
        "portals": {
            pid: {"agency": agency, "status": "pending", "bid_count": 0,
                  "checked_at": None}
            for pid, (agency, _county) in portals.items()
        },
    }


def load() -> dict | None:
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def save(manifest: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(manifest, indent=2))


def is_stale(manifest: dict) -> bool:
    started = manifest.get("run_started")
    if not started:
        return True
    try:
        age = datetime.now() - datetime.fromisoformat(started)
    except ValueError:
        return True
    return age.total_seconds() > STALE_AFTER_HOURS * 3600


def unfinished_portal_ids(manifest: dict) -> list[str]:
    return [pid for pid, rec in manifest.get("portals", {}).items()
            if rec.get("status") in UNFINISHED]


def record(manifest: dict, portal_id: str, agency: str, status: str,
           bid_count: int = 0) -> None:
    manifest.setdefault("portals", {})[portal_id] = {
        "agency": agency,
        "status": status,
        "bid_count": bid_count,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    save(manifest)


def counts(manifest: dict) -> dict:
    out = {"ok": 0, "empty": 0, "blocked": 0, "error": 0, "pending": 0}
    for rec in manifest.get("portals", {}).values():
        out[rec.get("status", "pending")] = out.get(rec.get("status", "pending"), 0) + 1
    return out


def format_summary(manifest: dict) -> str:
    """Human-readable end-of-run summary + resume hint when incomplete."""
    c = counts(manifest)
    total_bids = sum(r.get("bid_count", 0) for r in manifest.get("portals", {}).values())
    lines = [
        f"PlanetBids: {c['ok']} ok · {c['empty']} empty · "
        f"{c['blocked']} blocked · {c['error']} error · {c['pending']} pending "
        f"({total_bids} matched bids)"
    ]
    incomplete = [
        f"{rec['agency']} (cid={pid})"
        for pid, rec in manifest.get("portals", {}).items()
        if rec.get("status") in UNFINISHED
    ]
    if incomplete:
        lines.append("")
        lines.append(f"⚠ {len(incomplete)} portal(s) incomplete — re-run later today:")
        lines.append("    python main.py --source planetbids --resume")
        for item in incomplete:
            lines.append(f"      · {item}")
    return "\n".join(lines)
