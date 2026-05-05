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

    # Fetch bid for scoring
    bid_resp = sb.table("bids").select("is_relevant,due_date").eq("bid_id", bid_id).limit(1).execute()
    bid = (bid_resp.data or [{}])[0]

    from scoring import score_go_no_go
    go = score_go_no_go(bid, spec)

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
        "go_score":        go["score"],
        "go_verdict":      go["verdict"],
    }
    sb.table("bid_specs").upsert(row, on_conflict="bid_id").execute()
    print(f"✓ Saved spec for {bid_id}  [{go['verdict'].upper()} {go['score']}]")


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

    # Skip bids already downloaded or past their due date
    from datetime import date as _date
    today = _date.today()
    pending = []
    already = []
    skipped_due = []
    for b in bids:
        pdf_path = SPECS_DIR / f"{b['bid_id']}.pdf"
        if pdf_path.exists():
            already.append(b)
            continue
        due = b.get("due_date")
        if due:
            try:
                if _date.fromisoformat(str(due)) < today:
                    skipped_due.append(b)
                    continue
            except ValueError:
                pass
        pending.append(b)

    print(f"Unprocessed relevant bids: {len(bids)}")
    if already:
        print(f"  {len(already)} already downloaded (run --pending to list)")
    if skipped_due:
        print(f"  {len(skipped_due)} skipped — past due date (expirer will archive)")
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

        # Log in to Crisp Plan Room once if any CRISP bids need downloading
        crisp_pending = [b for b in pending if b.get("source") == "Crisp Plan Room"]
        crisp_logged_in = False
        if crisp_pending:
            crisp_login_page = await context.new_page()
            crisp_logged_in = await _crisp_login(crisp_login_page)
            if crisp_logged_in:
                print(f"  ✓ Crisp Plan Room: logged in — {len(crisp_pending)} bids to download")
            else:
                print("  ⚠ Crisp Plan Room: login failed — check CRISP_USER / CRISP_PASSWORD in .env")
            await crisp_login_page.close()

        # Log in to CaleProcure once and keep the page open for all CCOP downloads.
        # CaleProcure stores the auth token in sessionStorage, which is lost when a
        # new tab is opened — reusing the same page preserves the session.
        ccop_pending = [b for b in pending if b.get("source") == "Caltrans CCOP"]
        ccop_page = None
        ccop_logged_in = False
        if ccop_pending:
            ccop_page = await context.new_page()
            ccop_logged_in = await _caleprocure_login(ccop_page)
            if ccop_logged_in:
                print(f"  ✓ CaleProcure: logged in — {len(ccop_pending)} bids to download")
            else:
                print("  ⚠ CaleProcure: login failed — check CALEPROCURE_USER / CALEPROCURE_PASSWORD in .env")
                await ccop_page.close()
                ccop_page = None

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

            # Crisp Plan Room — fetch page images from public web viewer
            if source == "Crisp Plan Room":
                page = await context.new_page()
                try:
                    saved = await _download_crisp_docs(page, context, bid_id, url, logged_in=crisp_logged_in)
                    if not saved:
                        print(f"    ⚠ No documents found\n")
                except Exception as e:
                    print(f"    ⚠ Crisp error: {e}\n")
                finally:
                    await page.close()
                continue

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

            # Caltrans CCOP — reuse the authenticated ccop_page (same tab = same sessionStorage)
            if source == "Caltrans CCOP":
                if not ccop_logged_in or ccop_page is None:
                    print("    ⚠ SKIP — CaleProcure login failed\n")
                    continue
                try:
                    saved = await _download_caleprocure_docs(ccop_page, context, bid_id, url)
                    if not saved:
                        print(f"    ⚠ No documents saved for {bid_id}\n")
                except Exception as e:
                    print(f"    ⚠ CCOP error: {e}\n")
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
                data = await resp.body()
                if not data:
                    print("    ⚠ Empty response\n"); await page.close(); continue

                if data[:2] == b"PK":
                    # ZIP or DOCX — extract best content
                    content, ext = _extract_best_pdf_from_zip(data, bid_id)
                    if content:
                        save_path = SPECS_DIR / f"{bid_id}{ext}"
                        save_path.write_bytes(content)
                        print(f"    ✓ Extracted from ZIP → {save_path.name} ({len(content)//1024} KB)\n")
                    else:
                        print("    ⚠ ZIP contained no usable content\n")
                    await page.close(); continue

                if b"%PDF" not in data[:10]:
                    ct = resp.headers.get("content-type", "unknown")
                    print(f"    ⚠ Not a valid PDF (content-type: {ct})\n"); await page.close(); continue

                out.write_bytes(data)
                print(f"    ✓ Saved {out.name} ({len(data)//1024} KB)\n")

            except Exception as e:
                print(f"    ⚠ Error: {e}\n")
            finally:
                await page.close()

        if ccop_page:
            await ccop_page.close()

        await browser.close()

    print(f"Done. PDFs saved to {SPECS_DIR}/")
    print("Now run: python parser.py --pending  to see what needs parsing")


