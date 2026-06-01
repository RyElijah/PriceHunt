"""
Live Carousell search via Playwright (headless + anti-bot tweaks).

Carousell returns 403 to plain requests; a real browser session is required.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Any
from urllib.parse import quote_plus, urljoin

from tools.relevance import _keywords, filter_relevant_listings

logger = logging.getLogger(__name__)

BASE_URL = "https://www.carousell.ph"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
WAIT_MS = 2500
NAV_TIMEOUT_MS = 45000
SCROLL_PASSES = 2
SCROLL_WAIT_MS = 500
LISTING_CARD_SELECTOR = "[data-testid*='listing-card']"
MAX_PROFILE_FETCHES = 5
PROFILE_WAIT_MS = 1200
MAX_LOCATION_FETCHES = 15
LOCATION_WAIT_MS = 1000
SEARCH_CACHE_TTL_SEC = 300

Listing = dict[str, Any]

# username -> {reviews, rating, profile_url}
_seller_profile_cache: dict[str, dict[str, Any]] = {}
# query (lower) -> (monotonic_ts, listings without source tag)
_search_result_cache: dict[str, tuple[float, list[Listing]]] = {}
# listing url base -> meet-up location string
_location_cache: dict[str, str] = {}


def _seller_profiles_enabled() -> bool:
    return os.getenv("PRICEHUNT_SELLER_PROFILES", "0").strip() in ("1", "true", "yes")


def _fetch_locations_enabled() -> bool:
    return os.getenv("PRICEHUNT_FETCH_LOCATIONS", "1").strip() not in ("0", "false", "no")


def _cache_get(query: str) -> list[Listing] | None:
    key = query.strip().lower()
    entry = _search_result_cache.get(key)
    if not entry:
        return None
    ts, listings = entry
    if time.monotonic() - ts > SEARCH_CACHE_TTL_SEC:
        _search_result_cache.pop(key, None)
        return None
    return [dict(L) for L in listings]


def _cache_set(query: str, listings: list[Listing]) -> None:
    key = query.strip().lower()
    _search_result_cache[key] = (time.monotonic(), [dict(L) for L in listings])


def _block_heavy_assets(route: Any) -> None:
    if route.request.resource_type in ("image", "media", "font"):
        route.abort()
    else:
        route.continue_()


def _wait_for_results(page: Any) -> None:
    try:
        page.wait_for_selector(LISTING_CARD_SELECTOR, timeout=12000)
    except Exception:
        page.wait_for_timeout(WAIT_MS)


def _parse_php_price(text: str) -> int | None:
    if not text:
        return None
    match = re.search(r"(?:₱|PHP|Php)\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
    if not match:
        return None
    try:
        return int(float(match.group(1).replace(",", "")))
    except ValueError:
        return None


def _parse_int(text: str) -> int:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else 0


def _parse_seller_profile_text(text: str) -> dict[str, Any]:
    """
    Extract review count and star rating from a Carousell seller profile page.

    Carousell layout (under "Profile details"):
        5.0
        19 reviews
    Or: N/A / No review yet when the seller has no feedback.
    """
    reviews = 0
    rating: float | None = None

    section = text
    if "Profile details" in text:
        section = text.split("Profile details", 1)[1][:1200]

    if re.search(r"no review yet", section, re.IGNORECASE):
        return {"reviews": 0, "rating": None}

    rev_m = re.search(
        r"(\d[\d,]*)\s+reviews?\b",
        section,
        re.IGNORECASE,
    )
    if rev_m:
        reviews = _parse_int(rev_m.group(1))

    stacked = re.search(
        r"(?:^|\n)\s*([1-5](?:\.\d)?)\s*\n+\s*(\d[\d,]*)\s+reviews?\b",
        section,
        re.IGNORECASE | re.MULTILINE,
    )
    if stacked:
        rating = float(stacked.group(1))
        reviews = _parse_int(stacked.group(2))
    elif rev_m:
        before = section[: rev_m.start()]
        for line in reversed([ln.strip() for ln in before.split("\n") if ln.strip()][-6:]):
            if re.fullmatch(r"[1-5](?:\.\d)?", line):
                rating = float(line)
                break
            if line.upper() == "N/A":
                break

    combined = re.search(
        r"(\d(?:\.\d)?)\s*\(\s*(\d[\d,]*)\s*reviews?\s*\)",
        section,
        re.IGNORECASE,
    )
    if combined:
        rating = float(combined.group(1))
        reviews = _parse_int(combined.group(2))

    if rating is not None and not (1.0 <= rating <= 5.0):
        rating = None

    return {"reviews": reviews, "rating": rating}


def fetch_seller_profile(page: Any, username: str) -> dict[str, Any]:
    """Load /u/{username}/ and read reviews + rating (cached per process)."""
    username = (username or "").strip().lstrip("@")
    if not username or username.lower() == "unknown":
        return {"reviews": 0, "rating": None, "profile_url": ""}

    if username in _seller_profile_cache:
        return _seller_profile_cache[username]

    profile_url = urljoin(BASE_URL, f"/u/{username}/")
    info: dict[str, Any] = {
        "reviews": 0,
        "rating": None,
        "profile_url": profile_url,
        "fetched": False,
    }

    try:
        page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(PROFILE_WAIT_MS)
        body = page.inner_text("body", timeout=5000)
        if "security verification" in body.lower() or "cloudflare" in body.lower()[:500]:
            logger.warning("Seller profile blocked for %s (bot check)", username)
            _seller_profile_cache[username] = info
            return info

        parsed = _parse_seller_profile_text(body)
        info["reviews"] = parsed["reviews"]
        info["rating"] = parsed["rating"]
        info["fetched"] = True
    except Exception as exc:
        logger.warning("Seller profile fetch failed for %s: %s", username, exc)

    _seller_profile_cache[username] = info
    return info


def enrich_listings_with_seller_profiles(
    page: Any, listings: list[Listing], *, max_fetches: int = MAX_PROFILE_FETCHES
) -> None:
    """Attach real seller review counts and ratings from Carousell profile pages."""
    if not _seller_profiles_enabled():
        for listing in listings:
            seller = (listing.get("seller_name") or "").strip()
            if seller and seller.lower() != "unknown":
                listing.setdefault(
                    "seller_profile_url",
                    urljoin(BASE_URL, f"/u/{seller}/"),
                )
            listing.setdefault("seller_reviews", 0)
            listing.setdefault("seller_rating", None)
            listing.setdefault("seller_profile_fetched", False)
        return

    fetches = 0
    for listing in listings:
        seller = (listing.get("seller_name") or "").strip()
        if not seller or seller.lower() == "unknown":
            continue

        if seller not in _seller_profile_cache:
            if fetches >= max_fetches:
                _seller_profile_cache[seller] = {
                    "reviews": 0,
                    "rating": None,
                    "profile_url": urljoin(BASE_URL, f"/u/{seller}/"),
                    "fetched": False,
                }
            else:
                fetch_seller_profile(page, seller)
                fetches += 1

        profile = _seller_profile_cache.get(seller, {})
        listing["seller_reviews"] = int(profile.get("reviews") or 0)
        listing["seller_rating"] = profile.get("rating")
        listing["seller_profile_fetched"] = bool(profile.get("fetched"))
        listing["seller_profile_url"] = profile.get("profile_url") or listing.get(
            "seller_profile_url", ""
        )


_CONDITION_LINE = re.compile(
    r"^(lightly|brand|like|well|heavily|slightly|fairly)\s+",
    re.IGNORECASE,
)
_CONDITION_PHRASES = (
    "used with care",
    "no visible",
    "visible flaws",
    "flaws,",
    "free shipping",
    "shipping fee",
    "meet-up not",
)
_PRODUCT_FIELD_LABELS = frozenset(
    {
        "description",
        "posted",
        "model",
        "storage",
        "category",
        "brand",
        "type",
        "color",
        "size",
        "warranty",
        "series",
        "likes",
        "chat",
        "home",
        "follow",
        "share",
    }
)


def _is_meetup_place_line(line: str) -> bool:
    """True if a line is a seller meet-up place (not condition/shipping UI noise)."""
    if not line or len(line) < 3 or len(line) > 120:
        return False
    low = line.lower().strip()
    if low in (
        "meet-up",
        "meetup",
        "mailing · meetup",
        "mailing",
        "condition",
        "meet the seller",
    ):
        return False
    if low in _PRODUCT_FIELD_LABELS:
        return False
    if low.startswith("see ") and "location" in low:
        return False
    if low.startswith("meet ") and "seller" in low:
        return False
    if _CONDITION_LINE.match(low):
        return False
    if any(phrase in low for phrase in _CONDITION_PHRASES):
        return False
    if _parse_php_price(line) is not None:
        return False
    if re.match(r"^\d+(\.\d+)?$", low):
        return False
    if re.search(r"\b\d+\s+(?:hours?|minutes?|days?|weeks?)\s+ago\b", low):
        return False
    if "iphone" in low and "series" in low:
        return False
    if " · " in line and any(x in low for x in ("gadgets", "mobile phones", "followers")):
        return False
    return True


def _extract_places_from_meetup_block(block: str) -> list[str]:
    places: list[str] = []
    for line in block.split("\n"):
        line = line.strip()
        if _is_meetup_place_line(line):
            places.append(line)
    return places


def _parse_listing_location_text(text: str) -> str:
    """Parse seller meet-up places from a Carousell listing detail page."""
    if not text:
        return ""

    places: list[str] = []
    # Pages may have duplicate Meet-up sections; parse each chunk separately.
    for header in re.finditer(r"Meet-?up\s*\n+", text, re.IGNORECASE):
        rest = text[header.end() :]
        end = re.search(
            r"\n(?:Condition|See \d+\+?\s*locations|Meet the seller)\b",
            rest,
            re.IGNORECASE,
        )
        block = rest[: end.start()] if end else rest[:400]
        places.extend(_extract_places_from_meetup_block(block))

    if places:
        return " · ".join(dict.fromkeys(places[:8]))

    if re.search(r"\bmailing\b", text, re.IGNORECASE) and not re.search(
        r"meet-?up", text, re.IGNORECASE
    ):
        return "Mailing / shipping"

    return ""


def _expected_location_count(text: str) -> int:
    m = re.search(r"see\s+(\d+)\+?\s*locations?", text, re.IGNORECASE)
    if not m:
        return 0
    try:
        return max(1, int(m.group(1)))
    except ValueError:
        return 0


def _expand_meetup_locations(page: Any) -> None:
    """Click 'See N+ locations' on the listing card (not global nav)."""
    try:
        meet_header = page.get_by_text(re.compile(r"^Meet-?up$", re.IGNORECASE))
        if meet_header.count() < 1:
            return
        section = meet_header.last.locator("xpath=ancestor::*[self::section or self::div][1]")
        btn = section.locator("button, a").filter(
            has_text=re.compile(r"see\s+\d+\+?\s*locations?", re.IGNORECASE)
        )
        if btn.count():
            btn.first.click(timeout=2500)
            page.wait_for_timeout(700)
    except Exception:
        pass


def fetch_listing_location(page: Any, listing_url: str) -> tuple[str, bool]:
    """Open listing page and read seller meet-up location(s)."""
    base = (listing_url or "").split("?")[0].rstrip("/") + "/"
    if not base or "/p/" not in base:
        return "", False

    if base in _location_cache:
        cached = _location_cache[base]
        return cached, bool(cached)

    loc = ""
    try:
        page.goto(base, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(LOCATION_WAIT_MS)
        body = page.inner_text("body", timeout=5000)
        if "security verification" not in body.lower():
            loc = _parse_listing_location_text(body)
            need = _expected_location_count(body)
            have = len([p for p in loc.split(" · ") if p]) if loc else 0
            if need and have < need:
                _expand_meetup_locations(page)
                body = page.inner_text("body", timeout=5000)
                loc = _parse_listing_location_text(body) or loc
    except Exception as exc:
        logger.warning("Location fetch failed for %s: %s", base, exc)

    _location_cache[base] = loc
    return loc, bool(loc)


def enrich_listings_with_locations(
    page: Any, listings: list[Listing], *, max_fetches: int = MAX_LOCATION_FETCHES
) -> None:
    """Fill meet-up location from each listing's detail page (seller-provided)."""
    if not _fetch_locations_enabled():
        for listing in listings:
            listing.setdefault("location", "Meet-up not loaded")
            listing["location_fetched"] = False
        return

    fetches = 0
    for listing in listings:
        url = listing.get("url") or ""
        base = url.split("?")[0].rstrip("/") + "/" if url else ""

        if base and base in _location_cache:
            loc = _location_cache[base]
            if loc:
                listing["location"] = loc
            listing["location_fetched"] = bool(loc)
            continue

        if fetches >= max_fetches:
            listing["location"] = listing.get("location") or "Meet-up not loaded"
            listing["location_fetched"] = False
            continue

        loc, ok = fetch_listing_location(page, url)
        fetches += 1
        if loc:
            listing["location"] = loc
        else:
            listing["location"] = "Meet-up not specified by seller"
        listing["location_fetched"] = ok


