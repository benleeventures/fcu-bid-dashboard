"""Quick local test for the Crisp Plan Room scraper."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from scanner import _search_crisp

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            bids = await _search_crisp(page)
        finally:
            await browser.close()

    print(f"\n{'='*60}")
    print(f"Total bids: {len(bids)}")
    print(f"Flooring relevant: {sum(1 for b in bids if b['is_relevant'])}")
    print()
    for b in bids:
        rel = "★" if b["is_relevant"] else " "
        print(f"{rel} [{b['bid_id']}]")
        print(f"    Title:   {b['title']}")
        print(f"    Agency:  {b['agency']}")
        print(f"    Due:     {b['due_date_raw']} → {b['due_date']}")
        print(f"    URL:     {b['url']}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
