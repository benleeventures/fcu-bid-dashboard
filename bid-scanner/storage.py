"""
FCU Bid Scanner — cloud mirror for downloaded bid documents.

parser.py downloads agency bid PDFs to output/specs/ (local, gitignored). This
module pushes those files to Supabase Storage (public bucket `bid-docs`) and
records one row per file in the `bid_documents` table, so the dashboard bid page
and the Airtable tracker can link straight to them.

Nothing here touches a portal or a browser — it works entirely from files
already on disk. It's called from parser.download_all()'s reconcile pass (same
process, same loop, no second crawl) and from `parser.py --sync-docs` (a
disk-only backfill).

No-ops cleanly when SUPABASE_URL / SUPABASE_KEY are absent, so local dev without
credentials still runs.

Requires: `supabase/add_bid_documents.sql` applied + a public `bid-docs` bucket.
"""

import hashlib
import mimetypes
import os
from pathlib import Path

BUCKET = "bid-docs"

# Sources whose download handler enumerates the *entire* document set from the
# portal (not just a best-guess primary PDF). For these, captured == complete,
# so we record docs_expected = docs_captured and the dashboard shows "N of N".
# Everything else leaves docs_expected NULL → dashboard shows "primary only".
# The dashboard's full per-source classification (incl. "unsupported" portals
# we can't retrieve from at all) lives in app/lib/docSources.ts — keep in sync.
COMPLETE_SOURCES = {"BidNet Direct", "Caltrans CCOP", "Cal eProcure"}

# Extensions we treat as real bid documents. Everything else in a bid dir
# (thumbnails, .DS_Store, .json state) is skipped.
_DOC_EXTS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".zip", ".jpg", ".jpeg", ".png"}


def _enabled() -> bool:
    return bool(os.getenv("SUPABASE_URL", "").strip() and os.getenv("SUPABASE_KEY", "").strip())


_CLIENT = None


def _client():
    global _CLIENT
    if _CLIENT is None:
        from supabase import create_client
        _CLIENT = create_client(
            os.getenv("SUPABASE_URL").strip(), os.getenv("SUPABASE_KEY").strip()
        )
    return _CLIENT


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _content_type(path: Path, data: bytes) -> str:
    if data[:4] == b"%PDF":
        return "application/pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:2] == b"PK":
        # zip / docx / xlsx — let the extension decide
        return mimetypes.guess_type(path.name)[0] or "application/zip"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _public_url(storage_path: str) -> str:
    base = os.getenv("SUPABASE_URL").strip().rstrip("/")
    return f"{base}/storage/v1/object/public/{BUCKET}/{storage_path}"


def _classify(path: Path, is_flat: bool) -> str:
    if path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        return "page_image"
    return "primary" if is_flat else "attachment"


def _collect_files(bid_id: str) -> list[tuple[Path, bool]]:
    """(path, is_flat) for every real document file belonging to this bid.
    De-dupes the flat output/specs/<id>.pdf against an identical copy inside
    output/specs/<id>/ (BidNet / CCOP write both)."""
    from parser import _flat_pdf, _bid_dir

    out: list[tuple[Path, bool]] = []
    seen_sha: set[str] = set()

    flat = _flat_pdf(bid_id)
    if flat.exists() and flat.is_file():
        seen_sha.add(_sha256(flat.read_bytes()))
        out.append((flat, True))

    bdir = _bid_dir(bid_id)
    if bdir.exists() and bdir.is_dir():
        for f in sorted(bdir.iterdir()):
            if not f.is_file() or f.suffix.lower() not in _DOC_EXTS:
                continue
            sha = _sha256(f.read_bytes())
            if sha in seen_sha:
                continue
            seen_sha.add(sha)
            out.append((f, False))

    return out


def upload_file(bid_id: str, path: Path, is_flat: bool, source_url: str | None) -> dict | None:
    """Upload one file, upsert its bid_documents row, return the row.
    Skips the upload (but still returns the row) when an identical file
    (same sha256) is already recorded — makes re-runs cheap and idempotent."""
    from parser import _safe_id

    data = path.read_bytes()
    if not data:
        return None
    sha = _sha256(data)
    storage_path = f"{_safe_id(bid_id)}/{path.name}"

    sb = _client()

    existing = (
        sb.table("bid_documents")
        .select("*")
        .eq("bid_id", bid_id)
        .eq("filename", path.name)
        .limit(1)
        .execute()
    ).data
    if existing and existing[0].get("sha256") == sha:
        return existing[0]

    ctype = _content_type(path, data)
    try:
        sb.storage.from_(BUCKET).upload(
            storage_path, data,
            {"content-type": ctype, "upsert": "true"},
        )
    except Exception as e:
        print(f"    ⚠ storage upload failed for {path.name}: {e}")
        return None

    row = {
        "bid_id":       bid_id,
        "filename":     path.name,
        "storage_path": f"{BUCKET}/{storage_path}",
        "public_url":   _public_url(storage_path),
        "source_url":   source_url,
        "content_type": ctype,
        "bytes":        len(data),
        "sha256":       sha,
        "kind":         _classify(path, is_flat),
    }
    sb.table("bid_documents").upsert(row, on_conflict="bid_id,filename").execute()
    return row


