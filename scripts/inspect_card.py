import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    page = context.new_page()
    page.goto(
        "https://www.carousell.ph/search/?query=iphone+14&sort_by=2",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    page.wait_for_timeout(8000)

    links = page.locator("a[href*='/p/']").all()[:3]
    for i, link in enumerate(links):
        href = link.get_attribute("href")
        text = link.inner_text(timeout=2000)
        print(f"--- {i} ---")
        print("href", href)
        print("text", repr(text[:200]))
        # parent text
        parent = link.locator("xpath=ancestor::*[self::div][1]")
        try:
            print("parent", parent.inner_text(timeout=1000)[:200])
        except Exception:
            pass

    browser.close()
