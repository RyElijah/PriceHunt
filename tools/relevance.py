"""Filter listings so results match the user's product search."""

from __future__ import annotations

import re

# Words that are not product keywords (condition/location — not for title match)
STOPWORDS = frozenset(
    {
        "like",
        "new",
        "good",
        "condition",
        "brand",
        "used",
        "well",
        "medyo",
        "bago",
        "slightly",
        "negotiable",
        "with",
        "box",
        "metro",
        "manila",
        "ncr",
        "cebu",
        "philippines",
        "and",
        "or",
        "the",
        "a",
        "for",
        "under",
        "below",
        "around",
        "about",
        "only",
        "lang",
        "na",
        "ng",
    }
)


def _keywords(query: str) -> list[str]:
    """Meaningful search tokens (min 2 chars, not stopwords)."""
    tokens = re.findall(r"[a-z0-9]+", query.lower())
    return [t for t in tokens if len(t) >= 2 and t not in STOPWORDS]


def _token_matches(token: str, hay: str) -> bool:
    """Match a query token in title/slug text (numeric tokens use word boundaries)."""
    if token.isdigit():
        return bool(re.search(rf"(?<![0-9]){re.escape(token)}(?![0-9])", hay))
    return token in hay


def _slug_from_url(url: str) -> str:
    """Product slug from Carousell /p/... URL (ignore numeric listing id at end)."""
    if not url:
        return ""
    match = re.search(r"/p/([^/?#]+)", url.lower())
    if not match:
        return ""
    slug = match.group(1)
    slug = re.sub(r"-\d{6,}$", "", slug)
    return slug.replace("-", " ")


def title_matches_query(title: str, query: str, *, url: str = "") -> bool:
    """
    True if listing title (or product URL slug) plausibly matches the search product.

    For "iphone se" → title must contain "iphone" AND "se" (or slug has both).
    For single token "iphone" → title must contain "iphone".
    """
    if not query.strip():
        return True

    keys = _keywords(query)
    if not keys:
        return True

    slug = _slug_from_url(url)
    hay = f"{title} {slug}".lower()

    return all(_token_matches(k, hay) for k in keys)


def filter_relevant_listings(
    listings: list[dict],
    query: str,
    *,
    min_results: int = 3,
) -> list[dict]:
    """Keep only listings whose title matches query; relax if too few matches."""
    if not listings or not query.strip():
        return listings

    matched = [
        L
        for L in listings
        if title_matches_query(str(L.get("title", "")), query, url=str(L.get("url", "")))
    ]

    if len(matched) >= min_results:
        return matched

    # Partial match: at least the longest/primary keyword (e.g. "iphone" from "iphone se")
    keys = _keywords(query)
    if not keys:
        return listings

    primary = max(keys, key=len)
    partial = [
        L
        for L in listings
        if _token_matches(
            primary,
            f"{L.get('title', '')} {_slug_from_url(str(L.get('url', '')))}".lower(),
        )
    ]
    if partial:
        return partial

    return matched
