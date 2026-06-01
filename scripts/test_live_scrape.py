"""One-off probe for live Carousell HTML structure."""
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import re

url = "https://www.carousell.ph/iphone-14/q/?sort_by=2"
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(4000)
    html = page.content()
    browser.close()

print("len", len(html))
print("p links", len(re.findall(r"/p/", html)))
print("peso", html.count("₱"), "PHP", html.lower().count("php"))

soup = BeautifulSoup(html, "html.parser")
for a in soup.find_all("a", href=True):
    if "/p/" not in a["href"]:
        continue
    text = a.get_text(" ", strip=True)
    if len(text) > 10:
        print("HREF", a["href"][:70])
        print("TEXT", text[:100])
        break

# look for json blobs
for pat in ["listing", "price", "searchResults"]:
    print(pat, html.lower().count(pat.lower()))
