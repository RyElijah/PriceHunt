"""
BeautifulSoup-based scrapers for Carousell PH and OLX PH (legacy URLs → Carousell).

Sites often return 403 to datacenter IPs; callers receive [] and an error is logged.
Use Playwright live search (default) when plain HTTP is blocked.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from tools.relevance import filter_relevant_listings

logger = logging.getLogger(__name__)

MAX_LISTINGS = 20
REQUEST_TIMEOUT = 20
MIN_DELAY_SEC = 1.0

_LAST_REQUEST_AT = 0.0

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-PH,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

Listing = dict[str, Any]


def _throttle() -> None:
    global _LAST_REQUEST_AT
    elapsed = time.monotonic() - _LAST_REQUEST_AT
    if elapsed < MIN_DELAY_SEC:
        time.sleep(MIN_DELAY_SEC - elapsed)
    _LAST_REQUEST_AT = time.monotonic()


def _slugify(query: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower().strip())
    return slug.strip("-") or "search"


def _parse_price(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"(?:₱|PHP|Php)\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE)
    if match:
        try:
            return int(float(match.group(1).replace(",", "")))
        except ValueError:
            pass
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def _normalize_listing(
    raw: dict[str, Any],
    *,
    source: str,
    base_url: str,
) -> Listing | None:
    price = raw.get("price")
    if isinstance(price, str):
        price = _parse_price(price)
    if price is None or price <= 0:
        return None

    title = (raw.get("title") or "").strip()
    if not title:
        return None

    url = raw.get("url") or ""
    if url and not url.startswith("http"):
        url = urljoin(base_url, url)

    return {
        "title": title,
        "price": int(price),
        "location": (raw.get("location") or "").strip() or "Meet-up not specified",
        "location_fetched": raw.get("location_fetched"),
        "seller_name": (raw.get("seller_name") or "Unknown").strip(),
        "seller_reviews": int(raw.get("seller_reviews") or 0),
        "seller_rating": raw.get("seller_rating"),
        "seller_profile_url": raw.get("seller_profile_url") or "",
        "seller_profile_fetched": raw.get("seller_profile_fetched"),
        "url": url,
        "image_url": raw.get("image_url") or "",
        "source": source,
    }


def _fetch_html(url: str) -> str:
    _throttle()
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    response = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    response.raise_for_status()
    return response.text


def _extract_from_next_data(html: str) -> list[dict[str, Any]]:
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        return []

    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            title = node.get("title") or node.get("name") or node.get("listing_title")
            price = node.get("price") or node.get("price_formatted") or node.get("amount")
            listing_id = node.get("id") or node.get("listing_id") or node.get("legacy_id")
            if title and price is not None:
                key = f"{title}|{price}"
                if key not in seen:
                    seen.add(key)
                    seller = node.get("seller") or {}
                    if isinstance(seller, dict):
                        seller_name = seller.get("username") or seller.get("name") or ""
                        reviews = seller.get("feedback_count") or seller.get("reviews") or 0
                    else:
                        seller_name = str(node.get("seller_name") or "")
                        reviews = node.get("seller_reviews") or 0

                    path = node.get("url") or node.get("permalink") or ""
                    if listing_id and not path:
                        path = f"/p/{listing_id}/"

                    results.append(
                        {
                            "title": str(title),
                            "price": price,
                            "location": node.get("location") or node.get("meetup_location") or "",
                            "seller_name": seller_name,
                            "seller_reviews": reviews,
                            "url": path,
                            "image_url": (
                                (node.get("photos") or [None])[0]
                                if isinstance(node.get("photos"), list)
                                else node.get("thumbnail") or node.get("image_url") or ""
                            ),
                        }
                    )
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return results


def _extract_from_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("@type") not in ("Product", "Offer", "ListItem"):
                continue
            offers = item.get("offers")
            if isinstance(offers, dict):
                price = offers.get("price")
            else:
                price = item.get("price")
            title = item.get("name") or item.get("title")
            if title and price:
                results.append(
                    {
                        "title": title,
                        "price": price,
                        "url": item.get("url") or "",
                        "image_url": (
                            item.get("image")[0]
                            if isinstance(item.get("image"), list)
                            else item.get("image") or ""
                        ),
                    }
                )
    return results


def _extract_from_anchors(soup: BeautifulSoup, base_url: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "/p/" not in href and "/products/" not in href:
            continue
        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue

        text = anchor.get_text(" ", strip=True)
        if len(text) < 5:
            continue

        price_match = re.search(
            r"(?:₱|PHP|Php)\s*([\d,]+(?:\.\d+)?)", text, re.IGNORECASE
        )
        if not price_match:
            parent = anchor.find_parent(["div", "article", "li"])
            if parent:
                price_match = re.search(
                    r"(?:₱|PHP|Php)\s*([\d,]+(?:\.\d+)?)",
                    parent.get_text(" ", strip=True),
                    re.IGNORECASE,
                )
        if not price_match:
            continue

        price = _parse_price(price_match.group(1))
        if price is None:
            continue

        title = re.sub(
            r"(?:₱|PHP|Php)\s*[\d,]+(?:\.\d+)?", "", text, flags=re.IGNORECASE
        ).strip()
        title = re.sub(r"\s+", " ", title)
        if len(title) < 3:
            continue

        seen_urls.add(full_url)
        results.append(
            {
                "title": title[:200],
                "price": price,
                "url": full_url,
                "seller_name": "Unknown",
                "seller_reviews": 0,
                "location": "Philippines",
                "image_url": "",
            }
        )
    return results


def _parse_listings_html(html: str, *, source: str, base_url: str) -> list[Listing]:
    normalized: list[Listing] = []
    seen: set[tuple[str, int]] = set()

    raw_items: list[dict[str, Any]] = []
    raw_items.extend(_extract_from_next_data(html))
    soup = BeautifulSoup(html, "html.parser")
    raw_items.extend(_extract_from_json_ld(soup))
    raw_items.extend(_extract_from_anchors(soup, base_url))

    for raw in raw_items:
        listing = _normalize_listing(raw, source=source, base_url=base_url)
        if not listing:
            continue
        if listing["price"] > 0:
            key = (listing["title"].lower()[:80], listing["price"])
            if key in seen:
                continue
            seen.add(key)
            normalized.append(listing)
        if len(normalized) >= MAX_LISTINGS:
            break

    return normalized


def _filter_by_budget(listings: list[Listing], budget: int) -> list[Listing]:
    """Prefer in-budget listings; if too few, include nearest above budget (real data)."""
    budget = int(budget)
    within = [L for L in listings if int(L.get("price") or 0) <= budget]
    if len(within) >= 3:
        return within
    if within:
        return within
    over = sorted(
        [
            L
            for L in listings
            if budget < int(L.get("price") or 0) <= max(budget * 2, budget + 15000)
        ],
        key=lambda x: int(x.get("price") or 0),
    )
    for item in over:
        item["over_budget"] = True
    if over:
        return over[:MAX_LISTINGS]
    return sorted(listings, key=lambda x: int(x.get("price") or 0))[:MAX_LISTINGS]


def _use_playwright() -> bool:
    return os.getenv("PRICEHUNT_USE_PLAYWRIGHT", "1").strip() not in ("0", "false", "no")


def search_carousell(query: str, budget: int) -> list[Listing]:
    """
    Search Carousell Philippines for listings at or below budget (PHP).
    """
    query = (query or "").strip()
    if not query:
        return []

    if _use_playwright():
        try:
            from tools.live_search import fetch_carousell_search

            listings = fetch_carousell_search(query, max_items=MAX_LISTINGS)
            listings = filter_relevant_listings(listings, query)
            filtered = _filter_by_budget(listings, int(budget))
            if filtered:
                return filtered[:MAX_LISTINGS]
        except ImportError:
            logger.warning("Playwright not installed — pip install playwright && playwright install chromium")
        except Exception:
            logger.exception("Live Carousell (Playwright) failed")

    slug = _slugify(query)
    urls = [
        f"https://www.carousell.ph/search/{quote_plus(query)}/?search={quote_plus(query)}&sort_by=2",
        f"https://www.carousell.ph/{slug}/q/?sort_by=2",
    ]

    for url in urls:
        try:
            html = _fetch_html(url)
            listings = _parse_listings_html(html, source="carousell", base_url="https://www.carousell.ph")
            filtered = _filter_by_budget(listings, int(budget))
            if filtered:
                return filtered[:MAX_LISTINGS]
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 403:
                logger.warning("Carousell: 403 Forbidden for %s", url)
            else:
                logger.warning("Carousell HTTP error: %s", exc)
        except requests.RequestException as exc:
            logger.warning("Carousell request failed: %s", exc)

    logger.info("Carousell: no results")
    return []


def search_olx(query: str, budget: int) -> list[Listing]:
    """
    Search OLX Philippines. olx.ph redirects to Carousell; we scrape the legacy
    browse URL pattern and Carousell search as fallback for broader coverage.
    """
    query = (query or "").strip()
    if not query:
        return []

    if _use_playwright():
        try:
            from tools.live_search import fetch_carousell_search

            # OLX PH listings are on Carousell; live browser search, tagged olx
            listings = fetch_carousell_search(query, max_items=MAX_LISTINGS, source="olx")
            listings = filter_relevant_listings(listings, query)
            filtered = _filter_by_budget(listings, int(budget))
            if filtered:
                return filtered[:MAX_LISTINGS]
        except Exception:
            logger.exception("Live OLX/Carousell (Playwright) failed")

    slug = _slugify(query)
    urls = [
        f"https://www.carousell.ph/search/{quote_plus(query)}/?search={quote_plus(query)}&sort_by=2",
        f"https://www.carousell.ph/{slug}/q/?sort_by=2",
    ]

    base = "https://www.carousell.ph"
    for url in urls:
        try:
            html = _fetch_html(url)
            if "carousell" in url.lower():
                base = "https://www.carousell.ph"
            listings = _parse_listings_html(html, source="olx", base_url=base)
            filtered = _filter_by_budget(listings, int(budget))
            if filtered:
                return filtered[:MAX_LISTINGS]
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 403:
                logger.warning("OLX: 403 Forbidden for %s", url)
            else:
                logger.warning("OLX HTTP error: %s", exc)
        except requests.RequestException as exc:
            logger.warning("OLX request failed: %s", exc)

    logger.info("OLX: no results")
    return []
