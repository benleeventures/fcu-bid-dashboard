# PlanetBids Scraper — Debug Log

## The Goal
Scrape open bids from ~34 PlanetBids portals (Beverly Hills, Burbank, Glendale, etc.)
and filter by flooring keywords. Results go to Supabase + email digest.

## What We Know
- PlanetBids is a JS SPA (Ember.js) behind AWS WAF
- Bids are loaded via a JSON API: `https://api-external.prod.planetbids.com/papi/bids?cid=<portal_id>&per_page=30`
- The API uses OAuth Bearer token auth (separate domain from the portal UI)
- WAF CAPTCHA must be solved once per session on `vendors.planetbids.com`
- After solving CAPTCHA manually in Chrome, opening NEW TABS works fine (bids load)
- API response format: `{ data: [ { id, attributes: { title, stageStr, bidDueDate, issueDate, invitationNum } } ], meta: {} }`
- `per_page` can be set to 500 to get all bids in one call

## What We Tried

### 1. Headless Chromium + saved cookies
- Saved WAF cookies after solving CAPTCHA, loaded them in headless browser
- **Result:** WAF detects headless fingerprint, blocks API calls

### 2. Live browser session — navigate to each portal
- Open real Chrome, solve CAPTCHA once, navigate to each portal URL
- **Result:** Each navigation triggers a new WAF challenge, bids don't load

### 3. New tab per portal
- After CAPTCHA, open new tab for each portal (same session)
- User confirmed manually opening tabs works — bids load without new CAPTCHA
- **Result:** Playwright's new tab doesn't reuse session the same way; bids still blank

### 4. `route.fetch()` to modify per_page
- Intercept the bids API call, call it ourselves with per_page=500
- **Result:** `route.fetch()` runs from Playwright process (not browser), lacks auth token → 400/406

### 5. `page.on("response")` + `page.expect_response()`
- Listen for the browser's own API responses
- **Result:** Timing issues — response fires before listener is set up, or after we move on

### 6. Capture OAuth token from `/papi/oauth/refresh/` response
- Intercept the OAuth endpoint, extract token from response body
- **Result:** Response body has `{ error, meta }` — OAuth fails when called from Playwright process

### 7. Capture Bearer token from outgoing request headers
- Listen on `page.route("**/api-external**")` for Authorization header
- **Result:** Route handler never fires — requests to api-external not intercepted (possibly cross-origin limitation or timing)

### 8. `page.on("request")` to log all requests
- Log every request to find auth headers and api-external calls
- **Result:** Not yet confirmed — stopped here

## What Still Could Work

### Option A — Extract token from page JS memory
PlanetBids uses Ember.js. The auth token is stored in an Ember service in memory.
Try extracting it via `page.evaluate`:
```python
token = await page.evaluate("""() => {
    // Try Ember container
    try {
        const app = window.Ember?.Application?.INSTANCES?.[0];
        const session = app?.lookup('service:session');
        return session?.data?.authenticated?.access_token;
    } catch(e) { return null; }
}""")
```
Also try `window.localStorage`, `window.sessionStorage`.

### Option B — Monkey-patch fetch in the page
Inject JS before page load to intercept fetch calls and extract the token:
```python
await page.add_init_script("""
    const origFetch = window.fetch;
    window.fetch = async (url, opts) => {
        if (url.includes('api-external')) {
            window._pb_token = (opts?.headers?.Authorization || '').replace('Bearer ', '');
        }
        return origFetch(url, opts);
    };
""")
# After page loads: token = await page.evaluate("() => window._pb_token")
```

### Option C — Parse DOM with scroll (accept 30-bid limit)
- The page loads 30 bids in the DOM at a time (virtual scroll)
- Stay on each portal page, parse the visible 30 rows, filter by keyword
- 30 bids is enough for most portals (most have <30 open at once anyway)
- Much simpler, no API auth needed

### Option D — CDP (Chrome DevTools Protocol)
Use Playwright's CDP session to intercept requests at a lower level:
```python
client = await page.context.new_cdp_session(page)
await client.send("Network.enable")
# Listen for Network.requestWillBeSent events which include headers
```

### Option E — Selenium + real Chrome profile
Use Selenium with an existing Chrome profile (not a fresh context).
The existing profile has persistent WAF tokens and session state.
More complex setup but most reliable for WAF bypass.

## Current State of Code
- `main.py --source planetbids` → opens Chrome, waits for CAPTCHA + Enter
- Attempts to capture OAuth token from OAuth endpoint (doesn't work yet)
- Falls back to API calls without token (returns 400)
- First portal (Beverly Hills 39493) sometimes works via response interception

## Recommended Next Step
Try **Option B (monkey-patch fetch)** first — it's clean, non-destructive, and captures
the exact token the browser uses before any request is made.
Then **Option C (DOM parsing, 30 bids)** as a reliable fallback if B fails.
