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
    context = browser.new_context(
        user_agent=UA,
        viewport={"width": 1280, "height": 900},
        locale="en-PH",
    )
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
    count = page.locator("a[href*='/p/']").count()
    html = page.content()
    print("listings", count, "html", len(html))
    browser.close()

from tools.scraper import _filter_by_budget, _parse_listings_html

items = _filter_by_budget(
    _parse_listings_html(html, source="carousell", base_url="https://www.carousell.ph"),
    30000,
)
print("parsed", len(items))
for x in items[:5]:
    print(x["price"], x["title"][:55])
