"""
FCU Bid Agent — Document Parser (Step 2)

Workflows:

  Download PDFs:
    python parser.py --download

  Parse PDFs (AI-assisted):
    python parser.py --pending           # list PDFs ready to parse
    python parser.py --parse-all         # print manual parsing prompts (use with Claude Code)
    python parser.py --parse-all --ollama  # auto-parse via local Ollama (LLaMA 3 etc.)

  Save extracted spec (after reading PDF manually or with Claude Code):
    python parser.py --save <bid_id> '<json>'

  List:
    python parser.py --list              # show unprocessed relevant bids

JSON schema for --save:
  {
    "flooring_types": ["carpet", "LVT", "VCT"],
    "total_sqft": 4500,
    "rooms": "Classrooms, hallways, admin offices",
    "prevailing_wage": true,
    "bid_bond": true,
    "bid_bond_pct": 10,
    "walk_required": true,
    "walk_date_raw": "May 15, 2026 at 10:00 AM",
    "summary": "Two-sentence plain English summary of scope."
  }
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import date

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SCRIPT_DIR    = Path(__file__).parent
SPECS_DIR     = SCRIPT_DIR / "output" / "specs"
COOKIES_PB    = SCRIPT_DIR / "cookies.json"
BIDNET_LOGIN  = "https://www.bidnetdirect.com/login"


# ─────────────────────────────────────────────
# Supabase helpers
# ─────────────────────────────────────────────

def _sb():
    from supabase import create_client
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY required in .env")
    return create_client(url, key)


def get_unprocessed_bids() -> list[dict]:
    """Relevant bids with no entry in bid_specs."""
    sb = _sb()
    resp = sb.table("bids").select("bid_id,title,source,url").eq("is_relevant", True).execute()
    all_relevant = resp.data or []
    if not all_relevant:
        return []

    ids = [b["bid_id"] for b in all_relevant]
    parsed_ids = set()
    for i in range(0, len(ids), 200):
        r = sb.table("bid_specs").select("bid_id").in_("bid_id", ids[i:i+200]).execute()
        parsed_ids.update(row["bid_id"] for row in (r.data or []))

    return [b for b in all_relevant if b["bid_id"] not in parsed_ids]


def save_spec(bid_id: str, spec: dict, pdf_path: str = ""):
    sb = _sb()

    walk_date = None
    if spec.get("walk_date_raw"):
        walk_date = _parse_date(spec["walk_date_raw"])

    row = {
        "bid_id":          bid_id,
        "flooring_types":  spec.get("flooring_types") or [],
        "total_sqft":      spec.get("total_sqft"),
        "rooms":           (spec.get("rooms") or "")[:500],
        "prevailing_wage": spec.get("prevailing_wage"),
        "bid_bond":        spec.get("bid_bond"),
        "bid_bond_pct":    spec.get("bid_bond_pct"),
        "walk_required":   spec.get("walk_required"),
        "walk_date":       walk_date,
        "walk_date_raw":   (spec.get("walk_date_raw") or "")[:200],
        "summary":         (spec.get("summary") or "")[:1000],
        "raw_extract":     spec,
        "pdf_filename":    Path(pdf_path).name if pdf_path else None,
    }
    sb.table("bid_specs").upsert(row, on_conflict="bid_id").execute()
    print(f"✓ Saved spec for {bid_id}")


def _parse_date(raw: str) -> str | None:
    import re as _re
    months = {
        "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
        "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
        "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,
        "sep":9,"oct":10,"nov":11,"dec":12,
    }
    m = _re.search(r'(\w+)\s+(\d{1,2}),?\s+(\d{4})', raw, _re.IGNORECASE)
    if m:
        mon = months.get(m.group(1).lower())
        if mon:
            try:
                return date(int(m.group(3)), mon, int(m.group(2))).isoformat()
            except ValueError:
                pass
    return None


# ─────────────────────────────────────────────
# PDF download via Playwright
# ─────────────────────────────────────────────

async def download_all():
    import json as _json
    from playwright.async_api import async_playwright
    import urllib.parse

    SPECS_DIR.mkdir(parents=True, exist_ok=True)
    bids = get_unprocessed_bids()

    # Skip bids already downloaded
    pending = []
    already = []
    for b in bids:
        pdf_path = SPECS_DIR / f"{b['bid_id']}.pdf"
        if pdf_path.exists():
            already.append(b)
        else:
            pending.append(b)

    print(f"Unprocessed relevant bids: {len(bids)}")
    if already:
        print(f"  {len(already)} already downloaded (run --pending to list)")
    if not pending:
        print("Nothing new to download.")
        return

    print(f"  {len(pending)} to download\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        # Load PlanetBids cookies
        if COOKIES_PB.exists():
            with open(COOKIES_PB) as f:
                await context.add_cookies(_json.load(f))

        # Sources that block headless scraping — skip PDF download, flag for manual review
        BLOCKED_SOURCES = {
            "Caltrans CCOP":  "Requires login (CaleProcure account)",
            "OpenGov":        "Cloudflare Turnstile — blocks all automation",
        }

        # Log in to BidNet once if any BidNet bids need downloading
        bidnet_pending = [b for b in pending if b.get("source") == "BidNet Direct"]
        bidnet_logged_in = False
        if bidnet_pending:
            bidnet_page = await context.new_page()
            bidnet_logged_in = await _bidnet_login(bidnet_page)
            if bidnet_logged_in:
                print(f"  ✓ BidNet Direct: logged in — {len(bidnet_pending)} bids to download")
            else:
                print("  ⚠ BidNet Direct: login failed — check BIDNET_EMAIL / BIDNET_PASSWORD in .env")
            await bidnet_page.close()

        for b in pending:
            bid_id = b["bid_id"]
            url    = b.get("url", "")
            source = b.get("source", "")
            title  = b["title"][:55]
            out    = SPECS_DIR / f"{bid_id}.pdf"

            print(f"→ {bid_id}  [{source}]  {title}")

            if source in BLOCKED_SOURCES:
                print(f"    ⚠ SKIP — {BLOCKED_SOURCES[source]}\n")
                continue

            if not url:
                print("    ⚠ No URL\n"); continue

            # BidNet Direct — download all documents from Documents tab
            if source == "BidNet Direct":
                if not bidnet_logged_in:
                    print("    ⚠ SKIP — BidNet login failed\n")
                    continue
                page = await context.new_page()
                try:
                    downloaded = await _download_bidnet_docs(page, context, bid_id, url)
                    if downloaded:
                        # Use the solicitation PDF as the canonical spec file
                        sol = next((d for d in downloaded if "solicitation" in d.lower() or "ifpq" in d.lower() or "ifb" in d.lower()), downloaded[0])
                        sol_path = SPECS_DIR / bid_id / sol
                        if sol_path.exists():
                            # Symlink/copy primary file to the flat {bid_id}.pdf location
                            out.write_bytes(sol_path.read_bytes())
                    else:
                        print(f"    ⚠ No documents found\n")
                except Exception as e:
                    print(f"    ⚠ BidNet error: {e}\n")
                finally:
                    await page.close()
                continue

            page = await context.new_page()
            try:
                await page.goto(url, timeout=30000, wait_until="domcontentloaded")

                if source == "SAM.gov":
                    pdf_href = await _find_samgov_pdf(page, context)
                else:
                    await page.wait_for_timeout(2000)
                    pdf_href = await _find_generic_pdf(page)

                if not pdf_href:
                    print("    ⚠ No PDF link found\n"); await page.close(); continue

                # SAM.gov hrefs are relative — resolve to absolute
                if pdf_href.startswith("/"):
                    pdf_href = "https://sam.gov" + pdf_href

                pdf_href = urllib.parse.urljoin(page.url, pdf_href)
                resp = await context.request.get(pdf_href, timeout=30000)
                ct = resp.headers.get("content-type", "")
                if "pdf" not in ct and not pdf_href.lower().endswith(".pdf"):
                    print(f"    ⚠ Not a PDF ({ct})\n"); await page.close(); continue

                data = await resp.body()
                if not data or b"%PDF" not in data[:10]:
                    print("    ⚠ Response is not a valid PDF\n"); await page.close(); continue

                out.write_bytes(data)
                print(f"    ✓ Saved {out.name} ({len(data)//1024} KB)\n")

            except Exception as e:
                print(f"    ⚠ Error: {e}\n")
            finally:
                await page.close()

        await browser.close()

    print(f"Done. PDFs saved to {SPECS_DIR}/")
    print("Now run: python parser.py --pending  to see what needs parsing")


async def _bidnet_login(page) -> bool:
    """Log in to BidNet Direct with email/password. No CAPTCHA — fully automated."""
    email    = os.getenv("BIDNET_EMAIL", "")
    password = os.getenv("BIDNET_PASSWORD", "")
    if not email or not password:
        print("  ⚠ BIDNET_EMAIL / BIDNET_PASSWORD not set in .env")
        return False
    try:
        await page.goto(BIDNET_LOGIN, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1500)

        # BidNet uses SAML2 SSO — fields are j_username / j_password
        await page.fill('#j_username, input[name="j_username"]', email)
        await page.fill('#j_password, input[name="j_password"]', password)
        await page.click('#loginButton, button[type="submit"]')
        # Wait for navigation — networkidle hangs on BidNet SPA, use domcontentloaded + pause
        await page.wait_for_load_state("domcontentloaded", timeout=20000)
        await page.wait_for_timeout(3000)

        # If password field is still visible, login failed
        still_on_login = await page.query_selector('input[type="password"]')
        return still_on_login is None
    except Exception as e:
        print(f"  ⚠ BidNet login error: {e}")
        return False


async def _download_bidnet_docs(page, context, bid_id: str, bid_url: str) -> list[str]:
    """
    Download all PDFs from a BidNet bid's Documents tab.
    Saves to output/specs/{bid_id}/ and returns list of filenames downloaded.

    BidNet private portal URL pattern (constructed from numeric bid_id):
      /private/supplier/solicitations/notice/{bid_id}/abstract
    Clicking the Documents tab loads /abstract/documents via AJAX.
    PDF links: a[href*="/notice/attachment/"][href*="/download"]
    """
    import urllib.parse as _up

    bid_dir = SPECS_DIR / bid_id
    bid_dir.mkdir(parents=True, exist_ok=True)

    # Build the private notice URL from bid_id (numeric ID)
    notice_url = f"https://www.bidnetdirect.com/private/supplier/solicitations/notice/{bid_id}/abstract"
    await page.goto(notice_url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)

    # Click the Documents tab — triggers AJAX load to /abstract/documents
    docs_tab = await page.query_selector('a[href*="innerTabId=documents"]')
    if docs_tab:
        await docs_tab.click()
        # Wait for document links to appear in DOM (federal/aggregated bids load slower)
        try:
            await page.wait_for_selector(
                'a[href*="/notice/attachment/"]',
                timeout=15000
            )
        except Exception:
            await page.wait_for_timeout(6000)

    # Collect all document download links (PDF, DOCX, and federal UUID-named files)
    link_els = await page.query_selector_all('a[href*="/notice/attachment/"]')
    candidates = []
    seen = set()
    for link in link_els:
        href = await link.get_attribute("href") or ""
        text = (await link.inner_text()).strip()
        if not href or href in seen:
            continue
        seen.add(href)
        full_url = href if href.startswith("http") else "https://www.bidnetdirect.com" + href
        # Use link text as filename if it has a known extension, else fall back to URL path
        known_exts = (".pdf", ".docx", ".doc", ".xlsx", ".zip")
        if any(text.lower().endswith(ext) for ext in known_exts):
            filename = text
        else:
            filename = Path(_up.urlparse(full_url).path).name
            if not any(filename.lower().endswith(ext) for ext in known_exts):
                filename += ".pdf"
        candidates.append({"filename": filename, "url": full_url})

    if not candidates:
        print(f"    ⚠ No documents found (tab may not have loaded)")
        return []

    downloaded = []
    for doc in candidates:
        out_path = bid_dir / doc["filename"]
        if out_path.exists():
            print(f"    ↩ Already exists: {doc['filename']}")
            downloaded.append(doc["filename"])
            continue
        try:
            resp = await context.request.get(doc["url"], timeout=30000)
            data = await resp.body()
            if not data:
                print(f"    ⚠ Empty response: {doc['filename']}")
                continue
            # Detect file type from magic bytes; fix extension for UUID-named files
            if data[:4] == b"%PDF":
                ext, valid = ".pdf", True
            elif data[:2] == b"PK":
                ext, valid = ".docx", True
            elif data[:4] == b"\xd0\xcf\x11\xe0":
                ext, valid = ".doc", True
            else:
                print(f"    ⚠ Unrecognized file format: {doc['filename']}")
                continue
            # Fix extension if filename has none or wrong one
            fname = doc["filename"]
            if not any(fname.lower().endswith(e) for e in (".pdf", ".docx", ".doc", ".xlsx", ".zip")):
                fname = fname + ext
            out_path = bid_dir / fname
            if out_path.exists():
                print(f"    ↩ Already exists: {fname}")
                downloaded.append(fname)
                continue
            out_path.write_bytes(data)
            print(f"    ✓ {fname} ({len(data)//1024} KB)")
            downloaded.append(fname)
        except Exception as e:
            print(f"    ⚠ Failed {doc['filename']}: {e}")

    return downloaded


async def _find_samgov_pdf(page, context) -> str | None:
    """
    SAM.gov: click the Attachments/Links tab, find the best spec PDF.
    Confirmed working: files served from /api/prod/opps/v3/opportunities/resources/files/
    with api_key=null — no login required for public solicitations.

    Note: DB stores /workspace/contract/opp/<id>/view URLs — redirect to /opp/<id>/view first.
    """
    import re as _re

    # Normalize URL: /workspace/contract/opp/<id>/view → /opp/<id>/view
    current_url = page.url
    m = _re.search(r"/opp/([a-f0-9]+)/", current_url)
    if m:
        opp_id = m.group(1)
        canonical = f"https://sam.gov/opp/{opp_id}/view"
        if canonical != current_url:
            await page.goto(canonical, timeout=30000, wait_until="domcontentloaded")

    # Wait for Angular to render — poll for the tab element
    for _ in range(6):
        tab = await page.query_selector("text=Attachments/Links")
        if tab:
            break
        await page.wait_for_timeout(2000)

    # Click Attachments/Links tab
    tab = await page.query_selector("text=Attachments/Links")
    if tab:
        await tab.click()
        await page.wait_for_timeout(3000)

    # Collect all PDF links with scoring
    links = await page.query_selector_all("a[href*='/api/prod/opps/v3/opportunities/resources/files/']")
    candidates = []
    for link in links:
        href = await link.get_attribute("href") or ""
        text = (await link.inner_text()).strip().lower()
        if not href:
            continue
        score = 0
        # Prefer SOW, specs, RFP over amendments and reports
        if any(k in text for k in ["sow", "scope", "specification", "rfp", "ifb", "itb", "solicitation"]):
            score += 10
        if any(k in text for k in ["carpet", "floor", "resilient", "09 68", "09 65"]):
            score += 8
        if any(k in text for k in ["amend", "acm report", "environmental", "contractor guide"]):
            score -= 5
        if "download all" in text:
            score -= 20  # skip "Download All" zip link
        candidates.append((score, href))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


async def _find_generic_pdf(page) -> str | None:
    """Generic: scored PDF link search for Quality Bidders, PlanetBids, etc."""
    links = await page.query_selector_all("a[href*='.pdf'], a[href*='download'], a[href*='attachment'], a[href*='s3.amazonaws']")
    candidates = []
    for link in links:
        href = await link.get_attribute("href") or ""
        text = (await link.inner_text()).strip().lower()
        if not href:
            continue
        # Skip known false positives: CaleProcure diversity guide, external resource docs
        if any(k in href.lower() for k in ["prismic.io", "diversity", "dgs.ca.gov", "dir.ca.gov"]):
            continue
        if any(k in text for k in ["diversity data", "diversity procedures"]):
            continue
        score = 0
        if any(k in text for k in ["addendum", "add #", "notice of"]):
            score -= 10
        if any(k in href.lower() for k in ["diversity", "procedures", "training"]):
            score -= 20
        if any(k in text for k in ["invitation", "itb", "rfp", "ifb", "specification", "scope", "bid package"]):
            score += 5
        if href.lower().endswith(".pdf") or "s3.amazonaws" in href:
            score += 3
        candidates.append((score, href))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def cmd_list():
    bids = get_unprocessed_bids()
    if not bids:
        print("✓ All relevant bids have specs.")
        return
    print(f"{len(bids)} unprocessed relevant bids:\n")
    for b in bids:
        pdf = SPECS_DIR / f"{b['bid_id']}.pdf"
        tag = "PDF ✓" if pdf.exists() else "no PDF"
        print(f"  [{tag:6}]  {b['bid_id']}  {b['title'][:55]}")


def cmd_pending():
    """List downloaded PDFs that still need parsing."""
    if not SPECS_DIR.exists():
        print("No specs directory yet. Run --download first.")
        return
    bids = {b["bid_id"]: b for b in get_unprocessed_bids()}
    pdfs = sorted(SPECS_DIR.glob("*.pdf"))
    if not pdfs:
        print("No PDFs downloaded yet.")
        return
    pending = [p for p in pdfs if p.stem in bids]
    if not pending:
        print("✓ All downloaded PDFs have been parsed.")
        return
    print(f"{len(pending)} PDFs ready to parse:\n")
    for p in pending:
        bid = bids.get(p.stem, {})
        size = p.stat().st_size // 1024
        print(f"  {p.stem}  ({size} KB)  {bid.get('title','')[:50]}")
        print(f"    → {p}")
    print(f"\nFor each, read the PDF and run:")
    print(f"  python parser.py --save <bid_id> '<json>'")


def cmd_save(args: list[str], trigger_alerts: bool = True):
    if len(args) < 2:
        print("Usage: python parser.py --save <bid_id> '<json>'")
        sys.exit(1)
    bid_id = args[0]
    json_str = args[1]
    try:
        spec = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}")
        sys.exit(1)
    pdf_path = str(SPECS_DIR / f"{bid_id}.pdf")
    save_spec(bid_id, spec, pdf_path)

    if trigger_alerts:
        _post_parse_alerts(bid_id, spec)


def _post_parse_alerts(bid_id: str, spec: dict):
    """Fire compliance + job walk alerts after a spec is saved."""
    try:
        sb = _sb()
        resp = sb.table("bids").select("*").eq("bid_id", bid_id).limit(1).execute()
        bids = resp.data or []
        if not bids:
            return
        bid = bids[0]
        from notify import send_compliance_alert, send_job_walk_alert
        send_compliance_alert(bid, spec)
        if spec.get("walk_required"):
            send_job_walk_alert(bid, spec)
    except Exception as e:
        print(f"  ⚠ Post-parse alerts failed: {e}")


# kept as alias for backward compat
def _trigger_job_walk_alert(bid_id: str, spec: dict):
    _post_parse_alerts(bid_id, spec)


# ─────────────────────────────────────────────
# Ollama parsing backend
# ─────────────────────────────────────────────

_EXTRACTION_PROMPT = """You are parsing a public works bid document for a flooring contractor.