def sync_bid_docs(bid_id: str, source: str = "", source_url: str | None = None,
                  expected: int | None = None, push_airtable: bool = True) -> list[dict]:
    """Mirror every local document for one bid to Supabase Storage, update the
    bids doc-status columns, point bid_specs.pdf_url at the primary file, and
    (optionally) push links into Airtable. Returns the bid_documents rows.

    source   — download handler / portal name, for bids.docs_source
    expected — count of attachments the portal advertised, when the handler
               could enumerate them (BidNet, CCOP); None otherwise
    """
    if not _enabled():
        return []

    files = _collect_files(bid_id)
    if not files:
        return []

    if expected is None and source in COMPLETE_SOURCES:
        expected = len(files)

    rows: list[dict] = []
    for path, is_flat in files:
        r = upload_file(bid_id, path, is_flat, source_url)
        if r:
            rows.append(r)
    if not rows:
        return []

    sb = _client()

    from datetime import datetime, timezone
    sb.table("bids").update({
        "docs_captured":  len(rows),
        "docs_expected":  expected,
        "docs_synced_at": datetime.now(timezone.utc).isoformat(),
        "docs_source":    source or None,
    }).eq("bid_id", bid_id).execute()

    primary = next((r for r in rows if r["kind"] == "primary"), rows[0])
    try:
        sb.table("bid_specs").update({
            "pdf_url":      primary["public_url"],
            "pdf_filename": primary["filename"],
        }).eq("bid_id", bid_id).execute()
    except Exception:
        pass  # no spec row yet — save_spec will still set pdf_filename later

    print(f"    ☁ mirrored {len(rows)} document(s) → {BUCKET}/{bid_id}")

    if push_airtable and os.getenv("AIRTABLE_API_KEY") and os.getenv("AIRTABLE_BASE_ID"):
        try:
            from airtable_sync import update_bid_documents
            if update_bid_documents(bid_id, rows):
                print(f"    ✓ Airtable documents updated")
        except Exception as e:
            print(f"    ⚠ Airtable doc sync failed: {e}")

    return rows


def delete_bid_docs(bid_id: str) -> int:
    """Remove a bid's mirrored files + rows (housekeeping for the expirer).
    Returns the number of files removed."""
    if not _enabled():
        return 0
    from parser import _safe_id

    sb = _client()
    rows = (sb.table("bid_documents").select("filename").eq("bid_id", bid_id).execute()).data or []
    if rows:
        paths = [f"{_safe_id(bid_id)}/{r['filename']}" for r in rows]
        try:
            sb.storage.from_(BUCKET).remove(paths)
        except Exception as e:
            print(f"  ⚠ storage remove failed for {bid_id}: {e}")
    sb.table("bid_documents").delete().eq("bid_id", bid_id).execute()
    sb.table("bids").update({
        "docs_captured": 0, "docs_expected": None,
        "docs_synced_at": None, "docs_source": None,
    }).eq("bid_id", bid_id).execute()
    return len(rows)


def sync_all_local(only: str | None = None) -> None:
    """Disk-only backfill: walk output/specs/ and mirror every bid that has
    files. No portal access. Backs `python parser.py --sync-docs`."""
    if not _enabled():
        print("SUPABASE_URL / SUPABASE_KEY not set — nothing to sync.")
        return
    from parser import SPECS_DIR, _flat_pdf, _bid_dir

    if not SPECS_DIR.exists():
        print("No output/specs/ directory — run --download first.")
        return

    bid_ids: set[str] = set()
    for p in SPECS_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in _DOC_EXTS:
            bid_ids.add(p.stem)
        elif p.is_dir():
            bid_ids.add(p.name)

    if only:
        bid_ids = {b for b in bid_ids if b == str(only)}

    if not bid_ids:
        print("No local documents found to sync.")
        return

    # Map the on-disk _safe_id back to a real bid_id via the bids table so
    # foreign-key writes and Airtable lookups use the canonical id.
    sb = _client()
    q = sb.table("bids").select("bid_id,source,url")
    if not only:
        q = q.eq("is_relevant", True)   # bulk backfill stays scoped to relevant bids
    all_bids = (q.execute()).data or []
    by_safe = {}
    from parser import _safe_id
    for b in all_bids:
        by_safe.setdefault(_safe_id(b["bid_id"]), b)

    print(f"Syncing local documents for {len(bid_ids)} bid(s)...")
    synced = 0
    for safe in sorted(bid_ids):
        b = by_safe.get(safe)
        if not b:
            print(f"  ⚠ {safe}: no matching bids row — skipped")
            continue
        rows = sync_bid_docs(b["bid_id"], source=b.get("source") or "", source_url=b.get("url"))
        if rows:
            synced += 1
    print(f"Done. {synced} bid(s) mirrored.")
