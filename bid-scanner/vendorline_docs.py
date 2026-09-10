"""
FCU Bid Agent — VendorLine / PlanetBids document retrieval (on-demand, CAPTCHA-solved)

VendorLine has no document API. Its bids are PlanetBids agency-portal bids, and
the portal's "Bid Documents" tab sits behind the same Cloudflare/WAF CAPTCHA
that forces `--source planetbids` and `--intel` to run as headed-Chrome sessions
with a manual solve. The headless nightly parser (`parser.download_all`) can't
reach them, so this runs separately, on demand:

  python main.py --vl-docs                 # every relevant VendorLine bid missing docs
  python main.py --vl-docs --bid VL-57760-144851   # just one

Flow (mirrors `main.py --intel`):
  1. Open real Chrome on a warm-up portal, you solve one CAPTCHA, press Enter.
  2. For each VendorLine bid still missing documents: warm its portal, open the
     bo-detail page, click "Bid Documents", capture the /papi/ document list +
     scrape the DOM, download every file to output/specs/<bid_id>/.
  3. Hand off to storage.sync_bid_docs() — same mirror path as every other
     source: Supabase Storage (`bid-docs`) → dashboard bid page → Airtable.

Once the docs are on disk, `python parser.py --parse-all --claude --bid <id>`
scores the bid like any other.
"""

import asyncio
import os
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from intel_scanner import PLANETBIDS_BASE, _warm_portal

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
WARMUP_PORTAL = "39493"  # Beverly Hills — same portal --intel uses for the solve

_DOC_EXT_RE = re.compile(r"\.(pdf|docx?|xlsx?|zip|txt|rtf)(\?|$)", re.I)
_BID_ID_RE = re.compile(r"VL-(\d+)-(\d+)")


# ---------------------------------------------------------------------------
# Which bids need documents
# ---------------------------------------------------------------------------

def bids_needing_docs(only: str | None = None) -> list[dict]:
    """Relevant, still-open VendorLine bids that have no mirrored documents yet.

    'No documents' = bids.docs_captured is null/0 AND no bid_documents rows, so a
    re-run only touches what's still missing. Past-due and terminal-parse bids
    are skipped (nothing to bid on / already given up)."""
    from parser import _sb, _TERMINAL_PARSE
    from datetime import date

    sb = _sb()
    try:
        rows = (
            sb.table("bids")
            .select("bid_id,title,source,url,due_date,parse_status,parse_attempts,docs_captured")
            .eq("source", "VendorLine")
            .eq("is_relevant", True)
            .execute()
        ).data or []
    except Exception as e:
        print(f"  ⚠ bids query failed: {e}")
        return []

    if only:
        rows = [b for b in rows if str(b["bid_id"]) == str(only)]

    have_docs = set()
    ids = [b["bid_id"] for b in rows]
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        r = sb.table("bid_documents").select("bid_id").in_("bid_id", chunk).execute()
        have_docs.update(row["bid_id"] for row in (r.data or []))

    today = date.today()
    out = []
    for b in rows:
        if not only:
            if b["bid_id"] in have_docs or (b.get("docs_captured") or 0) > 0:
                continue
            if (b.get("parse_status") or "") in _TERMINAL_PARSE:
                continue
            due = b.get("due_date")
            if due:
                try:
                    if date.fromisoformat(str(due)) < today:
                        continue
                except ValueError:
                    pass
        if not _BID_ID_RE.match(str(b["bid_id"])):
            print(f"  ⚠ {b['bid_id']}: not a VL-<cid>-<bid> id — skipped")
            continue
        out.append(b)
    return out


# ---------------------------------------------------------------------------
# Document discovery on a bo-detail page
# ---------------------------------------------------------------------------

