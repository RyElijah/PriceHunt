import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

from tools.live_search import USER_AGENT, _block_heavy_assets

# grab first listing url from search
search = "https://www.carousell.ph/search/iphone+14/?search=iphone+14&sort_by=2"

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    c = b.new_context(user_agent=USER_AGENT, locale="en-PH")
    c.route("**/*", _block_heavy_assets)
    pg = c.new_page()
    pg.goto(search, timeout=60000)
    pg.wait_for_timeout(4000)
    link = pg.locator("a[href*='/p/']").first
    href = link.get_attribute("href") or ""
    if not href.startswith("http"):
        href = "https://www.carousell.ph" + href.split("?")[0]
    print("listing", href[:90])
    pg2 = c.new_page()
    pg2.goto(href.split("?")[0], timeout=60000)
    pg2.wait_for_timeout(4000)
    body = pg2.inner_text("body", timeout=8000)
    for pat in ["Meet-up", "Meetup", "Location", "Quezon", "Manila", "Makati", "Cebu"]:
        if pat.lower() in body.lower():
            idx = body.lower().find(pat.lower())
            print(pat, "->", repr(body[max(0, idx - 20) : idx + 80]))
    tids = sorted(set(re.findall(r'data-testid="([^"]+)"', pg2.content())))
    loc = [t for t in tids if "loc" in t.lower() or "meet" in t.lower() or "place" in t.lower()]
    print("testids", loc[:20])
    b.close()
