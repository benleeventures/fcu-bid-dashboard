"""
Scan funnel telemetry — one record per scanner run.

`ScanFunnel` accumulates counts as bids move through the pipeline
(raw scrape → geo gate → dedup → relevance → new/known) plus a per-source
breakdown with a health status, and (for PlanetBids) a per-portal outcome list.

`db.log_scan_run()` writes it to the `scan_run` / `scan_source_stat` /
`scan_portal_stat` tables. The `/scanner` dashboard reads those.

Source status values:
  ok       source returned rows normally
  empty    source loaded but returned 0 rows (no exception) — for most sources
           we can't tell a genuine "nothing matched" from a silent block
  blocked  PlanetBids only — WAF/blank page, derived from the run manifest
  partial  PlanetBids only — some portals ok, some still blocked/pending
  error    the scraper raised — see `note`
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SourceStat:
    source: str
    raw_count: int = 0          # rows returned before geo gate / dedup
    kept_count: int = 0         # rows surviving the geo gate (pre-dedup)
    relevant_count: int = 0     # is_relevant rows in the final deduped set
    new_count: int = 0          # first-seen-today rows
    status: str = "ok"          # ok | empty | blocked | partial | error
    portals_total: int | None = None
    portals_ok: int | None = None
    portals_blocked: int | None = None
    note: str = ""
    duration_secs: float | None = None


@dataclass
class ScanFunnel:
    mode: str = "full"                          # full | planetbids | opengov | sam | ...
    started_at: str = field(default_factory=_utcnow)
    finished_at: str | None = None
    duration_secs: float = 0.0

    raw_found: int = 0
    geo_in: int = 0
    geo_unknown: int = 0
    geo_out: int = 0
    after_dedup: int = 0
    dedup_removed: int = 0
    relevant: int = 0
    new_bids: int = 0
    updated_bids: int = 0

    digest_sent: bool = False
    error_summary: str = ""

    sources: dict[str, SourceStat] = field(default_factory=dict)
    portals: list[dict] = field(default_factory=list)   # PlanetBids per-portal rows

    # -- source accessor ----------------------------------------------------
    def source(self, name: str | None) -> SourceStat:
        key = name or "Unknown"
        if key not in self.sources:
            self.sources[key] = SourceStat(source=key)
        return self.sources[key]

    def mark_error(self, source_label: str, exc: BaseException) -> None:
        s = self.source(source_label)
        s.status = "error"
        s.note = str(exc)[:300]
        frag = f"{source_label}: {exc}"
        self.error_summary = (self.error_summary + " · " + frag if self.error_summary else frag)[:600]

    @contextmanager
    def guard(self, source_label: str):
        """Wrap a source scrape: time it, and flag it 'error' if it raises."""
        t0 = time.time()
        try:
            yield
        except Exception as exc:  # noqa: BLE001 — we want everything
            self.mark_error(source_label, exc)
            print(f"    ⚠ {source_label} scrape failed: {exc}")
        finally:
            self.source(source_label).duration_secs = round(time.time() - t0, 1)

    # -- pipeline stages --------------------------------------------------
    def note_raw(self, bids: list[dict]) -> None:
        """Called with the combined pre-geo bid list."""
        self.raw_found = len(bids)
        for b in bids:
            self.source(b.get("source")).raw_count += 1

    def note_geo(self, bids_before_filter: list[dict]) -> None:
        """Called after enrich(), before the geo_status != 'out' filter."""
        for b in bids_before_filter:
            st = b.get("geo_status")
            if st == "out":
                self.geo_out += 1
            elif st == "unknown":
                self.geo_unknown += 1
            else:
                self.geo_in += 1

    def note_kept(self, bids_after_geo: list[dict]) -> None:
        for b in bids_after_geo:
            self.source(b.get("source")).kept_count += 1

    def note_final(self, deduped: list[dict], pre_dedup_count: int) -> None:
        self.after_dedup = len(deduped)
        self.dedup_removed = max(0, pre_dedup_count - len(deduped))
        self.relevant = sum(1 for b in deduped if b.get("is_relevant"))
        for b in deduped:
            if b.get("is_relevant"):
                self.source(b.get("source")).relevant_count += 1

    def note_new(self, bids: list[dict]) -> None:
        """Per-source new counts from the `_is_new` flag set by upsert_bids."""
        for b in bids:
            if b.get("_is_new"):
                self.source(b.get("source")).new_count += 1

    def infer_statuses(self) -> None:
        """Anything that scraped 0 rows and didn't raise → 'empty'."""
        for s in self.sources.values():
            if s.status == "ok" and s.raw_count == 0:
                s.status = "empty"

    def apply_planetbids_manifest(self, manifest: dict, portal_meta: dict) -> None:
        """
        Fold a pb_state manifest into the PlanetBids SourceStat + per-portal rows.
        `portal_meta` is scanner.PLANETBIDS_PORTALS  {pid: (agency, county)}.
        """
        if not manifest:
            return
        try:
            from scanner import PLANETBIDS_SKIP as _pb_skip
        except Exception:
            _pb_skip = set()
        portals = {pid: rec for pid, rec in manifest.get("portals", {}).items()
                   if pid not in _pb_skip}
        counts = {"ok": 0, "empty": 0, "blocked": 0, "error": 0, "pending": 0}
        for pid, rec in portals.items():
            st = rec.get("status", "pending")
            counts[st] = counts.get(st, 0) + 1
            agency, county = portal_meta.get(pid, (rec.get("agency", ""), None))
            self.portals.append({
                "portal_id": pid,
                "agency": agency or rec.get("agency", ""),
                "county": county,
                "status": st,
                "bid_count": rec.get("bid_count", 0),
                "checked_at": rec.get("checked_at"),
            })

        s = self.source("PlanetBids")
        s.portals_total = len(portals)
        s.portals_ok = counts["ok"]
        s.portals_blocked = counts["blocked"] + counts["error"]
        unfinished = counts["blocked"] + counts["error"] + counts["pending"]
        if s.status == "error":
            pass
        elif counts["ok"] == 0 and unfinished:
            s.status = "blocked"
        elif unfinished:
            s.status = "partial"
        elif counts["ok"]:
            s.status = "ok"
        else:
            s.status = "empty"
        if unfinished:
            s.note = (f"{counts['ok']} ok · {counts['empty']} empty · "
                      f"{counts['blocked']} blocked · {counts['error']} error · "
                      f"{counts['pending']} pending")

    def finish(self, duration_secs: float | None = None) -> None:
        self.finished_at = _utcnow()
        if duration_secs is not None:
            self.duration_secs = round(duration_secs, 1)
        self.infer_statuses()

    # -- serialization for db.log_scan_run --------------------------------
    def run_row(self) -> dict:
        return {
            "mode": self.mode,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_secs": round(self.duration_secs, 1),
            "raw_found": self.raw_found,
            "geo_in": self.geo_in,
            "geo_unknown": self.geo_unknown,
            "geo_out": self.geo_out,
            "after_dedup": self.after_dedup,
            "dedup_removed": self.dedup_removed,
            "relevant": self.relevant,
            "new_bids": self.new_bids,
            "updated_bids": self.updated_bids,
            "digest_sent": self.digest_sent,
            "error_summary": self.error_summary or None,
        }

    def source_rows(self, scan_run_id: str) -> list[dict]:
        rows = []
        for s in self.sources.values():
            rows.append({
                "scan_run_id": scan_run_id,
                "source": s.source,
                "raw_count": s.raw_count,
                "kept_count": s.kept_count,
                "relevant_count": s.relevant_count,
                "new_count": s.new_count,
                "status": s.status,
                "portals_total": s.portals_total,
                "portals_ok": s.portals_ok,
                "portals_blocked": s.portals_blocked,
                "note": s.note or None,
                "duration_secs": s.duration_secs,
            })
        return rows

    def portal_rows(self, scan_run_id: str) -> list[dict]:
        return [{"scan_run_id": scan_run_id, **p} for p in self.portals]
