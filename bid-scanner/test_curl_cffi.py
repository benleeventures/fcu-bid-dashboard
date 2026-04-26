"""
Test: curl_cffi Chrome impersonation to bypass Cloudflare on PlanetBids.
Then attempt vendor login and bid search.
"""

import json
from curl_cffi import requests as cf_requests

BASE = "https://vendors.planetbids.com"
PORTAL_ID = "39493"
EMAIL = "floorcoveringunltd@msn.com"
PASSWORD = "LVTFloors9601$"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Use a persistent session so cookies carry across requests
session = cf_requests.Session(impersonate="chrome124")

def test_access():
    """Step 1: Can we reach the portal search page without CAPTCHA?"""
    url = f"{BASE}/portal/{PORTAL_ID}/bo/bo-search"
    print(f"GET {url}")
    r = session.get(url, headers=HEADERS, timeout=20)
    print(f"  Status: {r.status_code}")
    print(f"  Title line: {[l.strip() for l in r.text.split('<title>') if '</title>' in l][:1]}")

    if "Human Verification" in r.text or "cf-challenge" in r.text:
        print("  ⚠ Cloudflare challenge triggered")
        return False
    if r.status_code == 200:
        print("  ✓ No CAPTCHA — Cloudflare passed!")
        # Show first 500 chars of body
        import re
        text = re.sub(r'<[^>]+>', ' ', r.text)
        text = ' '.join(text.split())
        print(f"  Body preview: {text[:500]}")
        return True
    return False


def test_login():
    """Step 2: Try to log in as vendor."""
    # First, get the login page to grab CSRF token if needed
    login_url = f"{BASE}/portal/{PORTAL_ID}/login"
    print(f"\nGET {login_url}")
    r = session.get(login_url, headers=HEADERS, timeout=20)
    print(f"  Status: {r.status_code}")

    if "Human Verification" in r.text:
        print("  ⚠ Cloudflare CAPTCHA on login page too")
        return False

    # Look for CSRF token
    import re
    csrf = ""
    m = re.search(r'name=["\']_token["\'][^>]*value=["\']([^"\']+)["\']', r.text)
    if not m:
        m = re.search(r'value=["\']([^"\']+)["\'][^>]*name=["\']_token["\']', r.text)
    if m:
        csrf = m.group(1)
        print(f"  CSRF token: {csrf[:20]}...")

    # Also check for any hidden fields
    hidden = re.findall(r'<input[^>]*type=["\']hidden["\'][^>]*>', r.text)
    print(f"  Hidden inputs: {len(hidden)}")
    for h in hidden[:5]:
        print(f"    {h[:120]}")

    # Try POST login
    login_data = {
        "email": EMAIL,
        "password": PASSWORD,
        "_token": csrf,
    }
    post_headers = {**HEADERS, "Content-Type": "application/x-www-form-urlencoded", "Referer": login_url}
    print(f"\nPOST {login_url}")
    r2 = session.post(login_url, data=login_data, headers=post_headers, timeout=20, allow_redirects=True)
    print(f"  Status: {r2.status_code}  Final URL: {r2.url}")

    if "logout" in r2.text.lower() or "dashboard" in r2.text.lower():
        print("  ✓ Login successful!")
        return True
    else:
        text = re.sub(r'<[^>]+>', ' ', r2.text)
        text = ' '.join(text.split())
        print(f"  Body preview: {text[:400]}")
        return False


def test_bid_search():
    """Step 3: Try JSON API for bid listing."""
    # PlanetBids often has a JSON endpoint for bid data
    api_candidates = [
        f"{BASE}/portal/{PORTAL_ID}/bo/bo-search?format=json",
        f"{BASE}/api/portal/{PORTAL_ID}/bids",
        f"{BASE}/portal/{PORTAL_ID}/api/bids",
        f"{BASE}/portal/{PORTAL_ID}/bo/bo-search?type=open",
    ]
    for url in api_candidates:
        print(f"\nGET {url}")
        r = session.get(url, headers={**HEADERS, "Accept": "application/json, text/javascript, */*"}, timeout=15)
        print(f"  Status: {r.status_code}  Content-Type: {r.headers.get('content-type','')}")
        if r.status_code == 200 and "json" in r.headers.get("content-type", "").lower():
            print(f"  ✓ JSON response: {r.text[:300]}")
            break


if __name__ == "__main__":
    passed = test_access()
    if passed or True:  # try login regardless
        test_login()
    test_bid_search()
