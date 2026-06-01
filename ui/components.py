"""Reusable UI blocks for PriceHunt."""

from __future__ import annotations

import html
import os
from typing import Any

import streamlit as st

from ui.theme import score_bar_color

Listing = dict[str, Any]
ResultData = dict[str, Any]


def render_sidebar_brand() -> None:
    st.markdown(
        """
        <div class="ph-sidebar-brand">Price<span style="color:#2dd4bf">Hunt</span></div>
        <div class="ph-sidebar-tag">Smart preloved shopping · PH</div>
        """,
        unsafe_allow_html=True,
    )


def render_hero() -> None:
    st.markdown(
        """
        <div class="ph-hero">
            <h1>Find the best <span>preloved</span> deals</h1>
            <p>
                Search Carousell & OLX in one place. We score every listing for
                fair price and seller trust — so you buy safe, not sorry.
            </p>
            <div class="ph-pills">
                <span class="ph-pill">Value score</span>
                <span class="ph-pill">Trust score</span>
                <span class="ph-pill">Negotiation draft</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state() -> None:
    st.markdown(
        """
        <div class="ph-empty">
            <div class="ph-empty-icon">🔍</div>
            <p style="font-size:1rem;font-weight:600;color:#94a3b8;margin:0;">
                Search for any product to get started
            </p>
            <p style="font-size:0.85rem;margin-top:0.5rem;">
                Try &quot;iPhone 13&quot; or &quot;MacBook Air M1&quot; with your max budget in pesos.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_html(fragment: str) -> None:
    """Render HTML without markdown code-block issues from indented lines."""
    st.markdown(fragment.strip(), unsafe_allow_html=True)


def _score_bar_html(label: str, score: int) -> str:
    color = score_bar_color(score)
    safe_label = html.escape(label)
    return (
        f'<div class="ph-score-block">'
        f'<div class="ph-score-label">{safe_label}</div>'
        f'<div class="ph-score-bar-bg">'
        f'<div class="ph-score-bar" style="width:{score}%;background:{color};"></div>'
        f"</div>"
        f'<div class="ph-score-num">{score}/100</div>'
        f"</div>"
    )


def _listing_card_html(
    item: Listing,
    *,
    rank: int | None = None,
    is_top: bool = False,
    is_flagged: bool = False,
) -> str:
    title = html.escape(str(item.get("title", "Untitled")))
    price = int(item.get("price") or 0)
    seller = html.escape(str(item.get("seller_name", "Unknown")))
    reviews = int(item.get("seller_reviews") or 0)
    seller_rating = item.get("seller_rating")
    profile_url = html.escape(str(item.get("seller_profile_url") or ""))
    raw_location = (item.get("location") or "").strip()
    location_fetched = item.get("location_fetched")
    if raw_location and location_fetched is not False:
        location = html.escape(raw_location)
        if " · " in raw_location:
            parts = [html.escape(p.strip()) for p in raw_location.split(" · ") if p.strip()]
            location_line = "&#128205; Meet-up: " + " · ".join(parts)
        else:
            location_line = f"&#128205; Meet-up: {location}"
    elif raw_location:
        location_line = f"&#128205; {html.escape(raw_location)}"
    elif location_fetched is False:
        location_line = "&#128205; Meet-up location not loaded (search limit)"
    else:
        location_line = "&#128205; Meet-up not specified"
    url = html.escape(str(item.get("url") or "#"))

    profile_fetched = item.get("seller_profile_fetched")
    review_label = f"{reviews} review{'s' if reviews != 1 else ''}"

    if seller_rating is not None:
        try:
            stars = float(seller_rating)
            seller_line = f"&#128100; {seller} &middot; {stars:.1f}/5 ({review_label})"
        except (TypeError, ValueError):
            seller_line = f"&#128100; {seller} &middot; {review_label}"
    elif profile_fetched is False:
        seller_line = f"&#128100; {seller} &middot; rating not loaded (search limit)"
    elif profile_fetched and reviews == 0:
        seller_line = f"&#128100; {seller} &middot; no Carousell reviews yet"
    else:
        seller_line = f"&#128100; {seller} &middot; {review_label}"
    source = (item.get("source") or "carousell").lower()
    value = int(item.get("value_score", 0))
    trust = int(item.get("trust_score", 0))
    flags = item.get("flags") or []

    card_class = "ph-card"
    if is_top:
        card_class += " top-pick"
    if is_flagged:
        card_class += " flagged"

    badges = ""
    if is_top:
        badges += '<span class="ph-badge ph-badge-top">Top pick</span>'
    if source == "olx":
        badges += '<span class="ph-badge ph-badge-source-o">OLX</span>'
    else:
        badges += '<span class="ph-badge ph-badge-source-c">Carousell</span>'
    if item.get("over_budget"):
        badges += '<span class="ph-badge" style="background:#422006;color:#fbbf24;">Over budget</span>'
    if rank and rank > 1:
        badges += f'<span class="ph-badge" style="background:#1e2738;color:#94a3b8;">#{rank}</span>'

    flags_html = "".join(
        f'<div class="ph-flag">&#9888; {html.escape(str(f))}</div>' for f in flags
    )
    scores_html = _score_bar_html("Value", value) + _score_bar_html("Trust", trust)

    profile_link = ""
    if profile_url and seller.lower() != "unknown":
        profile_link = (
            f'<a href="{profile_url}" target="_blank" rel="noopener" '
            f'style="color:#94a3b8;font-size:0.85rem;font-weight:600;text-decoration:none;">'
            f"Seller profile &rarr;</a>"
        )

    return (
        f'<div class="{card_class}">'
        f"{badges}"
        f'<div class="ph-card-title">{title}</div>'
        f'<div class="ph-price">&#8369;{price:,}</div>'
        f'<div class="ph-meta">{seller_line}</div>'
        f'<div class="ph-meta">{location_line}</div>'
        f'<div class="ph-scores">{scores_html}</div>'
        f'<div class="ph-flags">{flags_html}</div>'
        f'<div style="margin-top:0.75rem;display:flex;gap:1rem;flex-wrap:wrap;">'
        f'<a href="{url}" target="_blank" rel="noopener" '
        f'style="color:#2dd4bf;font-size:0.85rem;font-weight:600;text-decoration:none;">'
        f"View listing &rarr;</a>"
        f"{profile_link}"
        f"</div>"
        f"</div>"
    )


def render_stats(data: ResultData) -> None:
    listings = data.get("listings") or []
    flagged = data.get("flagged") or []
    carousell = "ok" if data.get("carousell_ok") else "warn"
    olx = "ok" if data.get("olx_ok") else "warn"

    budget = int(data.get("budget", 0))
    c_ok = "&#10003;" if data.get("carousell_ok") else "&#10007;"
    o_ok = "&#10003;" if data.get("olx_ok") else "&#10007;"
    _render_html(
        f'<div class="ph-stats">'
        f'<div class="ph-stat"><div class="ph-stat-label">Listings</div>'
        f'<div class="ph-stat-value">{len(listings)}</div></div>'
        f'<div class="ph-stat"><div class="ph-stat-label">Budget</div>'
        f'<div class="ph-stat-value">&#8369;{budget:,}</div></div>'
        f'<div class="ph-stat"><div class="ph-stat-label">Carousell</div>'
        f'<div class="ph-stat-value {carousell}">{c_ok}</div></div>'
        f'<div class="ph-stat"><div class="ph-stat-label">OLX</div>'
        f'<div class="ph-stat-value {olx}">{o_ok}</div></div>'
        f"</div>"
    )
    if flagged:
        st.caption(f"⚠ {len(flagged)} listing(s) flagged — review before buying.")


def render_listing_card(
    item: Listing,
    *,
    rank: int | None = None,
    is_top: bool = False,
    is_flagged: bool = False,
) -> None:
    _render_html(_listing_card_html(item, rank=rank, is_top=is_top, is_flagged=is_flagged))


def render_negotiation(message: str) -> None:
    st.markdown('<div class="ph-section-title">Negotiation message</div>', unsafe_allow_html=True)
    safe = html.escape(message)
    st.markdown(f'<div class="ph-negotiation">{safe}</div>', unsafe_allow_html=True)
    st.text_area(
        "Copy and send to seller",
        value=message,
        height=100,
        label_visibility="collapsed",
        key=f"neg_{hash(message) % 10**8}",
    )


def _listing_key(item: Listing) -> tuple[str, int]:
    return (str(item.get("title", "")).lower(), int(item.get("price") or 0))


def render_results(data: ResultData) -> None:
    query = data.get("query", "")
    listings = data.get("listings") or []
    flagged = data.get("flagged") or []
    flagged_keys = {_listing_key(f) for f in flagged}

    title = html.escape(query)
    if data.get("query_corrected") and data.get("query_raw"):
        raw = html.escape(str(data["query_raw"]))
        title = f'{raw} &rarr; {html.escape(query)}'

    st.markdown(
        f'<div class="ph-section-title" style="margin-top:0;">Results for {title}</div>',
        unsafe_allow_html=True,
    )

    if not listings:
        st.warning(
            f"No listings found for **{query}** under ₱{int(data.get('budget', 0)):,}."
        )
        st.info(
            "Turn on **Demo listings** in the sidebar (live Carousell/OLX often block "
            "automated searches), or try a higher budget / broader search term."
        )
        return

    if data.get("used_demo_fallback"):
        st.info(
            "Live scraping returned nothing — showing **sample demo listings**. "
            "Enable **Live search (browser)** and run `playwright install chromium` if needed."
        )
    elif int(data.get("live_count") or 0) > 0:
        st.caption(
            f"**{data['live_count']} live listing(s)** from Carousell — links open real pages. "
            "First search may take ~10–15 seconds."
        )

    render_stats(data)

    top = listings[0]
    render_listing_card(top, rank=1, is_top=True)

    if len(listings) > 1:
        st.markdown('<div class="ph-section-title">Other listings</div>', unsafe_allow_html=True)
        for i, item in enumerate(listings[1:6], start=2):
            render_listing_card(
                item,
                rank=i,
                is_flagged=_listing_key(item) in flagged_keys
                or item.get("trust_score", 100) < 40
                or item.get("value_score", 100) < 35,
            )

    risky = [
        x
        for x in flagged
        if _listing_key(x) != _listing_key(top)
    ]
    if risky:
        st.markdown('<div class="ph-section-title">Flagged — use caution</div>', unsafe_allow_html=True)
        for item in risky[:4]:
            render_listing_card(item, is_flagged=True)

    neg = data.get("negotiation") or ""
    if neg:
        render_negotiation(neg)


def render_gemini_text(text: str) -> None:
    """Fallback when only markdown text is available from the agent."""
    st.markdown('<div class="ph-section-title">Agent response</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="ph-negotiation" style="white-space:pre-wrap;">{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )
