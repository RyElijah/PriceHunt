"""
Listing value and trust scoring for PriceHunt.

Call reset_market_context() with prices from the current search batch before
score_listing() so value scores reflect session market average.
"""

from __future__ import annotations

import statistics
from typing import Any

Listing = dict[str, Any]
ScoreResult = dict[str, Any]

_session_prices: list[int] = []


def reset_market_context(prices: list[int]) -> None:
    """Set reference prices from the current search (all platforms combined)."""
    global _session_prices
    _session_prices = [int(p) for p in prices if p and int(p) > 0]


def _market_average() -> float | None:
    if len(_session_prices) < 2:
        return None
    return statistics.median(_session_prices)


def score_listing(listing: Listing) -> ScoreResult:
    """
    Score a single listing dict.

    Returns:
        value_score (0-100), trust_score (0-100), flags (list[str]), recommendation (str)
    """
    price = int(listing.get("price") or 0)
    reviews = int(listing.get("seller_reviews") or 0)
    seller_rating = listing.get("seller_rating")
    title = (listing.get("title") or "").strip()
    location = (listing.get("location") or "").strip()
    image_url = (listing.get("image_url") or "").strip()
    url = (listing.get("url") or "").strip()
    seller = (listing.get("seller_name") or "").strip()

    flags: list[str] = []

    median = _market_average()
    if median and median > 0:
        ratio = price / median
        if ratio <= 0.75:
            value_score = 95
        elif ratio <= 0.9:
            value_score = 82
        elif ratio <= 1.05:
            value_score = 68
        elif ratio <= 1.2:
            value_score = 50
        else:
            value_score = 35
        pct_below = int((1 - ratio) * 100)
        if ratio < 0.55:
            flags.append(f"price {abs(pct_below)}% below market average")
            value_score = min(value_score, 40)
        elif ratio > 1.15:
            flags.append(f"price {int((ratio - 1) * 100)}% above session median")
    else:
        value_score = 60

    trust_score = 50

    if reviews >= 50:
        trust_score += 25
    elif reviews >= 15:
        trust_score += 18
    elif reviews >= 5:
        trust_score += 10
    elif reviews == 0 and listing.get("seller_profile_fetched", True):
        trust_score -= 15
        flags.append("seller has 0 reviews on Carousell")
    elif reviews == 0:
        trust_score -= 3

    if seller_rating is not None:
        try:
            stars = float(seller_rating)
            if stars >= 4.8:
                trust_score += 12
            elif stars >= 4.5:
                trust_score += 8
            elif stars >= 4.0:
                trust_score += 4
            elif stars < 3.5:
                trust_score -= 12
                flags.append(f"low seller rating ({stars:.1f}/5)")
        except (TypeError, ValueError):
            pass

    if len(title) >= 15:
        trust_score += 8
    else:
        trust_score -= 5
        flags.append("short or vague listing title")

    generic_locations = (
        "unknown",
        "philippines",
        "",
        "meet-up not loaded",
        "meet-up not specified by seller",
    )
    if location and location.lower() not in generic_locations:
        trust_score += 7
    else:
        flags.append("meet-up location not specified")

    if image_url:
        trust_score += 5
    else:
        trust_score -= 3

    if not url:
        trust_score -= 20
        flags.append("missing listing URL")

    if seller.lower() in ("unknown", "no_reviews", ""):
        trust_score -= 8

    if median and price < median * 0.45:
        trust_score -= 20
        if f"price {int((1 - price / median) * 100)}% below market average" not in flags:
            flags.append("price suspiciously below market average")

    trust_score = max(0, min(100, trust_score))
    value_score = max(0, min(100, value_score))

    if trust_score < 40 or value_score < 35:
        recommendation = "caution — review flags before contacting seller"
    elif trust_score >= 70 and value_score >= 65:
        recommendation = "strong pick — good price and trustworthy seller signals"
    elif value_score >= 65:
        recommendation = "good value — verify seller and item condition in person"
    else:
        recommendation = "acceptable — compare with other listings before buying"

    return {
        "value_score": int(value_score),
        "trust_score": int(trust_score),
        "flags": flags,
        "recommendation": recommendation,
    }
