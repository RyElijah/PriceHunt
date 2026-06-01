"""
Carousell search suggestions and autocorrect.

Uses Carousell PH top-searches API + fuzzy matching so typos map to
terms people actually search on the marketplace.
"""

from __future__ import annotations

import logging
import re
import time
from difflib import SequenceMatcher, get_close_matches
from functools import lru_cache
from typing import Any

import requests

logger = logging.getLogger(__name__)

TOP_SEARCHES_URL = (
    "https://www.carousell.ph/ds/keywords/1.0/top-searches"
    "?_path=%2F1.0%2Ftop-searches&count=100&country_code=PH&l=en&offset=0"
)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# Common typos / shorthand → Carousell-friendly terms
STATIC_ALIASES: dict[str, str] = {
    "iphoen": "iphone",
    "iphon": "iphone",
    "ipone": "iphone",
    "ifone": "iphone",
    "macbok": "macbook",
    "mac book": "macbook",
    "macbookair": "macbook air",
    "macbookpro": "macbook pro",
    "airpods": "airpods pro",
    "ps 5": "ps5",
    "playstation 5": "ps5",
    "samsun": "samsung",
    "galxy": "galaxy",
    "nintendo switch oled": "nintendo switch",
}

# Seed terms if API fails
FALLBACK_TERMS: list[str] = [
    "iphone 14",
    "iphone 13",
    "iphone 15",
    "iphone 12 pro",
    "macbook air",
    "macbook pro",
    "ps5",
    "airpods pro",
    "samsung galaxy",
    "nintendo switch",
    "laptop",
    "sofa bed",
    "gaming chair",
    "canon camera",
    "dyson",
]

_cache_at: float = 0.0
_cache_terms: list[str] = []
_CACHE_TTL_SEC = 3600


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _apply_aliases(text: str) -> str:
    lowered = text.lower()
    for wrong, right in STATIC_ALIASES.items():
        if wrong in lowered:
            lowered = re.sub(re.escape(wrong), right, lowered, flags=re.IGNORECASE)
    return _normalize_whitespace(lowered)


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def fetch_carousell_top_searches(*, force_refresh: bool = False) -> list[str]:
    """Trending search terms on Carousell Philippines."""
    global _cache_at, _cache_terms
    now = time.monotonic()
    if not force_refresh and _cache_terms and (now - _cache_at) < _CACHE_TTL_SEC:
        return list(_cache_terms)

    try:
        response = requests.get(TOP_SEARCHES_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        terms = payload.get("data") or []
        cleaned = [_normalize_whitespace(str(t)) for t in terms if str(t).strip()]
        if cleaned:
            merged = list(dict.fromkeys(cleaned + FALLBACK_TERMS))
            _cache_terms = merged
            _cache_at = now
            logger.info("Loaded %d Carousell top search terms", len(cleaned))
            return merged
    except Exception as exc:
        logger.warning("Carousell top-searches API failed: %s", exc)

    _cache_terms = list(FALLBACK_TERMS)
    _cache_at = now
    return list(FALLBACK_TERMS)


def suggest_queries(partial: str, *, limit: int = 8) -> list[str]:
    """
    Return Carousell-style suggestions for what the user is typing.
    """
    partial = _apply_aliases(_normalize_whitespace(partial))
    if len(partial) < 1:
        return fetch_carousell_top_searches()[:limit]

    catalog = fetch_carousell_top_searches()
    p = partial.lower()
    scored: list[tuple[float, str]] = []

    for term in catalog:
        tl = term.lower()
        if tl == p:
            scored.append((0.0, term))
        elif tl.startswith(p):
            scored.append((0.05 + len(p) / max(len(tl), 1) * 0.01, term))
        elif p in tl:
            scored.append((0.15, term))
        else:
            ratio = _similarity(p, tl)
            if ratio >= 0.55:
                scored.append((0.35 + (1 - ratio), term))

    # Whole-query fuzzy match (typo tolerance)
    for match in get_close_matches(p, [t.lower() for t in catalog], n=5, cutoff=0.65):
        for term in catalog:
            if term.lower() == match:
                scored.append((0.12, term))

    scored.sort(key=lambda x: (x[0], len(x[1])))
    seen: set[str] = set()
    results: list[str] = []
    for _, term in scored:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(term)
        if len(results) >= limit:
            break

    if not results and len(p) >= 2:
        results = [partial]
    return results


def autocorrect_query(query: str) -> tuple[str, bool, str]:
    """
    Pick the best Carousell search term for a user query.

    Returns:
        (corrected_query, was_corrected, message_for_ui)
    """
    raw = _normalize_whitespace(query)
    if not raw:
        return raw, False, ""

    normalized = _apply_aliases(raw)
    suggestions = suggest_queries(normalized, limit=5)

    if not suggestions:
        return normalized, False, ""

    best = suggestions[0]
    if best.lower() == raw.lower():
        return best, False, ""

    if best.lower() == normalized.lower() and normalized.lower() != raw.lower():
        return best, True, f"Adjusted spelling: **{raw}** → **{best}**"

    sim_raw = _similarity(raw, best)
    sim_norm = _similarity(normalized, best)

    if sim_raw >= 0.88 or sim_norm >= 0.78:
        return best, True, f"Using Carousell search term: **{best}**"

    # Do not expand "iphone" → "iphone 14" — keep user's exact product terms
    return normalized if normalized != raw else raw, normalized != raw, (
        f"Adjusted spelling: **{raw}** → **{normalized}**" if normalized != raw else ""
    )


@lru_cache(maxsize=256)
def cached_suggestions(partial: str) -> tuple[str, ...]:
    """Streamlit-friendly cached wrapper."""
    return tuple(suggest_queries(partial))
