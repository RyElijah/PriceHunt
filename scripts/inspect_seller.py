import re
from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
url = "https://www.carousell.ph/search/?query=iphone+14&sort_by=2"

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(user_agent=UA)
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    page = ctx.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(7000)

    cards = page.locator("[data-testid*='listing']")
    seen = set()
    for i in range(min(cards.count(), 30)):
        card = cards.nth(i)
        seller_el = card.locator("[data-testid='listing-card-text-seller-name']")
        if seller_el.count() == 0:
            continue
        seller = seller_el.first.inner_text(timeout=1000).strip()
        if seller in seen:
            continue
        seen.add(seller)
        link = card.locator("a[href*='/p/']").first
        if not link.count():
            continue
        if not re.search(r"iphone", link.inner_text(timeout=1500), re.I):
            continue
        print("seller", seller)
        page2 = ctx.new_page()
        page2.goto(f"https://www.carousell.ph/u/{seller}/", timeout=30000)
        page2.wait_for_timeout(3000)
        t = page2.inner_text("body")
        rev = re.search(r"(\d[\d,]*)\s*reviews?", t, re.I)
        star = re.search(r"(\d(?:\.\d)?)\s*(?:\(|out of|\/)", t)
        print("  reviews", rev.group(1) if rev else "none")
        page2.close()
        if len(seen) >= 4:
            break
    b.close()