Extract the following fields and return ONLY a valid JSON object — no markdown, no commentary.

{
  "flooring_types": ["list of flooring types found: carpet, LVT, VCT, tile, hardwood, window_coverings, blinds, etc. Empty array if none."],
  "total_sqft": <number or null — total square footage of flooring scope>,
  "rooms": "<comma-separated list of rooms or areas, e.g. 'Classrooms, hallways, admin offices'. Empty string if not specified.>",
  "prevailing_wage": <true if prevailing wage or certified payroll is required, false if not, null if unclear>,
  "bid_bond": <true if a bid bond is required, false if not, null if unclear>,
  "bid_bond_pct": <bid bond percentage as a number, e.g. 10 for 10%. null if not specified>,
  "walk_required": <true if a mandatory pre-bid job walk or site visit is required, false if not>,
  "walk_date_raw": "<the walk date/time as written in the document, e.g. 'May 15, 2026 at 10:00 AM'. Empty string if no walk required.>",
  "dvbe_required": <true if DVBE (Disabled Veteran Business Enterprise) participation is required, false if not, null if unclear>,
  "dvbe_pct": <DVBE participation percentage as a number if specified, e.g. 3. null if not specified>,
  "dbe_goal_pct": <DBE (Disadvantaged Business Enterprise) goal percentage as a number if stated, e.g. 5. null if not specified>,
  "summary": "<2-sentence plain English summary of the flooring scope. Focus on what materials, how much, and where.>"
}

