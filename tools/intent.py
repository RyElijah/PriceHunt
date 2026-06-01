"""
Parse natural-language shopping requests (English + Taglish) into search parameters.
"""

from __future__ import annotations

import re

PRODUCT_ALIASES: dict[str, str] = {
    r"\bref\b": "refrigerator",
    r"\brefs\b": "refrigerator",
    r"\bfridge\b": "refrigerator",
    r"\bcp\b": "cellphone",
    r"\blappy\b": "laptop",
    r"\bmac\b": "macbook",
}

CONDITION_HINTS = (
    "like new",
    "good condition",
    "brand new",
    "medyo bago",
    "slightly used",
    "well used",
    "negotiable",
    "with box",
    "metro manila",
    "ncr",
    "cebu",
)


def _parse_budget_php(text: str, default: int = 25000) -> int:
    lowered = text.lower().replace(",", "")
    for match in re.finditer(r"(?:₱|php|peso)?\s*(\d+(?:\.\d+)?)\s*(k|thousand)?", lowered):
        amount = float(match.group(1))
        if match.group(2):
            amount *= 1000
        value = int(amount)
        if 500 <= value <= 5_000_000:
            return value
    for match in re.finditer(r"(?:under|below|max|hanggang|around|about)\s*(\d+)\s*(k)?", lowered):
        amount = float(match.group(1))
        if match.group(2):
            amount *= 1000
        value = int(amount)
        if 500 <= value <= 5_000_000:
            return value
    return default


def _apply_product_aliases(text: str) -> str:
    result = text
    for pattern, replacement in PRODUCT_ALIASES.items():
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def _extract_preferences(text: str) -> str:
    lowered = text.lower()
    found: list[str] = []
    for hint in CONDITION_HINTS:
        if hint in lowered:
            found.append(hint)
    return " · ".join(dict.fromkeys(found))


def interpret_user_query(text: str, *, default_budget: int = 25000) -> dict[str, str | int]:
    """
    Parse free-form user text into structured search fields.

    Example: "ref medyo bago around 5k" → refrigerator, budget 5000, preferences
    """
    raw = (text or "").strip()
    if not raw:
        return {
            "raw": "",
            "query": "",
            "budget": default_budget,
            "preferences": "",
        }

    budget = _parse_budget_php(raw, default_budget)
    preferences = _extract_preferences(raw)

    cleaned = raw
    cleaned = re.sub(
        r"(?:₱|php|peso)?\s*\d+(?:\.\d+)?\s*(?:k|thousand)?",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"(?:under|below|max|hanggang|around|about)\s*\d+\s*k?",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:around|about|only|lang|na|ng)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    for hint in CONDITION_HINTS:
        cleaned = re.sub(re.escape(hint), " ", cleaned, flags=re.IGNORECASE)
    cleaned = _apply_product_aliases(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")

    query = cleaned if len(cleaned) >= 2 else _apply_product_aliases(raw)

    return {
        "raw": raw,
        "query": query,
        "budget": budget,
        "preferences": preferences,
    }
