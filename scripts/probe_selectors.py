import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

from tools.live_search import USER_AGENT, _scroll_results

url = "https://www.carousell.ph/search/iphone+14/?search=iphone+14&sort_by=2"

with sync_playwright() as p:
    b = p.chromium.launch(
        headless=True, args=["--disable-blink-features=AutomationControlled"]
    )
    c = b.new_context(user_agent=USER_AGENT, locale="en-PH")
    c.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    pg = c.new_page()
    pg.goto(url, timeout=60000)
    pg.wait_for_timeout(8000)
    _scroll_results(pg)
    for sel in [
        "[data-testid='listing-card']",
        "[data-testid*='listing-card']",
        "[data-testid*='listing']",
    ]:
        print(sel, pg.locator(sel).count())
    b.close()
