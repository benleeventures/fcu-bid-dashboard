"""
Debug: capture full AJAX response when clicking a download icon on
CaleProcure event 08A3992. Print the full data-if-source attr and
look for viewredirect / URL patterns in the response.
"""
import asyncio, json, os, re
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

AUC_ID   = "08A3992"
BIDDER_ID = os.getenv("CALEPROCURE_BIDDER_ID", "0000026084")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA)
        page = await ctx.new_page()

        # --- login ---
        print("Logging in...")
        await page.goto("https://caleprocure.ca.gov/pages/BS3/login.aspx", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        await page.fill('#userid', os.getenv("CALEPROCURE_USER"))
        await page.fill('#pwd',    os.getenv("CALEPROCURE_PASSWORD"))
        await page.click('input[name="Submit"], button:has-text("Login")')
        await page.wait_for_load_state("networkidle", timeout=20000)
        await page.wait_for_timeout(2000)
        if await page.query_selector('#userid'):
            print("⚠ Login failed"); await browser.close(); return
        print("✓ Logged in")

        # --- navigate to event ---
        nav_url = (
            "https://caleprocure.ca.gov/pages/Events-BS3/event-details.aspx"
            f"?Page=AUC_RESP_INQ_DTL&Action=U&AUC_ID={AUC_ID}&AUC_ROUND=1"
            f"&BIDDER_ID={BIDDER_ID}&BIDDER_LOC=MAIN&BIDDER_SETID=STATE"
            "&BIDDER_TYPE=V&BUSINESS_UNIT=2660"
        )
        await page.goto(nav_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(5000)
        title = await page.title()
        print(f"  Event page title: {title}")

        # --- subscribe ---
        sub_btn = await page.query_selector('button:has-text("Subscribe"), a:has-text("Subscribe")')
        if sub_btn:
            print("  Clicking Subscribe...")
            await page.click('button:has-text("Subscribe"), a:has-text("Subscribe")')
            await page.wait_for_timeout(3000)
            print("  ✓ Subscribed")
        else:
            print("  (no Subscribe button)")

        # --- open event package ---
        pkg_sel = 'button:has-text("View Event Package"), a:has-text("View Event Package")'
        if not await page.query_selector(pkg_sel):
            print("⚠ View Event Package not found"); await browser.close(); return
        await page.click(pkg_sel)
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
        # poll for table
        for _ in range(10):
            rows = await page.evaluate("""() => {
                const r = [];
                document.querySelectorAll('tbody tr').forEach(tr => {
                    const cells = tr.querySelectorAll('td');
                    if (cells.length < 2) return;
                    const fn = cells[0].innerText.trim();
                    if (fn && fn.match(/\\.[a-z]{2,5}$/i)) r.push(fn);
                });
                return r;
            }""")
            if rows: break
            await page.wait_for_timeout(1000)
        print(f"  Attachment rows: {rows}")
        if not rows:
            print("⚠ No rows"); await browser.close(); return

        # --- click first download icon, intercept AJAX ---
        ajax_bodies = []
        async def capture_response(resp):
            if "AUC_MANAGE_BIDS" in resp.url and resp.status == 200:
                try:
                    b = await resp.body()
                    ajax_bodies.append(b.decode("utf-8", errors="replace"))
                except Exception:
                    pass
        page.on("response", capture_response)

        print(f"\n  Clicking download icon for: {rows[0]}")
        clicked = await page.evaluate("""() => {
            const btns = [];
            document.querySelectorAll('tbody tr').forEach(tr => {
                const cells = tr.querySelectorAll('td');
                if (cells.length < 2) return;
                const fn = cells[0].innerText.trim();
                if (!fn || !fn.match(/\\.[a-z]{2,5}$/i)) return;
                const lastCell = cells[cells.length - 1];
                const btn = lastCell.querySelector('button, a, input[type="image"]');
                if (btn) btns.push(btn);
            });
            if (btns[0]) { btns[0].click(); return true; }
            return false;
        }""")
        print(f"  Button clicked: {clicked}")

        # wait for AJAX
        await page.wait_for_timeout(5000)

        # --- inspect #downloadButton full HTML ---
        dl_html = await page.evaluate("() => document.getElementById('downloadButton')?.outerHTML || '(not in DOM)'")
        print(f"\n#downloadButton full HTML:\n{dl_html}\n")

        # --- look for viewredirect in page source ---
        content = await page.content()
        urls = re.findall(r'viewredirect[^"\'<>\s]{0,200}', content)
        print(f"viewredirect URLs in page: {urls[:5]}")

        # --- inspect data-if state in JS ---
        ps_state = await page.evaluate("""() => {
            try {
                // CaleProcure's data-if framework stores state in a global
                if (window.psPageState) return JSON.stringify(window.psPageState).slice(0, 2000);
                if (window.ptAJAX) return 'ptAJAX exists';
                // Search for attachment wrapper data
                const keys = Object.keys(window).filter(k => k.toLowerCase().includes('attach') || k.toLowerCase().includes('wrapper'));
                return 'window keys: ' + JSON.stringify(keys.slice(0, 20));
            } catch(e) { return 'error: ' + e; }
        }""")
        print(f"\nPS state probe: {ps_state}\n")

        # --- AJAX responses ---
        print(f"\n{'='*60}")
        print(f"AJAX responses captured: {len(ajax_bodies)}")
        for i, body in enumerate(ajax_bodies):
            print(f"\n--- AJAX response {i+1} ({len(body)} chars) ---")
            # Search for viewredirect or URL-like patterns
            vr_matches = re.findall(r'(?:viewredirect|/nlx3/psc|docdownload|attachment)[^"\'\\<>]{0,300}', body)
            if vr_matches:
                print("URL patterns found:")
                for m in vr_matches[:10]:
                    print(f"  {m}")
            # Print attachmentWrapper context
            idx = body.find('attachmentWrapper')
            if idx >= 0:
                print(f"\nattachmentWrapper context (±300):\n{body[max(0,idx-50):idx+400]}")
            # Print full body to file
            Path(f"/tmp/ajax_response_{i}.json").write_text(body)
            print(f"(Full response saved to /tmp/ajax_response_{i}.json)")

        await browser.close()

asyncio.run(main())
