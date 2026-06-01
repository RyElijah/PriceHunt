"""Inspect DOM for multi meet-up locations."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

from tools.live_search import USER_AGENT, _block_heavy_assets

url = "https://www.carousell.ph/p/iphone-14-128gb-rush-1441294079/"

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    c = b.new_context(user_agent=USER_AGENT, locale="en-PH")
    c.route("**/*", _block_heavy_assets)
    pg = c.new_page()
    pg.goto(url, timeout=30000)
    pg.wait_for_timeout(2000)

    # all testids with meet/location
    html = pg.content()
    tids = sorted(set(re.findall(r'data-testid="([^"]+)"', html)))
    for t in tids:
        if any(x in t.lower() for x in ("meet", "loc", "place", "address")):
            print("tid", t)

    # try role/list items near meet-up
    for sel in [
        "[data-testid*='meetup']",
        "[data-testid*='meet-up']",
        "[data-testid*='location']",
        "button:has-text('locations')",
    ]:
        loc = pg.locator(sel)
        print(sel, "count", loc.count())
        for i in range(min(loc.count(), 5)):
            print(" ", i, repr(loc.nth(i).inner_text(timeout=1000)[:100]))

    btn = pg.locator("button, a").filter(has_text=re.compile(r"see \d", re.I))
    print("see buttons", btn.count())
    for i in range(min(btn.count(), 3)):
        print(" btn", repr(btn.nth(i).inner_text(timeout=500)))

    if btn.count():
        btn.first.click()
        pg.wait_for_timeout(1000)
        meet = pg.get_by_text("Meet-up", exact=False)
        print("after click body slice:")
        body = pg.inner_text("body", timeout=5000)
        idx = body.lower().find("meet-up")
        print(repr(body[idx : idx + 350].replace("\n", " | ")))

    b.close()