def _parse_card_text_fallback(card_text: str) -> tuple[str, str, int | None, str]:
    """
    Parse card inner text when structured selectors fail.
    Typical order: seller, time ago, title, price, condition/extra.
    """
    lines = [ln.strip() for ln in card_text.split("\n") if ln.strip()]
    if not lines:
        return "", "Philippines", None, ""

    seller = lines[0]
    title = ""
    price = None
    location = "Philippines"

    time_pat = re.compile(
        r"^\d+\s+(?:second|minute|hour|day|week|month|year)s?\s+ago$|^\d+\s+(?:min|hr|mo|yr)s?\s+ago$",
        re.I,
    )

    for line in lines[1:]:
        if time_pat.match(line):
            continue
        p = _parse_php_price(line)
        if p is not None and price is None:
            price = p
            continue
        if not title and len(line) > 8 and not line.isdigit():
            title = line

    return seller, location, price, title


def _extract_listing_from_card(card: Any, *, source: str) -> Listing | None:
    try:
        seller_el = card.locator("[data-testid='listing-card-text-seller-name']")
        if seller_el.count() == 0:
            return None

        seller_name = seller_el.first.inner_text(timeout=2000).strip()
        profile_link = card.locator("a[href*='/u/']").first
        profile_url = ""
        if profile_link.count():
            href = profile_link.get_attribute("href") or ""
            profile_url = href if href.startswith("http") else urljoin(BASE_URL, href)
            user_match = re.search(r"/u/([^/?#]+)/?", href)
            if user_match:
                # Username from href matches Carousell profile/reviews (display name may differ).
                seller_name = user_match.group(1)

        product_link = card.locator("a[href*='/p/']").first
        if product_link.count() == 0:
            return None

        href = product_link.get_attribute("href") or ""
        if "/p/" not in href:
            return None

        link_text = product_link.inner_text(timeout=2000)
        lines = [ln.strip() for ln in link_text.split("\n") if ln.strip()]
        title = lines[0] if lines else ""
        price = None
        for line in lines[1:8]:
            p = _parse_php_price(line)
            if p is not None:
                price = p
                break

        if not title or price is None:
            card_text = card.inner_text(timeout=2000)
            fb_seller, fb_loc, fb_price, fb_title = _parse_card_text_fallback(card_text)
            seller_name = seller_name or fb_seller
            title = title or fb_title
            price = price if price is not None else fb_price
            location = fb_loc
        else:
            location = ""

        loc_el = card.locator(
            "[data-testid*='location'], [data-testid*='meetup'], "
            "[data-testid*='meet-up']"
        )
        if loc_el.count():
            loc_text = loc_el.first.inner_text(timeout=1000).strip()
            if loc_text and loc_text.lower() not in ("philippines", "meet-up"):
                location = loc_text

        url = href if href.startswith("http") else urljoin(
            BASE_URL, href.split("?")[0].rstrip("/") + "/"
        )

        image_url = ""
        img = card.locator("img[src*='karousell']").first
        if img.count():
            image_url = img.get_attribute("src") or ""

        return {
            "title": title[:200],
            "price": int(price),
            "location": location or "",
            "location_fetched": bool(location),
            "seller_name": seller_name or "Unknown",
            "seller_reviews": 0,
            "seller_rating": None,
            "seller_profile_url": profile_url,
            "url": url,
            "image_url": image_url,
            "source": source,
        }
    except Exception:
        return None