async def _download_caleprocure_docs(page, context, bid_id: str, url: str) -> bool:
    """
    Download all attachments from a CaleProcure/CCOP event after login.

    Flow: event details (direct AUC_RESP_INQ_DTL URL) → "View Event Package"
          → attachments page → per-file: download icon → "Your file is ready"
          modal → "Download Attachment" popup → capture PDF bytes → save.

    The shortlink (/event/{BU}/{AUC_ID}) redirects to BIDDER_ID=BID0000001 (guest)
    when resolved server-side. Navigate to AUC_RESP_INQ_DTL directly with FCU's
    BIDDER_ID so PeopleSoft loads the authenticated vendor view.
    """
    import re as _re

    PKG_BTN_SEL = (
        'button:has-text("View Event Package"), '
        'a:has-text("View Event Package"), '
        'input[value*="Event Package" i]'
    )
    BIDDER_ID = os.getenv("CALEPROCURE_BIDDER_ID", "0000026084")

    out_dir = SPECS_DIR / bid_id
    out_dir.mkdir(parents=True, exist_ok=True)
    saved_any = False

    # Extract AUC_ID: stored URL is caleprocure.ca.gov/event/2660/08A3992
    m = _re.search(r'/event/\d+/(\w+)', url or "")
    auc_id = m.group(1) if m else bid_id.replace("CCOP-", "")

    # Use the direct AUC_RESP_INQ_DTL URL — prevents the guest-BIDDER_ID redirect
    # that the shortlink causes when no PS session cookie exists.
    nav_url = (
        "https://caleprocure.ca.gov/pages/Events-BS3/event-details.aspx"
        f"?Page=AUC_RESP_INQ_DTL&Action=U&AUC_ID={auc_id}&AUC_ROUND=1"
        f"&BIDDER_ID={BIDDER_ID}&BIDDER_LOC=MAIN&BIDDER_SETID=STATE"
        f"&BIDDER_TYPE=V&BUSINESS_UNIT=2660"
    )

    try:
        # domcontentloaded — avoids networkidle timeout on pages with long-polling
        await page.goto(nav_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(5000)  # give Angular time to fully render

        title = await page.title()
        if "oops" in title.lower() or "error" in title.lower() or "403" in title:
            print(f"    ⚠ Page error (title: '{title}') — BIDDER_ID or session issue\n")
            return False

        # CaleProcure requires vendors to Subscribe to an event before the
        # PeopleSoft backend will serve attachments. Click Subscribe if present.
        try:
            sub_sel = 'button:has-text("Subscribe"), a:has-text("Subscribe")'
            sub_btn = await page.query_selector(sub_sel)
            if sub_btn:
                await page.click(sub_sel)
                await page.wait_for_timeout(3000)
                print(f"    → Subscribed to event {auc_id}")
        except Exception as _sub_err:
            print(f"    ↷ Subscribe step skipped: {_sub_err}")

        pkg_btn = await page.query_selector(PKG_BTN_SEL)
        if not pkg_btn:
            print(f"    ⚠ 'View Event Package' not found (title: '{title}')\n")
            return False

        # Use page.click() (string selector) to avoid stale element reference
        # if the SPA re-renders between query_selector and click
        await page.click(PKG_BTN_SEL)
        await page.wait_for_load_state("domcontentloaded", timeout=15000)

        # Poll up to 10s for Angular to populate the attachments table.
        # Fixed 3s wait was sometimes insufficient.
        JS_GET_ROWS = """() => {
            const results = [];
            document.querySelectorAll('tbody tr').forEach(tr => {
                const cells = tr.querySelectorAll('td');
                if (cells.length < 2) return;
                const filename = cells[0].innerText.trim();
                // Must look like a filename (has an extension)
                if (!filename || !filename.match(/\\.[a-z]{2,5}$/i)) return;
                const lastCell = cells[cells.length - 1];
                const btn = lastCell.querySelector('button, a, input[type="image"]');
                if (btn) results.push(filename);
            });
            return results;
        }"""
        row_info = []
        for _poll in range(10):
            row_info = await page.evaluate(JS_GET_ROWS)
            if row_info:
                break
            await page.wait_for_timeout(1000)

        # Attachments table: "Attached File | Attachment Description | Download"
        # Only collect rows that have an actual filename (skip header/footer rows
        # with empty first cells or non-file content like "Delete" rows).

        if not row_info:
            print("    ⚠ No downloadable attachments found on attachments page\n")
            return False

        print(f"    Found {len(row_info)} attachment(s): {row_info}")

        # Collect row data including any direct href URLs in the last cell.
        # PeopleSoft sometimes exposes viewredirect links directly as <a href>.
        JS_GET_ROW_DATA = """() => {
            const results = [];
            document.querySelectorAll('tbody tr').forEach(tr => {
                const cells = tr.querySelectorAll('td');
                if (cells.length < 2) return;
                const filename = cells[0].innerText.trim();
                if (!filename || !filename.match(/\\.[a-z]{2,5}$/i)) return;
                const lastCell = cells[cells.length - 1];
                const btn = lastCell.querySelector('button, a, input[type="image"]');
                if (!btn) return;
                const href = btn.tagName === 'A' ? (btn.getAttribute('href') || '') : '';
                results.push({ filename, href });
            });
            return results;
        }"""
        row_data = await page.evaluate(JS_GET_ROW_DATA)

        for i, row in enumerate(row_data):
            filename = row["filename"]
            direct_href = row.get("href", "")
            safe_name = _re.sub(r"[^\w\-.]", "_", filename) or f"attachment_{i}.pdf"
            if not safe_name.lower().endswith(".pdf"):
                safe_name += ".pdf"

            try:
                pdf_bytes: list[bytes] = []

                # Fast path: if the button is a plain anchor with a URL, fetch directly
                if direct_href and ("viewredirect" in direct_href or direct_href.startswith("http")):
                    full_url = direct_href if direct_href.startswith("http") else (
                        "https://caleprocure.ca.gov" + direct_href
                    )
                    try:
                        r = await context.request.get(full_url, timeout=30000)
                        body = await r.body()
                        if body and b"%PDF" in body[:10]:
                            pdf_bytes.append(body)
                    except Exception as _e:
                        print(f"    ↷ Direct href fetch failed: {_e}")

                if not pdf_bytes:
                    # Click the nth download button — same filename-filter as above
                    clicked = await page.evaluate(f"""() => {{
                        const btns = [];
                        document.querySelectorAll('tbody tr').forEach(tr => {{
                            const cells = tr.querySelectorAll('td');
                            if (cells.length < 2) return;
                            const filename = cells[0].innerText.trim();
                            if (!filename || !filename.match(/\\.[a-z]{{2,5}}$/i)) return;
                            const lastCell = cells[cells.length - 1];
                            const btn = lastCell.querySelector('button, a, input[type="image"]');
                            if (btn) btns.push(btn);
                        }});
                        if (btns[{i}]) {{ btns[{i}].click(); return true; }}
                        return false;
                    }}""")

                    if not clicked:
                        print(f"    ⚠ Download button {i} not found\n")
                        continue

                    # Wait for #downloadButton (the "Download Attachment" modal button).
                    # PeopleSoft hides this via data-if until the server confirms the
                    # file is ready. Subscribe (above) should unlock it.
                    download_visible = False
                    try:
                        await page.wait_for_selector('#downloadButton', state='visible', timeout=20000)
                        download_visible = True
                    except Exception:
                        print(f"    ⚠ #downloadButton never became visible for '{filename}'")

                    if download_visible:
                        # "Download Attachment" opens a popup with the PDF viewredirect URL.
                        try:
                            async with page.expect_popup(timeout=15000) as popup_info:
                                await page.evaluate("document.getElementById('downloadButton').click()")
                            popup = await popup_info.value

                            captured: list[bytes] = []

                            async def _on_response(resp):
                                ct = resp.headers.get("content-type", "")
                                if resp.status == 200 and (
                                    "pdf" in ct.lower()
                                    or "octet-stream" in ct.lower()
                                    or "viewredirect" in resp.url
                                ):
                                    try:
                                        body = await resp.body()
                                        if body and b"%PDF" in body[:10]:
                                            captured.append(body)
                                    except Exception:
                                        pass

                            popup.on("response", _on_response)
                            await popup.wait_for_load_state("networkidle", timeout=20000)
                            await popup.wait_for_timeout(1000)

                            if not captured:
                                file_url = popup.url
                                try:
                                    r = await context.request.get(file_url, timeout=30000)
                                    body = await r.body()
                                    if body and b"%PDF" in body[:10]:
                                        captured.append(body)
                                except Exception:
                                    pass

                            await popup.close()
                            pdf_bytes.extend(captured)
                        except Exception as _popup_err:
                            print(f"    ⚠ Popup error for '{filename}': {_popup_err}")
                    else:
                        # Modal never appeared — log the page state for diagnosis
                        dl_btn_html = await page.evaluate(
                            "() => document.getElementById('downloadButton')?.outerHTML || '(not in DOM)'"
                        )
                        print(f"    ⚠ #downloadButton state: {dl_btn_html[:200]}")

                # Dismiss modal if still open so the next download button is clickable
                try:
                    await page.click('button:has-text("Close")', timeout=2000)
                    await page.wait_for_timeout(300)
                except Exception:
                    pass

                if not pdf_bytes:
                    print(f"    ⚠ No PDF bytes captured for '{filename}'\n")
                    continue

                data = pdf_bytes[0]
                (out_dir / safe_name).write_bytes(data)
                print(f"    ✓ {safe_name} ({len(data) // 1024} KB)")
                saved_any = True

                # Primary doc → also save as flat {bid_id}.pdf for the parser
                if i == 0:
                    (SPECS_DIR / f"{bid_id}.pdf").write_bytes(data)

            except Exception as e:
                print(f"    ⚠ Error downloading '{filename}': {e}")

    except Exception as e:
        print(f"    ⚠ CaleProcure download error: {e}")

    if saved_any:
        print(f"    ✓ All attachments saved to {out_dir}/\n")
    return saved_any


async def _caleprocure_login(page) -> bool:
    """Log in to CaleProcure (CA eProcure). Page renders via JS — needs networkidle."""
    user     = os.getenv("CALEPROCURE_USER", "")
    password = os.getenv("CALEPROCURE_PASSWORD", "")
    if not user or not password:
        print("  ⚠ CALEPROCURE_USER / CALEPROCURE_PASSWORD not set in .env")
        return False
    try:
        await page.goto("https://caleprocure.ca.gov/pages/BS3/login.aspx",
                        wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)
        await page.fill('#userid', user)
        await page.fill('#pwd', password)
        await page.click('input[name="Submit"], button:has-text("Login")')
        await page.wait_for_load_state("networkidle", timeout=20000)
        await page.wait_for_timeout(2000)
        still_on_login = await page.query_selector('#userid')
        return still_on_login is None
    except Exception as e:
        print(f"  ⚠ CaleProcure login error: {e}")
        return False


async def _crisp_login(page) -> bool:
    """Log in to Crisp Plan Room with username/password."""
    user     = os.getenv("CRISP_USER", "")
    password = os.getenv("CRISP_PASSWORD", "")
    if not user or not password:
        print("  ⚠ CRISP_USER / CRISP_PASSWORD not set in .env")
        return False
    try:
        await page.goto("https://www.crispplanroom.com/login", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1500)

        await page.fill(
            'input[name="username"], input[name="user"], input[id="username"], input[type="text"]',
            user,
        )
        await page.fill('input[name="password"], input[type="password"]', password)
        await page.click('button[type="submit"], input[type="submit"]')
        await page.wait_for_load_state("domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000)

        still_on_login = await page.query_selector('input[type="password"]')
        return still_on_login is None
    except Exception as e:
        print(f"  ⚠ Crisp login error: {e}")
        return False


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

        # If still on login page, login failed — check URL since query_selector
        # can crash if a post-login navigation destroys the execution context
        try:
            still_on_login = await page.query_selector('input[type="password"]')
            return still_on_login is None
        except Exception:
            return "login" not in page.url.lower()
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


def _extract_best_pdf_from_zip(zip_data: bytes, bid_id: str) -> tuple[bytes | None, str]:
    """
    Open a ZIP in memory and return (content_bytes, extension).
    Tries PDFs first, falls back to extracting text from DOCX.
    Returns (None, '') if nothing usable found.
    """
    import io, zipfile, xml.etree.ElementTree as ET

    def _score(name: str) -> int:
        n = name.lower()
        s = 0
        if any(k in n for k in ["sow", "scope", "specification", "rfp", "ifb", "itb", "solicitation"]):
            s += 10
        if any(k in n for k in ["carpet", "floor", "resilient", "09_68", "09_65"]):
            s += 8
        if any(k in n for k in ["amend", "acm", "environmental", "guide"]):
            s -= 5
        return s

    try:
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            names = zf.namelist()

            # 1. Try PDFs first
            pdf_names = [n for n in names if n.lower().endswith(".pdf")]
            if pdf_names:
                best = max(pdf_names, key=_score)
                data = zf.read(best)
                if b"%PDF" in data[:10]:
                    print(f"    ↳ ZIP: picked PDF {best} ({len(data)//1024} KB)")
                    return data, ".pdf"

            # 2. DOCX — extract plain text from word/document.xml
            if "word/document.xml" in names:
                xml_bytes = zf.read("word/document.xml")
                root = ET.fromstring(xml_bytes)
                W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                paragraphs = []
                for para in root.iter(f"{{{W}}}p"):
                    text = "".join(t.text or "" for t in para.iter(f"{{{W}}}t"))
                    if text.strip():
                        paragraphs.append(text)
                text_content = "\n".join(paragraphs)
                if text_content.strip():
                    print(f"    ↳ ZIP: extracted DOCX text ({len(text_content)//1024} KB)")
                    return text_content.encode("utf-8"), ".txt"

            return None, ""
    except Exception as e:
        print(f"    ⚠ ZIP extract error: {e}")
        return None, ""


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


async def _download_crisp_docs(page, context, bid_id: str, bid_url: str, logged_in: bool = False) -> bool:
    """
    Download CRISP plan room docs via the inline web viewer (free, never the paid download).

    Scans all wvopen buttons from the specs/plans tab, scores them for flooring
    relevance, and screenshots up to MAX_FILES × MAX_PAGES images. If Ollama is
    running and there are many files, it asks the LLM to pick the best ones.

    URL pattern: /projects/{id}/details/{slug} → /projects/{id}/specs/{slug}
    Viewer:      /webviewer/{project_id}/{section_id}/{file_id}
    """
    import re as _re

    CRISP_BASE = "https://www.crispplanroom.com"
    MAX_PAGES = 8
    MAX_FILES = 2  # screenshots at most 2 files to keep cost+time low

    proj_match = _re.search(r"/projects/(\d+)/", bid_url)
    if not proj_match:
        print("    ⚠ Cannot parse project ID from URL")
        return False
    proj_id = proj_match.group(1)

    slug = bid_url.split("/details/")[-1].rstrip("/")
    buttons: list[tuple[str, str, str]] = []

    for tab in ("specs", "plans"):
        tab_url = f"{CRISP_BASE}/projects/{proj_id}/{tab}/{slug}"
        await page.goto(tab_url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1500)

        html = await page.content()
        # wvopen buttons: Livewire.dispatch('wvopen', { section: NNN, file: NNN})...>label</button>
        found = _re.findall(
            r"Livewire\.dispatch\('wvopen',\s*\{[^}]*section:\s*(\d+),\s*file:\s*(\d+)[^}]*\}\).*?>(.*?)</button>",
            html, _re.S,
        )
        if found:
            buttons = found
            break

    if not buttons:
        print("    ⚠ No viewer-trigger buttons found in specs or plans tab")
        return False

    # Strip HTML tags from labels
    def _clean(s: str) -> str:
        return _re.sub(r"<[^>]+>", "", s).strip()

    labeled = [(sec, fid, _clean(label)) for sec, fid, label in buttons]

    # Score each file for flooring relevance
    def _score(name: str) -> int:
        n = name.lower()
        # Admin/process docs — not useful for scope estimation
        if any(x in n for x in [
            "rfi", "request for info", "modification procedure", "contract modification",
            "submittal", "transmittal", "substitution request", "meeting minute",
            "progress schedule", "safety plan", "insurance", "bonds", "liquidated",
            "prevailing wage", "payroll", "permit", "warranty form", "punch list",
        ]):
            return -15
        # Division 09 = Finishes — always the flooring spec section
        if _re.search(r"\b09\s*[-–]\s*\d|div\s*0?9\b|09\s*finish|section\s*09", n):
            return 25
        if any(x in n for x in ["floor", "carpet", "lvt", "vct", "vinyl", "tile",
                                  "resilient", "turf", "synthetic", "athletic surface"]):
            return 20
        if any(x in n for x in ["sow", "scope of work", "summary of work", "01 11", "011100",
                                  "summary of the work"]):
            return 15
        if _re.search(r"\b01\s*[-–]\s*\d|div\s*0?1\b", n):
            return 8
        if any(x in n for x in ["spec", "specification", "bid spec", "project manual"]):
            return 6
        if any(x in n for x in ["addend", "gameon", "install guide", "pricelist"]):
            return -5
        return 0

    scored = sorted(
        [((_score(label), sec, fid, label)) for sec, fid, label in labeled],
        key=lambda x: x[0], reverse=True,
    )

    # If Ollama is running and there are many candidates, ask it to pick
    top_files: list[tuple[str, str, str]] = []
    if len(scored) > 5 and os.getenv("OLLAMA_RELEVANCE"):
        top_files = _ollama_pick_crisp_files([(sec, fid, label) for _, sec, fid, label in scored])
    if not top_files:
        top_files = [(sec, fid, label) for _, sec, fid, label in scored[:MAX_FILES]]

    print(f"    {len(labeled)} file(s) found — downloading top {len(top_files)}: "
          + ", ".join(f'"{label[:40]}"' for _, _, label in top_files))

    bid_dir = SPECS_DIR / bid_id
    bid_dir.mkdir(parents=True, exist_ok=True)

    all_images: list[bytes] = []
    page_offset = 0

    for sec_id, file_id, file_label in top_files:
        viewer_url = f"{CRISP_BASE}/webviewer/{proj_id}/{sec_id}/{file_id}"
        viewer_page = await context.new_page()
        page_images: list[bytes] = []

        async def capture_page_image(response, _imgs=page_images):
            if "viewer.onlineplanroom.com" in response.url and "/pageimg" in response.url and ".jpg" in response.url:
                try:
                    body = await response.body()
                    if body:
                        _imgs.append(body)
                except Exception:
                    pass

        viewer_page.on("response", capture_page_image)
        try:
            await viewer_page.goto(viewer_url, wait_until="networkidle", timeout=30000)
            await viewer_page.wait_for_timeout(6000)

            if not page_images:
                print(f"    File: {file_label[:60]}  (section={sec_id} file={file_id})")
                print("    (native PDF — capturing viewer screenshots)")
                for _ in range(MAX_PAGES):
                    container = await viewer_page.query_selector("#preview-container")
                    if not container:
                        break
                    shot = await container.screenshot(type="jpeg", quality=85)
                    if shot:
                        page_images.append(shot)
                    await viewer_page.keyboard.press("ArrowRight")
                    await viewer_page.wait_for_timeout(1200)
        finally:
            viewer_page.remove_listener("response", capture_page_image)
            await viewer_page.close()

        pages_this = page_images[:MAX_PAGES]
        print(f"    File: {file_label[:60]}  → {len(pages_this)} page(s)")
        for i, img_bytes in enumerate(pages_this):
            (bid_dir / f"page{page_offset + i:03d}.jpg").write_bytes(img_bytes)
        all_images.extend(pages_this)
        page_offset += len(pages_this)

    if not all_images:
        print("    ⚠ No page images captured from viewer")
        return False

    print(f"    ✓ Captured {len(all_images)} total page image(s)")

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if api_key and api_key != "your_key_here":
        print("    → Parsing with Claude vision...")
        spec = _parse_with_claude_images(all_images[:MAX_PAGES])
        if spec:
            save_spec(bid_id, spec, str(bid_dir / "page000.jpg"))
            print(f"    ✓ Spec saved\n")
        else:
            print("    ⚠ Claude vision parsing failed — images saved, parse manually\n")
    else:
        print(f"    ✓ Images saved to {bid_dir} — set ANTHROPIC_API_KEY to auto-parse\n")

    return True


def _ollama_pick_crisp_files(
    files: list[tuple[str, str, str]], max_pick: int = 2
) -> list[tuple[str, str, str]]:
    """
    Ask Ollama to select the most flooring-relevant files from a CRISP listing.
    Returns a subset of (section_id, file_id, label) tuples, or [] on failure.
    """
    try:
        import requests as _req
        import json as _json

        names = [label for _, _, label in files]
        numbered = "\n".join(f"{i+1}. {n}" for i, n in enumerate(names))
        prompt = (
            "A commercial flooring contractor needs to review a public works bid. "
            f"Below are documents available in the bid package. "
            f"Pick the {max_pick} most relevant for estimating flooring work "
            "(carpet, vinyl, LVT, VCT, tile, epoxy, hardwood). "
            "Focus on specs, scope of work, and Division 09 Finishes sections. "
            "Reply with only the numbers, comma-separated (e.g. '2,5').\n\n"
            f"{numbered}"
        )
        resp = _req.post(
            "http://localhost:11434/api/generate",
            json={
                "model": os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0, "num_predict": 20},
            },
            timeout=20,
        )
        raw = resp.json().get("response", "").strip()
        import re as _re
        indices = [int(x) - 1 for x in _re.findall(r"\d+", raw) if 0 < int(x) <= len(files)]
        return [files[i] for i in indices[:max_pick]] if indices else []
    except Exception:
        return []


def _parse_with_claude_images(images: list[bytes]) -> dict | None:
    """Send a list of JPEG page images to Claude Haiku vision for spec extraction."""
    try:
        import anthropic
        import base64
    except ImportError:
        print("  ⚠ anthropic not installed — run: pip install anthropic")
        return None

    content = [{
        "type": "text",
        "text": f"{_EXTRACTION_PROMPT}\n\nThis is a scanned document. Extract the spec from the page images below.",
    }]
    for img_bytes in images:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.b64encode(img_bytes).decode(),
            },
        })

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": content}],
        )
        raw = msg.content[0].text.strip()
    except Exception as e:
        print(f"  ⚠ Claude API error: {e}")
        return None

    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end])
        except Exception:
            pass
    if "```" in raw:
        for part in raw.split("```"):
            part = part.strip().lstrip("json").strip()
            try:
                return json.loads(part)
            except Exception:
                continue
    print(f"  ⚠ Claude returned invalid JSON: {raw[:200]}")
    return None


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
    docs = sorted([*SPECS_DIR.glob("*.pdf"), *SPECS_DIR.glob("*.txt")])
    if not docs:
        print("No documents downloaded yet.")
        return
    pending = [p for p in docs if p.stem in bids]
    if not pending:
        print("✓ All downloaded documents have been parsed.")
        return
    print(f"{len(pending)} documents ready to parse:\n")
    for p in pending:
        bid = bids.get(p.stem, {})
        size = p.stat().st_size // 1024
        print(f"  {p.stem}  ({size} KB)  [{p.suffix}]  {bid.get('title','')[:50]}")
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

    # Alerts removed — handled by daily scheduled agents:
    #   digest.py  (7:00am) — compliance flags + parsed specs
    #   jobwalk.py (7:15am) — upcoming job walks (GO only, consolidated)


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


