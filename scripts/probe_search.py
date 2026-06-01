"""Debug Carousell search page extraction."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright

from tools.live_search import USER_AGENT, _build_search_urls, _scroll_results

QUERY = "iphone 14"


def try_url(page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(8000)
    _scroll_results(page)
    title = page.title()
    h1 = page.locator("h1").first.inner_text(timeout=3000) if page.locator("h1").count() else ""
    body = page.inner_text("body", timeout=5000).lower()
    iphone_hits = body.count("iphone")
    cards = page.locator("[data-testid='listing-card'], [data-testid*='listing-card']")
    if cards.count() == 0:
        cards = page.locator("a[href*='/p/']")
    print(f"\nURL: {url[:70]}...")
    print(f"  title={title!r} h1={h1[:60]!r} iphone_in_body={iphone_hits}")
    # sample product links
    links = page.locator("a[href*='/p/']")
    seen = set()
    for i in range(min(links.count(), 40)):
        href = links.nth(i).get_attribute("href") or ""
        text = links.nth(i).inner_text(timeout=500)[:80].replace("\n", " ")
        key = href.split("?")[0]
        if key in seen or "/p/" not in href:
            continue
        seen.add(key)
        if re.search(r"iphone|14", text + href, re.I):
            print(f"  match: {text[:55]} | {href[-50:]}")
        if len(seen) >= 6:
            break
    print(f"  unique /p/ links sampled: {len(seen)}")


def main() -> None:
    urls = _build_search_urls(QUERY) + [
        "https://www.carousell.ph/categories/mobile-phones-461/iphone-14-100061/",
        "https://www.carousell.ph/search/iphone%2014/",
    ]
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
            locale="en-PH",
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()
        for url in urls:
            try:
                try_url(page, url)
            except Exception as exc:
                print(f"  FAIL: {exc}")
        browser.close()


if __name__ == "__main__":
    main()