Important:
- Return ONLY the JSON object. No other text.
- If a field cannot be determined, use null (not "unknown" or empty string, except for text fields).
- For flooring_types, use lowercase: carpet, lvt, vct, tile, hardwood, window_coverings, blinds, resilient."""


def _parse_with_ollama(pdf_path: Path) -> dict | None:
    """
    Send PDF text to local Ollama for structured extraction.
    Requires: Ollama running at OLLAMA_BASE_URL (default: http://localhost:11434)
    Model: OLLAMA_MODEL (default: llama3)
    """
    import urllib.request

    try:
        import pdfplumber
    except ImportError:
        print("  ⚠ pdfplumber not installed — run: pip install pdfplumber")
        return None

    # Extract text from PDF
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages = pdf.pages[:20]  # cap at 20 pages to stay within context
            text = "\n".join(p.extract_text() or "" for p in pages).strip()
    except Exception as e:
        print(f"  ⚠ PDF text extraction failed: {e}")
        return None

    if not text:
        print("  ⚠ No text extracted from PDF (may be a scanned image)")
        return None

    # Truncate to ~12K chars to stay within typical context limits
    text = text[:12000]

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3")

    payload = json.dumps({
        "model": model,
        "prompt": f"{_EXTRACTION_PROMPT}\n\n---\nBID DOCUMENT TEXT:\n{text}",
        "stream": False,
        "options": {"temperature": 0.1},
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            raw = result.get("response", "").strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  ⚠ Ollama returned invalid JSON: {e}")
        return None
    except Exception as e:
        print(f"  ⚠ Ollama error: {e}")
        return None


def cmd_parse_all(use_ollama: bool = False):
    """
    Parse all downloaded PDFs that don't yet have bid_specs.

    Without --ollama: prints a manual prompt for each PDF so you can parse
    with Claude Code and then run --save manually.

    With --ollama: auto-parses each PDF via local Ollama.
    """
    if not SPECS_DIR.exists():
        print("No specs directory. Run --download first.")
        return

    bids = {b["bid_id"]: b for b in get_unprocessed_bids()}
    pdfs = sorted(SPECS_DIR.glob("*.pdf"))
    pending = [p for p in pdfs if p.stem in bids]

    if not pending:
        print("✓ All downloaded PDFs have been parsed (or no PDFs yet — run --download).")
        return

    print(f"{len(pending)} PDF(s) to parse:\n")

    for pdf_path in pending:
        bid_id = pdf_path.stem
        bid = bids.get(bid_id, {})
        size_kb = pdf_path.stat().st_size // 1024
        title = bid.get("title", "")[:60]
        print(f"→ {bid_id}  ({size_kb} KB)  {title}")

        if use_ollama:
            print("  Sending to Ollama...")
            spec = _parse_with_ollama(pdf_path)
            if spec:
                save_spec(bid_id, spec, str(pdf_path))
                if spec.get("walk_required"):
                    _trigger_job_walk_alert(bid_id, spec)
                print()
            else:
                print(f"  ⚠ Parse failed — run manually:\n    python parser.py --save {bid_id} '<json>'\n")
        else:
            # Print instructions for Claude Code manual parsing
            print(f"  PDF: {pdf_path}")
            print(f"  Read the PDF above and extract the spec JSON, then run:")
            print(f"  python parser.py --save {bid_id} '<json>'\n")

    if not use_ollama:
        print("─" * 60)
        print("JSON schema to extract:")
        print(_EXTRACTION_PROMPT.split("\n\n")[0])
        print()
        print("Tip: In Claude Code, use Read tool on each PDF path shown above.")


def cmd_rfq(bid_id: str):
    """Send an RFQ draft email for a bid that has a saved estimate with material lines."""
    sb = _sb()
    bid_resp  = sb.table("bids").select("*").eq("bid_id", bid_id).limit(1).execute()
    spec_resp = sb.table("bid_specs").select("*").eq("bid_id", bid_id).limit(1).execute()
    est_resp  = sb.table("estimates").select("*").eq("bid_id", bid_id).limit(1).execute()

    bids  = bid_resp.data or []
    specs = spec_resp.data or []
    ests  = est_resp.data or []

    if not bids:
        print(f"  ✗ Bid not found: {bid_id}")
        sys.exit(1)
    if not ests:
        print(f"  ✗ No estimate for {bid_id} — build one in the dashboard first")
        sys.exit(1)

    bid  = bids[0]
    spec = specs[0] if specs else {}
    est  = ests[0]

    from notify import send_rfq_emails
    send_rfq_emails(bid, spec, est)


def _send_no_spec_alert(missing: list[dict]) -> None:
    """Email ADMIN_EMAIL with a list of bids that still have no parsed spec after 48h."""
    import requests
    resend_key  = os.getenv("RESEND_API_KEY")
    admin_email = os.getenv("ADMIN_EMAIL") or os.getenv("NOTIFY_EMAIL")
    if not resend_key or not admin_email or not missing:
        return

    rows = "".join(
        f'<tr>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #E5DDD0">'
        f'<a href="{b.get("url","")}" style="color:#C8922A">{b.get("title","—")}</a></td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #E5DDD0;color:#6A6A70">{b.get("agency","—")}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #E5DDD0;color:#6A6A70">{b.get("source","—")}</td>'
        f'</tr>'
        for b in missing
    )

    html = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;color:#1A1A1C;background:#FAF7F2">
<div style="max-width:640px;margin:0 auto;padding:32px 24px">
<div style="border-left:4px solid #D93025;padding-left:16px;margin-bottom:24px">
  <p style="margin:0;font-size:11px;color:#6A6A70;text-transform:uppercase">FCU Bid Agent · Parser Alert</p>
  <h1 style="margin:6px 0 0;font-size:18px">{len(missing)} bid{"s" if len(missing)!=1 else ""} with no extracted documents</h1>
  <p style="margin:4px 0 0;font-size:13px;color:#6A6A70">Found over 48 hours ago — please check and retrieve manually</p>
</div>
<table style="width:100%;border-collapse:collapse;background:#fff;border:1px solid #E5DDD0;border-radius:8px;overflow:hidden">
  <thead><tr style="background:#E5DDD0">
    <th style="padding:8px 12px;text-align:left;font-size:11px;color:#6A6A70">Title</th>
    <th style="padding:8px 12px;text-align:left;font-size:11px;color:#6A6A70">Agency</th>
    <th style="padding:8px 12px;text-align:left;font-size:11px;color:#6A6A70">Source</th>
  </tr></thead>
  <tbody>{rows}</tbody>
</table>
<p style="margin-top:20px;font-size:12px;color:#6A6A70">
  Options: (1) Open the portal link and download PDFs manually, then run
  <code>python parser.py --save &lt;bid_id&gt; '&lt;json&gt;'</code><br>
  (2) If docs are unavailable, email Joanne/Ben to manually assess GO/NO-GO.
</p>
</div></body></html>"""

    requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
        json={
            "from": "FCU Bid Agent <agent@bids.benlee.ventures>",
            "to": [admin_email],
            "subject": f"[FCU Parser] {len(missing)} bid{'s' if len(missing)!=1 else ''} missing documents — review needed",
            "html": html,
        },
        timeout=10,
    )
    print(f"  → No-spec alert sent to {admin_email} ({len(missing)} bids)")