def _build_search_urls(query: str) -> list[str]:
    q = query.strip()
    encoded = quote_plus(q)
    slug = re.sub(r"[^a-z0-9]+", "-", q.lower()).strip("-") or "search"
    # Path-based URLs return real results; ?query= alone often loads unrelated feed.
    return [
        f"{BASE_URL}/search/{encoded}/?search={encoded}&sort_by=2",
        f"{BASE_URL}/{slug}/q/?sort_by=2",
        f"{BASE_URL}/search/?query={encoded}&sort_by=2",
    ]


def _search_page_matches_query(page: Any, query: str) -> bool:
    """True when the loaded page is actually filtered to the user's search."""
    keys = _keywords(query)
    if not keys:
        return True
    try:
        heading = page.locator("h1").first.inner_text(timeout=4000).lower()
    except Exception:
        heading = ""
    heading_norm = heading.replace("'", "").replace("+", " ")
    if keys and all(k in heading_norm for k in keys):
        return True
    try:
        body = page.inner_text("body", timeout=5000).lower()
    except Exception:
        return False
    primary = max(keys, key=len)
    return body.count(primary) >= 8


def _scroll_results(page: Any) -> None:
    for _ in range(SCROLL_PASSES):
        page.mouse.wheel(0, 1200)
        page.wait_for_timeout(SCROLL_WAIT_MS)


