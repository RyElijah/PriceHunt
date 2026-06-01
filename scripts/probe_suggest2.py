import json
import sys
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# try REST endpoints
urls = [
    "https://www.carousell.ph/ds/keywords/1.0/top-searches?_path=%2F1.0%2Ftop-searches&count=20&country_code=PH&l=en&offset=0",
    "https://www.carousell.ph/ds/keywords/1.0/suggestions?_path=%2F1.0%2Fsuggestions&query=iphone%2014&country_code=PH&l=en",
    "https://www.carousell.ph/ds/keywords/1.0/typeahead?_path=%2F1.0%2Ftypeahead&query=iphone&country_code=PH&l=en",
    "https://www.carousell.ph/ds/search/1.0/suggestions?query=iphone+14&country_code=PH&l=en",
]
h = {"User-Agent": UA, "Accept": "application/json"}
for u in urls:
    try:
        r = requests.get(u, headers=h, timeout=15)
        print(r.status_code, u.split("/ds/")[1][:60])
        print(r.text[:300])
    except Exception as e:
        print("ERR", e)

print("\n--- DOM ---")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(user_agent=UA)
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    page = ctx.new_page()
    page.goto("https://www.carousell.ph/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2000)
    inp = page.locator("input").filter(has_text="").first
    # all inputs
    for i in range(page.locator("input").count()):
        el = page.locator("input").nth(i)
        ph = el.get_attribute("placeholder") or ""
        typ = el.get_attribute("type") or ""
        if "search" in ph.lower() or typ == "search":
            print("input", i, ph, typ)
            el.click()
            el.fill("ipho")
            page.wait_for_timeout(2000)
            # suggestion items
            for sel in ["[role='option']", "[role='listbox'] *", "ul li", "[class*='suggest']"]:
                c = page.locator(sel).count()
                if c:
                    print(sel, c)
                    for j in range(min(5, c)):
                        print(" ", page.locator(sel).nth(j).inner_text()[:80])
            break
    browser.close()
