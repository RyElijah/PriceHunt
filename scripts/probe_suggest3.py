from playwright.sync_api import sync_playwright

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
apis: list[str] = []


def on_resp(r):
    u = r.url
    if "carousell.ph/ds/" in u and r.status == 200:
        if any(x in u.lower() for x in ("keyword", "suggest", "type", "query")):
            apis.append(u)


with sync_playwright() as p:
    b = p.chromium.launch(
        headless=True, args=["--disable-blink-features=AutomationControlled"]
    )
    c = b.new_context(user_agent=UA)
    c.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    pg = c.new_page()
    pg.on("response", on_resp)
    pg.goto("https://www.carousell.ph/", timeout=60000)
    pg.wait_for_timeout(2000)

    for i in range(pg.locator("input").count()):
        ph = pg.locator("input").nth(i).get_attribute("placeholder") or ""
        print("inp", i, repr(ph))

    for label in ["Search for items", "Search", "search"]:
        loc = pg.get_by_placeholder(label, exact=False)
        if loc.count():
            print("found placeholder", label)
            loc.first.click()
            loc.first.fill("iphone 14")
            pg.wait_for_timeout(3500)
            for sel in ["[role='option']", "[role='listbox'] li", "a[href*='search']"]:
                n = pg.locator(sel).count()
                if n:
                    print(sel, n)
                    for j in range(min(8, n)):
                        print(" ", pg.locator(sel).nth(j).inner_text()[:100])
            break

    b.close()

for u in apis:
    print("API", u[:160])
