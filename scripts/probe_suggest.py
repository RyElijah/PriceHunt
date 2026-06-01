import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

captured: list[tuple[str, str]] = []

def on_response(response):
    url = response.url
    if "carousell" in url and any(k in url.lower() for k in ("keyword", "suggest", "search", "typeahead")):
        try:
            body = response.text()[:500] if response.status == 200 else ""
        except Exception:
            body = ""
        captured.append((str(response.status), url[:150], body[:200]))


with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    ctx = browser.new_context(user_agent=UA, locale="en-PH")
    ctx.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    page = ctx.new_page()
    page.on("response", on_response)
    page.goto("https://www.carousell.ph/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)

    # type in search box if exists
    for sel in [
        "input[type='search']",
        "input[placeholder*='Search']",
        "input[name='search']",
        "[data-testid*='search'] input",
    ]:
        loc = page.locator(sel).first
        if loc.count() > 0:
            loc.fill("iphone 1")
            page.wait_for_timeout(2500)
            loc.fill("iphone 14")
            page.wait_for_timeout(2500)
            break

    browser.close()

for item in captured:
    print("---")
    print(item)