def _walk_json_for_docs(node, acc: list[dict]):
    """Recursively pull anything that looks like a bid document out of a /papi/
    JSON payload: a dict carrying a filename-ish key, or an id under a
    'document'-flavoured container. Collects {name, id, url} candidates."""
    if isinstance(node, dict):
        # JSON:API shape — {id, type, attributes:{...}}. Flatten so the filename
        # on `attributes` and the id on the resource are seen together.
        flat = dict(node)
        if isinstance(node.get("attributes"), dict):
            flat = {**node["attributes"], **{k: node[k] for k in ("id", "type") if k in node}}
        keys = {k.lower() for k in flat.keys()}
        name = None
        for k in ("filename", "fileName", "documentName", "docName", "originalName",
                  "name", "title"):
            if flat.get(k) and isinstance(flat[k], str):
                name = flat[k]
                break
        type_hint = str(flat.get("type") or "").lower()
        looks_doc = bool(name and _DOC_EXT_RE.search(name)) or (
            bool(name) and bool(keys & {"documentid", "biddocumentid", "fileid",
                                        "s3key", "filekey", "filesize", "mimetype", "contenttype"})
        ) or ("document" in type_hint and name is not None)
        if looks_doc:
            url = None
            for k in ("downloadUrl", "downloadURL", "url", "fileUrl", "s3Url", "publicUrl", "href"):
                if isinstance(flat.get(k), str) and flat[k].startswith("http"):
                    url = flat[k]
                    break
            acc.append({
                "name": name,
                "id": flat.get("documentId") or flat.get("bidDocumentId") or flat.get("id"),
                "url": url,
            })
        for v in node.values():
            _walk_json_for_docs(v, acc)
    elif isinstance(node, list):
        for v in node:
            _walk_json_for_docs(v, acc)


async def _fetch_bid_documents(page, portal_id: str, numeric_bid_id: str) -> list[tuple[int, str, str]]:
    """Open one bid's detail page (portal already CAPTCHA-cleared this session),
    open the Bid Documents tab, and return scored (score, href, text) candidates
    in the shape parser._download_scored_docs expects. Empty list = nothing found
    / CAPTCHA wall."""
    captured: list[dict] = []
    seen_papi: set[str] = set()

    async def on_response(response):
        url = response.url
        if "/papi/" not in url or url in seen_papi:
            return
        seen_papi.add(url)
        try:
            data = await response.json()
        except Exception:
            return
        _walk_json_for_docs(data, captured)

    detail_url = f"{PLANETBIDS_BASE}/portal/{portal_id}/bo/bo-detail/{numeric_bid_id}"
    page.on("response", on_response)
    try:
        await _warm_portal(page, portal_id)
        try:
            await page.goto(detail_url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"      ⚠ detail page load error: {e}")
            return []
        await page.wait_for_timeout(3500)

        body = ""
        try:
            body = await page.inner_text("body")
        except Exception:
            pass
        if any(w in body.lower() for w in ("confirm you are human", "security check", "verify you are")):
            print(f"      ⚠ CAPTCHA wall on {detail_url} — solve it in Chrome, then re-run")
            return []

        # Open the Bid Documents tab to trigger the lazy /papi/ document fetch
        for sel in (
            'button:has-text("Bid Documents")', 'a:has-text("Bid Documents")',
            'li:has-text("Bid Documents")', 'button:has-text("Documents")',
            'a:has-text("Documents")', 'li:has-text("Documents")',
            '[data-tab*="document" i]', '[id*="document" i]',
        ):
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.click()
                    await page.wait_for_timeout(2500)
                    break
            except Exception:
                pass
        await page.wait_for_timeout(1500)

        # DOM scrape: real anchor links to files
        dom_links: list[tuple[str, str]] = []
        try:
            anchors = await page.query_selector_all("a[href]")
            for a in anchors:
                href = await a.get_attribute("href") or ""
                text = ((await a.inner_text()) or "").strip()
                low = href.lower()
                if (_DOC_EXT_RE.search(low) or "files-prod" in low or "s3.amazonaws" in low
                        or "/papi/" in low and "document" in low
                        or "download" in low and _DOC_EXT_RE.search(text.lower() or "")):
                    dom_links.append((urljoin(page.url, href), text))
        except Exception:
            pass
    finally:
        page.remove_listener("response", on_response)

    scored: list[tuple[int, str, str]] = []
    seen: set[str] = set()

    def _add(url: str, text: str):
        if not url or url in seen:
            return
        seen.add(url)
        tl = (text or "").lower()
        score = 0
        if any(k in tl for k in ("addendum", "notice of", "sign-in", "planholder")):
            score -= 4
        if any(k in tl for k in ("invitation", "itb", "ifb", "rfp", "specification",
                                 "scope", "bid package", "project manual", "plans", "sow")):
            score += 5
        if _DOC_EXT_RE.search(url.lower()):
            score += 3
        scored.append((score, url, text or Path(urlparse(url).path).name))

    for d in captured:
        if d.get("url"):
            _add(d["url"], d.get("name") or "")
        elif d.get("id"):
            # PlanetBids serves a bid document by id off the papi base
            _add(f"{PLANETBIDS_BASE}/papi/bidDocuments/{d['id']}", d.get("name") or "")
    for url, text in dom_links:
        _add(url, text)

    if scored:
        print(f"      → {len(captured)} papi doc record(s), {len(dom_links)} DOM link(s), "
              f"{len(scored)} unique candidate(s)")
    else:
        # Nothing found — dump what the page did fetch so the selectors/endpoints
        # can be refined (same first-run debugging pattern as the intel scanner).
        eps = sorted({u.split("/papi/")[-1].split("?")[0] for u in seen_papi})
        print(f"      → no document candidates. papi endpoints seen: {eps or '(none)'}")
    return scored


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

