"""
Debug: what does PlanetBids /papi/bids actually return for one portal?

    python debug_papi.py 23758

Opens Chrome. Solve the CAPTCHA, wait for the bid list, press Enter ONCE.
No auto-clicking (that was hanging). It just dumps:
  - every /papi/... request URL + key headers
  - each /papi/bids response: row count, meta/links pagination, stage breakdown
  - then probes pages 2/3 and an awarded filter by replaying the call in-page
Writes papi_dump_<cid>.json and exits.
"""
import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent.parent / "bid-scanner"))
try:
    from dotenv import load_dotenv
    load_dotenv(HERE.parent.parent / "bid-scanner" / ".env")
except ImportError:
    pass

from playwright.async_api import async_playwright

BASE = "https://vendors.planetbids.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def summarize(tag, url, j):
    data = j.get("data", []) if isinstance(j, dict) else []
    print(f"\n{tag} {url}")
    print(f"    rows: {len(data)}")
    if isinstance(j, dict):
        for mk in ("meta", "links"):
            if mk in j:
                print(f"    {mk}: {json.dumps(j[mk])[:500]}")
    stages = {}
    for rec in data:
        s = rec.get("attributes", {}).get("stageStr") or "?"
        stages[s] = stages.get(s, 0) + 1
    print(f"    stageStr: {stages}")
    for rec in data[:50]:
        at = rec.get("attributes", {})
        print(f"      - [{at.get('stageStr')}] {at.get('title','')[:72]}")


async def main(cid: str):
    requests_seen = []
    responses = []

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(channel="chrome", headless=False)
        except Exception:
            browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()

        async def on_request(req):
            if "/papi/" in req.url:
                requests_seen.append({"url": req.url, "method": req.method,
                                      "headers": dict(req.headers)})

        async def on_response(resp):
            if "/papi/bids" in resp.url:
                try:
                    responses.append({"url": resp.url, "json": await resp.json()})
                except Exception:
                    pass

        page.on("request", on_request)
        page.on("response", on_response)

        await page.goto(f"{BASE}/portal/{cid}/bo/bo-search",
                        wait_until="domcontentloaded", timeout=30000)
        print("\n-> Solve CAPTCHA, wait for the bid list, press Enter ONCE.")
        await asyncio.get_event_loop().run_in_executor(None, input, "")
        print("   working...")

        # The base call the page already made — grab its URL as a template.
        base_url = responses[-1]["url"] if responses else \
            f"{BASE}/papi/bids?cid={cid}"

        # Replay the call in-page (inherits cookies + headers the app set) with
        # tweaked params, to learn the pagination + filter scheme.
        probes = {
            "page2":      _with_params(base_url, {"page[number]": "2"}),
            "page1_big":  _with_params(base_url, {"page[size]": "200"}),
            "awarded":    _with_params(base_url, {"filter[stage]": "awarded"}),
            "all_stages": _with_params(base_url, {"filter[stage]": "all"}),
        }
        probe_results = {}
        for name, u in probes.items():
            try:
                txt = await asyncio.wait_for(page.evaluate(
                    """async (u) => { const r = await fetch(u, {headers: {accept:'application/json'}});
                        return JSON.stringify({status:r.status, body: await r.text()}); }""",
                    u), timeout=20)
                obj = json.loads(txt)
                body = obj.get("body", "")
                try:
                    probe_results[name] = {"url": u, "status": obj["status"],
                                           "json": json.loads(body)}
                except Exception:
                    probe_results[name] = {"url": u, "status": obj["status"],
                                           "body_head": body[:300]}
            except Exception as e:
                probe_results[name] = {"url": u, "error": str(e)}

        try:
            await asyncio.wait_for(browser.close(), timeout=10)
        except Exception:
            pass

    print("\n===== /papi/ REQUESTS =====")
    for r in requests_seen:
        print(f"\n{r['method']} {r['url']}")
        for k in ("em-version", "company-id", "visit-id", "authorization",
                  "x-api-version", "x-em-version", "accept"):
            if k in r["headers"]:
                print(f"    {k}: {r['headers'][k]}")

    print("\n===== /papi/bids RESPONSES (page's own calls) =====")
    for pl in responses:
        summarize("[page]", pl["url"], pl["json"])

    print("\n===== PROBES =====")
    for name, res in probe_results.items():
        if "json" in res:
            summarize(f"[{name} status={res['status']}]", res["url"], res["json"])
        else:
            print(f"\n[{name}] {res}")

    out = HERE / f"papi_dump_{cid}.json"
    out.write_text(json.dumps({"requests": requests_seen, "responses": responses,
                               "probes": probe_results}, indent=2, default=str))
    print(f"\nwrote {out}")


def _with_params(url: str, extra: dict) -> str:
    from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
    u = urlparse(url)
    q = dict(parse_qsl(u.query))
    q.update(extra)
    return urlunparse(u._replace(query=urlencode(q)))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "23758"))