def _parse_with_claude(pdf_path: Path) -> dict | None:
    """
    Fallback for scanned PDFs: convert pages to images and send to Claude Haiku vision.
    Only called when pdfplumber extracts no text and ANTHROPIC_API_KEY is set.
    """
    try:
        import anthropic
        import base64
        from pdf2image import convert_from_path
    except ImportError as e:
        missing = str(e).split("'")[1] if "'" in str(e) else str(e)
        print(f"  ⚠ Missing dependency: {missing}")
        if "pdf2image" in str(e):
            print("     Install with: pip install pdf2image && brew install poppler")
        elif "anthropic" in str(e):
            print("     Install with: pip install anthropic")
        return None

    try:
        images = convert_from_path(str(pdf_path), dpi=150, first_page=1, last_page=8)
    except Exception as e:
        print(f"  ⚠ PDF→image conversion failed: {e}")
        return None

    # Build content blocks: prompt + each page as base64 image
    content = [{"type": "text", "text": f"{_EXTRACTION_PROMPT}\n\nThis is a scanned PDF. Extract the spec from the document images below."}]
    for img in images:
        import io
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.b64encode(buf.getvalue()).decode(),
            },
        })

    try:
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": content}],
        )
        raw = msg.content[0].text.strip()
    except Exception as e:
        print(f"  ⚠ Claude API error: {e}")
        return None

    # Reuse same JSON parser as Ollama path
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(raw[start:end])
        except Exception:
            pass
    if "```" in raw:
        for part in raw.split("```"):
            part = part.strip().lstrip("json").strip()
            try:
                return json.loads(part)
            except Exception:
                continue
    print(f"  ⚠ Claude returned invalid JSON: {raw[:200]}")
    return None


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

    # Extract text — PDF or pre-extracted .txt
    try:
        if str(pdf_path).endswith(".txt"):
            text = pdf_path.read_text(encoding="utf-8").strip()
        else:
            with pdfplumber.open(pdf_path) as pdf:
                pages = pdf.pages[:20]
                text = "\n".join(p.extract_text() or "" for p in pages).strip()
    except Exception as e:
        print(f"  ⚠ Text extraction failed: {e}")
        return None

    if not text:
        print("  ⚠ No text extracted (may be a scanned image)")
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if api_key and api_key != "your_key_here" and not str(pdf_path).endswith(".txt"):
            print("  → Falling back to Claude vision API...")
            return _parse_with_claude(pdf_path)
        return None

    # Truncate to ~12K chars to stay within typical context limits
    text = text[:12000]

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

    payload = json.dumps({
        "model": model,
        "prompt": f"{_EXTRACTION_PROMPT}\n\n---\nBID DOCUMENT TEXT:\n{text}",
        "stream": False,
        "options": {"temperature": 0.1},
    }).encode()

    def _call_ollama(prompt: str) -> str | None:
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
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
                return json.loads(resp.read()).get("response", "").strip()
        except Exception as e:
            print(f"  ⚠ Ollama error: {e}")
            return None

    def _clean_and_parse(raw: str) -> dict | None:
        if not raw:
            return None
        # Strip markdown fences
        if "```" in raw:
            parts = raw.split("```")
            for part in parts:
                part = part.strip().lstrip("json").strip()
                try:
                    return json.loads(part)
                except Exception:
                    continue
        # Find the outermost JSON object
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end])
            except Exception:
                pass
        return None

    first_prompt = f"{_EXTRACTION_PROMPT}\n\n---\nBID DOCUMENT TEXT:\n{text}"
    raw = _call_ollama(first_prompt)
    result = _clean_and_parse(raw)
    if result:
        return result

    # Retry with a stricter prompt showing just the required keys
    print("  ↻ Retrying with strict JSON prompt...")
    retry_prompt = (
        "Return ONLY a valid JSON object with these exact keys. No explanation, no markdown.\n\n"
        '{"flooring_types":[],"total_sqft":null,"rooms":"","prevailing_wage":null,'
        '"bid_bond":null,"bid_bond_pct":null,"walk_required":false,"walk_date_raw":"",'
        '"dvbe_required":null,"dvbe_pct":null,"dbe_goal_pct":null,"summary":""}\n\n'
        f"BID DOCUMENT TEXT:\n{text[:6000]}"
    )
    raw = _call_ollama(retry_prompt)
    result = _clean_and_parse(raw)
    if result:
        return result

    print(f"  ⚠ Ollama failed after retry — raw response: {(raw or '')[:200]}")
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
    docs = sorted([*SPECS_DIR.glob("*.pdf"), *SPECS_DIR.glob("*.txt")])
    pending = [p for p in docs if p.stem in bids]

    if not pending:
        print("✓ All downloaded documents have been parsed (or none yet — run --download).")
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


