import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

from tools.live_search import USER_AGENT, _block_heavy_assets

url = "https://www.carousell.ph/p/iphone-14-128gb-rush-1441294079/"

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    c = b.new_context(user_agent=USER_AGENT)
    c.route("**/*", _block_heavy_assets)
    pg = c.new_page()
    pg.goto(url, timeout=30000)
    html = pg.content()
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
        html,
        re.DOTALL,
    )
    if m:
        d = json.loads(m.group(1))

        def walk(o: object, depth: int = 0) -> None:
            if depth > 14:
                return
            if isinstance(o, dict):
                for k, v in o.items():
                    kl = k.lower()
                    if any(x in kl for x in ("meetup", "location", "place", "address")):
                        if isinstance(v, (str, int, float)) and v:
                            print(f"{k}: {v!r}")
                        elif isinstance(v, list) and v and len(str(v)) < 300:
                            print(f"{k}: {v!r}")
                    walk(v, depth + 1)
            elif isinstance(o, list):
                for v in o[:30]:
                    walk(v, depth + 1)

        walk(d)
    else:
        print("no next data")
    b.close()
