"""Print full AJAX response to find download URL or restriction reason."""
import asyncio, os, json
from dotenv import load_dotenv; load_dotenv()
from playwright.async_api import async_playwright

USER = os.getenv("CALEPROCURE_USER", "")
PASS = os.getenv("CALEPROCURE_PASSWORD", "")
BIDDER_ID = "0000026084"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA)
        page = await ctx.new_page()

        await page.goto("https://caleprocure.ca.gov/pages/BS3/login.aspx",
                        wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        await page.fill('#userid', USER); await page.fill('#pwd', PASS)
        await page.click('input[name="Submit"], button:has-text("Login")')
        await page.wait_for_load_state("networkidle", timeout=20000)
        await page.wait_for_timeout(2000)
        print(f"Logged in: {await page.title()}")

        # Navigate to 08A3992 WITH AUC_VERSION=3 (from user's screenshot)
        nav_url = (
            "https://caleprocure.ca.gov/pages/Events-BS3/event-details.aspx"
            f"?Page=AUC_RESP_INQ_DTL&Action=U&AUC_ID=08A3992&AUC_ROUND=1"
            f"&AUC_VERSION=3"
            f"&BIDDER_ID={BIDDER_ID}&BIDDER_LOC=MAIN&BIDDER_SETID=STATE"
            f"&BIDDER_TYPE=V&BUSINESS_UNIT=2660"
        )
        await page.goto(nav_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(5000)
        print(f"Event details: {await page.title()} | {page.url[:80]}")

        await page.click('button:has-text("View Event Package"), a:has-text("View Event Package")')
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
        for _ in range(5):
            rows = await page.evaluate("""() => [...document.querySelectorAll('tbody tr')].map(tr =>
                [...tr.querySelectorAll('td')].map(td => td.innerText.trim()))""")
            if any(r and r[0] and r[0].endswith('.pdf') for r in rows):
                break
            await page.wait_for_timeout(2000)
        print(f"PDF rows: {[r[0] for r in rows if r and r[0].endswith('.pdf')]}")

        # Capture full response
        full_bodies = {}
        async def on_resp(r):
            if 'google' not in r.url:
                try:
                    full_bodies[r.url] = await r.text()
                except Exception:
                    pass
        page.on("response", on_resp)

        print("\nClicking download icon...")
        await page.evaluate("""() => {
            const btns = [];
            document.querySelectorAll('tbody tr').forEach(tr => {
                const cells = tr.querySelectorAll('td');
                if (!cells.length || !cells[0].innerText.trim().endsWith('.pdf')) return;
                const btn = cells[cells.length-1].querySelector('button,a,input[type="image"]');
                if (btn) btns.push(btn);
            });
            if (btns[0]) btns[0].click();
        }""")
        await page.wait_for_timeout(8000)

        for url, body in full_bodies.items():
            print(f"\n=== {url[:80]} (len={len(body)}) ===")
            # Try to pretty-print JSON
            try:
                data = json.loads(body)
                # Print key sections
                capture = data.get('CaptureResults', {})
                print(f"CaptureResults keys: {list(capture.keys())}")
                for key, val in capture.items():
                    if isinstance(val, list) and val:
                        print(f"  {key}: {json.dumps(val[0])[:200]}")
                # Look for any URL-like strings
                body_lower = body.lower()
                for kw in ['viewredirect', 'pdffile', 'fileurl', 'attachment', 'token', 'url', 'href', 'link']:
                    idx = body_lower.find(kw)
                    if idx >= 0:
                        snippet = body[max(0,idx-20):idx+80]
                        print(f"  [{kw}] -> {repr(snippet)}")
            except json.JSONDecodeError:
                print(f"Not JSON. First 500: {body[:500]}")

asyncio.run(main())