async def run_vl_doc_sync(only: str | None = None) -> dict:
    from playwright.async_api import async_playwright
    from parser import _bid_dir, _download_scored_docs, mark_parse_status, MAX_PARSE_ATTEMPTS
    from storage import sync_bid_docs

    bids = bids_needing_docs(only=only)
    if not bids:
        print("No VendorLine bids need documents.")
        return {"bids": 0, "with_docs": 0}

    print(f"{len(bids)} VendorLine bid(s) missing documents:")
    for b in bids:
        print(f"  · {b['bid_id']}  {b['title'][:60]}")
    print()

    with_docs = 0
    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(channel="chrome", headless=False)
        except Exception:
            browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()

        target = f"{PLANETBIDS_BASE}/portal/{WARMUP_PORTAL}/bo/bo-search"
        print(f"Opening Chrome → {target}")
        try:
            await page.goto(target, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass
        print("\n→ Solve the CAPTCHA in the Chrome window.")
        print("→ Press Enter here when done.")
        await asyncio.get_event_loop().run_in_executor(None, input, "")

        for b in bids:
            bid_id = b["bid_id"]
            m = _BID_ID_RE.match(str(bid_id))
            cid, numeric_id = m.group(1), m.group(2)
            print(f"\n→ {bid_id}  [{cid}/{numeric_id}]  {b['title'][:55]}")

            try:
                scored = await _fetch_bid_documents(page, cid, numeric_id)
            except Exception as e:
                print(f"    ⚠ error: {e}")
                scored = []

            if not scored:
                print("    ⚠ no documents found")
                attempts = (b.get("parse_attempts") or 0) + 1
                if attempts >= MAX_PARSE_ATTEMPTS:
                    mark_parse_status(bid_id, "no_docs",
                                      f"no VendorLine/PlanetBids documents after {attempts} attempts")
                else:
                    mark_parse_status(bid_id, None, "vl-docs attempt — nothing captured")
                continue

            n = await _download_scored_docs(ctx, bid_id, scored, page.url)
            if not n:
                print("    ⚠ candidates found but none downloaded (HTML/error pages)")
                mark_parse_status(bid_id, None, "vl-docs attempt — candidates unreachable")
                continue

            print(f"    ✓ {n} document(s) saved")
            # The Bid Documents tab is the complete set → record N of N.
            try:
                sync_bid_docs(bid_id, source="VendorLine", source_url=b.get("url"),
                              expected=n)
                with_docs += 1
            except Exception as e:
                print(f"    ⚠ doc mirror failed for {bid_id}: {e}")

        await browser.close()

    print(f"\n✓ VendorLine doc sync complete — {with_docs}/{len(bids)} bid(s) now have documents")
    print("  Score them:  python parser.py --parse-all --claude")
    return {"bids": len(bids), "with_docs": with_docs}
