"""One-off: inspect seller/rating fields on Carousell search cards and profiles."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright

from tools.live_search import (
    _parse_seller_profile_text,
    fetch_carousell_search,
    fetch_seller_profile,
)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def main() -> None:
    listings = fetch_carousell_search("iphone 14", max_items=5)
    print(f"Got {len(listings)} listings\n")
    for L in listings:
        print(
            f"- {L['seller_name']!r} | reviews={L.get('seller_reviews')} "
            f"rating={L.get('seller_rating')} fetched={L.get('seller_profile_fetched')}"
        )
        print(f"  title: {L['title'][:60]}...")
        print(f"  url: {L['url'][:80]}")


if __name__ == "__main__":
    main()