def extract_listings_from_page(
    page: Any,
    *,
    query: str,
    source: str,
    max_items: int,
) -> list[Listing]:
    listings: list[Listing] = []
    seen: set[str] = set()

    cards = page.locator(LISTING_CARD_SELECTOR)
    count = cards.count()

    if count == 0:
        logger.warning("No listing cards found on page")
        return []

    scan_limit = min(count, max(max_items * 6, 40))
    for i in range(scan_limit):
        card = cards.nth(i)
        if card.locator("[data-testid='listing-card-text-seller-name']").count() == 0:
            continue
        listing = _extract_listing_from_card(card, source=source)
        if not listing:
            continue

        base_url = listing["url"].split("?")[0]
        if base_url in seen:
            continue

        seen.add(base_url)
        listings.append(listing)

    listings = filter_relevant_listings(listings, query, min_results=1)
    listings = listings[:max_items]

    if listings:
        enrich_listings_with_locations(page, listings)
        enrich_listings_with_seller_profiles(page, listings)
    return listings


def _scrape_carousell_uncached(query: str, *, max_items: int) -> list[Listing]:
    from playwright.sync_api import sync_playwright

    for url in _build_search_urls(query):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                context = browser.new_context(
                    user_agent=USER_AGENT,
                    viewport={"width": 1280, "height": 900},
                    locale="en-PH",
                )
                context.route("**/*", _block_heavy_assets)
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                )
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
                _wait_for_results(page)
                _scroll_results(page)
                if not _search_page_matches_query(page, query):
                    logger.warning(
                        "Carousell page does not match query %r — trying next URL: %s",
                        query,
                        url,
                    )
                    browser.close()
                    continue

                listings = extract_listings_from_page(
                    page, query=query, source="carousell", max_items=max_items
                )
                browser.close()

            if listings:
                logger.info(
                    "Live Carousell: %d relevant listings for %r from %s",
                    len(listings),
                    query,
                    url,
                )
                return listings[:max_items]
        except Exception as exc:
            logger.warning("Live Carousell fetch failed for %s: %s", url, exc)

    return []


def fetch_carousell_search(
    query: str, *, max_items: int = 20, source: str = "carousell"
) -> list[Listing]:
    query = (query or "").strip()
    if not query:
        return []

    cached = _cache_get(query)
    if cached is None:
        cached = _scrape_carousell_uncached(query, max_items=max_items)
        if cached:
            _cache_set(query, cached)
    else:
        logger.debug("Using cached Carousell results for %r", query)

    return [{**L, "source": source} for L in cached[:max_items]]


def fetch_live_listings_for_pipeline(
    query: str, *, max_items: int = 20
) -> list[Listing]:
    """
    One browser scrape; tag half the results as Carousell and half as OLX
    (OLX PH inventory is on Carousell — avoids a second ~40s browser run).
    """
    query = (query or "").strip()
    if not query:
        return []

    raw = fetch_carousell_search(query, max_items=max_items, source="carousell")
    if not raw:
        return []

    if len(raw) == 1:
        return raw

    mid = max(1, len(raw) // 2)
    tagged: list[Listing] = []
    for i, item in enumerate(raw):
        row = dict(item)
        row["source"] = "olx" if i >= mid else "carousell"
        tagged.append(row)
    return tagged
