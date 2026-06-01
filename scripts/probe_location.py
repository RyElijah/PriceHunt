"""Probe Carousell cards for location fields."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

from tools.live_search import (
    LISTING_CARD_SELECTOR,
    USER_AGENT,
    _block_heavy_assets,
    _scroll_results,
    _wait_for_results,
)

url = "https://www.carousell.ph/search/iphone+14/?search=iphone+14&sort_by=2"

with sync_playwright() as p:
    b = p.chromium.launch(
        headless=True, args=["--disable-blink-features=AutomationControlled"]
    )
    c = b.new_context(user_agent=USER_AGENT, locale="en-PH")
    c.route("**/*", _block_heavy_assets)
    c.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    page = c.new_page()
    page.goto(url, timeout=60000)
    _wait_for_results(page)
    _scroll_results(page)

    cards = page.locator(LISTING_CARD_SELECTOR)
    n = 0
    for i in range(min(cards.count(), 25)):
        card = cards.nth(i)
        if card.locator("[data-testid='listing-card-text-seller-name']").count() == 0:
            continue
        html = card.evaluate("el => el.innerHTML.slice(0, 4000)")
        text = card.inner_text(timeout=2000)
        tids = sorted(set(re.findall(r'data-testid="([^"]+)"', html)))
        loc_tids = [t for t in tids if "loc" in t.lower() or "meet" in t.lower() or "place" in t.lower()]
        print("--- card", i, "---")
        print("location testids:", loc_tids)
        for tid in loc_tids:
            el = card.locator(f"[data-testid='{tid}']")
            if el.count():
                print(f"  {tid}:", el.first.inner_text(timeout=500)[:80])
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        print("text lines:", lines[:12])
        n += 1
        if n >= 5:
            break
    b.close()
