"""Dump seller profile page text/JSON for rating patterns."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
SELLERS = ["marie_moon", "juffel", "raine17"]


def extract_next_data(html: str) -> dict | None:
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def find_feedback_keys(obj, path="$", hits=None, depth=0):
    if hits is None:
        hits = []
    if depth > 12:
        return hits
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = k.lower()
            if any(x in kl for x in ("feedback", "review", "rating", "score", "star")):
                if isinstance(v, (int, float, str)) or (isinstance(v, dict) and len(v) < 8):
                    hits.append((f"{path}.{k}", v))
            find_feedback_keys(v, f"{path}.{k}", hits, depth + 1)
    elif isinstance(obj, list) and len(obj) < 30:
        for i, v in enumerate(obj):
            find_feedback_keys(v, f"{path}[{i}]", hits, depth + 1)
    return hits


def main() -> None:
    with sync_playwright() as p:
        b = p.chromium.launch(
            headless=True, args=["--disable-blink-features=AutomationControlled"]
        )
        ctx = b.new_context(user_agent=UA, locale="en-PH")
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = ctx.new_page()
        for seller in SELLERS:
            url = f"https://www.carousell.ph/u/{seller}/"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            body = page.inner_text("body", timeout=5000)
            html = page.content()
            print("=" * 60, seller)
            if "security verification" in body.lower():
                print("BLOCKED")
                continue
            for pat in [
                r"(\d(?:\.\d)?)\s*\(\s*(\d[\d,]*)\s*reviews?\s*\)",
                r"(\d[\d,]*)\s*reviews?",
                r"(\d(?:\.\d)?)\s*/\s*5",
                r"Positive",
                r"feedback",
            ]:
                m = re.search(pat, body, re.I)
                print(f"  pat {pat!r}: {m.group(0)[:80] if m else 'none'}")
            nd = extract_next_data(html)
            if nd:
                hits = find_feedback_keys(nd)
                print(f"  __NEXT_DATA__ hits ({len(hits)}):")
                for pth, val in hits[:15]:
                    print(f"    {pth}: {val!r}")
            else:
                print("  no __NEXT_DATA__")
            # snippet around 'review'
            idx = body.lower().find("review")
            if idx >= 0:
                print("  body snippet:", repr(body[max(0, idx - 40) : idx + 80]))
        b.close()


if __name__ == "__main__":
    main()
