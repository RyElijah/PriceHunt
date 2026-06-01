from playwright.sync_api import sync_playwright

captured: list[str] = []

def on_response(response):
    url = response.url
    if any(x in url for x in ("api", "search", "listing", "catalog", "bff")):
        if "carousell" in url or "karousell" in url:
            captured.append(f"{response.status} {url[:120]}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.on("response", on_response)
    page.goto(
        "https://www.carousell.ph/search/?query=iphone+14&sort_by=2",
        wait_until="domcontentloaded",
        timeout=60000,
    )
    page.wait_for_timeout(8000)
    # try common selectors
    for sel in ["a[href*='/p/']", "[data-testid*='listing']", "article"]:
        try:
            page.wait_for_selector(sel, timeout=8000)
            print("FOUND selector", sel, page.locator(sel).count())
        except Exception as e:
            print("NO selector", sel)
    html = page.content()
    print("html len", len(html), "/p/" in html)
    browser.close()

for line in captured[:25]:
    print(line)
