"""Quick test: CRISP login + doc listing for CRISP-854."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(__file__))
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

from parser import _crisp_login, _download_crisp_docs
from playwright.async_api import async_playwright

BID_ID  = "CRISP-854"
BID_URL = "https://www.crispplanroom.com/projects/854/details/santa-ana-usd-willard-intermediate-school"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        login_page = await context.new_page()
        print("→ Logging in to Crisp...")
        logged_in = await _crisp_login(login_page)
        await login_page.close()
        print(f"  Login result: {'✓ success' if logged_in else '✗ failed'}")

        if not logged_in:
            await browser.close()
            return

        page = await context.new_page()
        print(f"\n→ Fetching docs for {BID_ID}...")
        ok = await _download_crisp_docs(page, context, BID_ID, BID_URL, logged_in=True)
        await page.close()
        await browser.close()
        print(f"\nResult: {'✓ docs saved' if ok else '✗ no docs'}")

asyncio.run(main())