def cmd_recalculate():
    """Recompute go_score + go_verdict for all existing bid_specs."""
    sb = _sb()
    specs_resp = sb.table("bid_specs").select("bid_id,total_sqft,prevailing_wage,bid_bond,walk_required,raw_extract").execute()
    specs = specs_resp.data or []
    if not specs:
        print("No specs found.")
        return

    bid_ids = [s["bid_id"] for s in specs]
    bids_resp = sb.table("bids").select("bid_id,is_relevant,due_date").in_("bid_id", bid_ids).execute()
    bids_by_id = {b["bid_id"]: b for b in (bids_resp.data or [])}

    from scoring import score_go_no_go
    updated = 0
    for spec in specs:
        bid = bids_by_id.get(spec["bid_id"], {})
        go = score_go_no_go(bid, spec)
        sb.table("bid_specs").update({
            "go_score":   go["score"],
            "go_verdict": go["verdict"],
        }).eq("bid_id", spec["bid_id"]).execute()
        print(f"  {spec['bid_id']}  [{go['verdict'].upper()} {go['score']}]")
        updated += 1

    print(f"\n✓ Recalculated {updated} specs")


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


if __name__ == "__main__":
    argv = sys.argv[1:]

    if not argv or "--list" in argv:
        cmd_list()
    elif "--download" in argv:
        asyncio.run(download_all())
    elif "--pending" in argv:
        cmd_pending()
    elif "--parse-all" in argv:
        cmd_parse_all(use_ollama="--ollama" in argv)
    elif "--save" in argv:
        idx = argv.index("--save")
        cmd_save(argv[idx+1:])
    elif "--recalculate" in argv:
        cmd_recalculate()
    elif "--rfq" in argv:
        idx = argv.index("--rfq")
        if idx + 1 >= len(argv):
            print("Usage: python parser.py --rfq <bid_id>")
            sys.exit(1)
        cmd_rfq(argv[idx + 1])
    else:
        print(__doc__)