def cmd_auto():
    """
    Automated daily run (used by launchd via --auto flag).
    1. Download all unprocessed bid PDFs.
    2. Parse them via Ollama.
    3. Alert ADMIN_EMAIL about any bids still missing docs after 48h.
    """
    from datetime import datetime, timezone, timedelta
    print("Parser auto run — download + parse + alert")

    asyncio.run(download_all())
    cmd_parse_all(use_ollama=True)

    # No-spec alert: relevant bids older than 48h still without a spec
    sb = _sb()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    recent = (
        sb.table("bids")
        .select("bid_id, title, agency, source, url")
        .eq("is_relevant", True)
        .lte("first_seen_at", cutoff)
        .execute().data or []
    )
    if recent:
        ids = [b["bid_id"] for b in recent]
        parsed_ids = set()
        for i in range(0, len(ids), 200):
            r = sb.table("bid_specs").select("bid_id").in_("bid_id", ids[i:i+200]).execute()
            parsed_ids.update(row["bid_id"] for row in (r.data or []))
        missing = [b for b in recent if b["bid_id"] not in parsed_ids]
        if missing:
            print(f"  ⚠ {len(missing)} bids still have no spec — sending alert")
            _send_no_spec_alert(missing)
        else:
            print("  ✓ All older bids have parsed specs")


if __name__ == "__main__":
    argv = sys.argv[1:]

    if not argv or "--list" in argv:
        cmd_list()
    elif "--auto" in argv:
        cmd_auto()
    elif "--download" in argv:
        asyncio.run(download_all())
    elif "--pending" in argv:
        cmd_pending()
    elif "--parse-all" in argv:
        cmd_parse_all(use_ollama="--ollama" in argv)
    elif "--save" in argv:
        idx = argv.index("--save")
        cmd_save(argv[idx+1:])
    elif "--rfq" in argv:
        idx = argv.index("--rfq")
        if idx + 1 >= len(argv):
            print("Usage: python parser.py --rfq <bid_id>")
            sys.exit(1)
        cmd_rfq(argv[idx + 1])
    else:
        print(__doc__)
