"""
Capture full POST request body + cookies when clicking download icon.
"""
import asyncio, json, os, re
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

AUC_ID    = "08A3992"
BIDDER_ID = os.getenv("CALEPROCURE_BIDDER_ID", "0000026084")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA)
        page = await ctx.new_page()

        # login
        await page.goto("https://caleprocure.ca.gov/pages/BS3/login.aspx", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        await page.fill('#userid', os.getenv("CALEPROCURE_USER"))
        await page.fill('#pwd',    os.getenv("CALEPROCURE_PASSWORD"))
        await page.click('input[name="Submit"], button:has-text("Login")')
        await page.wait_for_load_state("networkidle", timeout=20000)
        await page.wait_for_timeout(2000)
        print("✓ Logged in" if not await page.query_selector('#userid') else "⚠ Login failed")

        # Print cookies
        cookies = await ctx.cookies()
        ps_cookies = [c for c in cookies if any(k in c['name'].upper() for k in ['PS', 'SESSION', 'TOKEN'])]
        print(f"\nPS cookies after login ({len(ps_cookies)}):")
        for c in ps_cookies:
            print(f"  {c['name']} = {c['value'][:40]}... (domain: {c['domain']})")

        # navigate to event
        nav_url = (
            "https://caleprocure.ca.gov/pages/Events-BS3/event-details.aspx"
            f"?Page=AUC_RESP_INQ_DTL&Action=U&AUC_ID={AUC_ID}&AUC_ROUND=1"
            f"&BIDDER_ID={BIDDER_ID}&BIDDER_LOC=MAIN&BIDDER_SETID=STATE"
            "&BIDDER_TYPE=V&BUSINESS_UNIT=2660"
        )
        await page.goto(nav_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(5000)

        # subscribe
        if await page.query_selector('button:has-text("Subscribe"), a:has-text("Subscribe")'):
            await page.click('button:has-text("Subscribe"), a:has-text("Subscribe")')
            await page.wait_for_timeout(3000)
            print("✓ Subscribed")

        # open event package
        await page.click('button:has-text("View Event Package"), a:has-text("View Event Package")')
        await page.wait_for_load_state("domcontentloaded", timeout=15000)
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
        print(f"Rows: {rows}")

        # Capture request + response
        req_body = {}
        resp_body = {}

        async def on_request(req):
            if "AUC_MANAGE_BIDS" in req.url:
                try:
                    body = req.post_data or ""
                    req_body['data'] = body
                    req_body['url'] = req.url
                    req_body['headers'] = dict(req.headers)
                except Exception as e:
                    req_body['error'] = str(e)

        async def on_response(resp):
            if "AUC_MANAGE_BIDS" in resp.url and resp.status == 200:
                try:
                    b = await resp.body()
                    resp_body['data'] = b.decode('utf-8', errors='replace')
                except Exception as e:
                    resp_body['error'] = str(e)

        page.on("request", on_request)
        page.on("response", on_response)

        # click download icon
        await page.evaluate("""() => {
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
            if (btns[0]) btns[0].click();
        }""")
        await page.wait_for_timeout(5000)

        print(f"\n{'='*60}")
        print("POST Request:")
        print(f"  URL: {req_body.get('url', 'N/A')}")
        post_data = req_body.get('data', '')
        print(f"  Body length: {len(post_data)}")

        # Parse URL-encoded body
        if post_data:
            params = {}
            for part in post_data.split('&'):
                if '=' in part:
                    k, _, v = part.partition('=')
                    from urllib.parse import unquote_plus
                    params[unquote_plus(k)] = unquote_plus(v)
            important_keys = ['ICAction', 'ICStateNum', 'ICSID', 'ICType', 'ICElementNum',
                              'ICXPos', 'ICYPos', 'ICFocus', 'ICChanged', 'ICResubmit',
                              'AUC_ID', 'BIDDER_ID', 'ICModalWidget']
            print("\nKey PS parameters:")
            for k in important_keys:
                if k in params:
                    print(f"  {k} = {params[k]}")
            print("\nAll parameters:")
            for k, v in sorted(params.items()):
                print(f"  {k} = {v[:80]}")

        # Save full request body
        Path('/tmp/request_body.txt').write_text(post_data)
        print(f"\n(Full POST body saved to /tmp/request_body.txt)")

        # Print attachmentWrapper from response
        if 'data' in resp_body:
            idx = resp_body['data'].find('attachmentWrapper')
            if idx >= 0:
                print(f"\nattachmentWrapper in response:\n{resp_body['data'][max(0,idx-20):idx+300]}")

        await browser.close()

asyncio.run(main())
