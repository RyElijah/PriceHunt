"""
PriceHunt — Streamlit UI: live Carousell/OLX + Gemini AI agent.
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage

from agent import (
    has_gemini_api_key,
    is_gemini_model_error,
    is_gemini_quota_error,
    run_pricehunt,
)
from tools.intent import interpret_user_query
from tools.suggestions import cached_suggestions, fetch_carousell_top_searches
from ui.components import (
    render_empty_state,
    render_gemini_text,
    render_hero,
    render_results,
    render_sidebar_brand,
)
from ui.theme import inject_theme

load_dotenv()

st.set_page_config(
    page_title="PriceHunt — Preloved deals PH",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()


@st.cache_data(ttl=3600, show_spinner=False)
def _load_carousell_terms() -> tuple[str, ...]:
    return tuple(fetch_carousell_top_searches())


_load_carousell_terms()

if "memory" not in st.session_state:
    st.session_state.memory = []

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "last_result" not in st.session_state:
    st.session_state.last_result = None

if "product_query" not in st.session_state:
    st.session_state.product_query = ""


def _queue_product(text: str) -> None:
    st.session_state.pending_product = text


def _apply_pending_product() -> None:
    pending = st.session_state.pop("pending_product", None)
    if pending is not None:
        st.session_state.product_query = pending


def remember_search(query: str, budget: int, top: dict | None, narrative: str = "") -> None:
    st.session_state.memory.append(
        {
            "query": query,
            "budget": budget,
            "top": top,
            "summary": narrative[:500] if narrative else "",
        }
    )


def _has_api_key() -> bool:
    return has_gemini_api_key()


with st.sidebar:
    render_sidebar_brand()

    st.markdown("##### AI & search")
    api_ok = _has_api_key()
    if api_ok:
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        st.success("Gemini API key detected")
        st.caption(f"Model: `{model}` (fallback: gemini-flash-latest)")
    else:
        st.warning("No Gemini key — live listings still work; AI analysis disabled")

    ai_mode = st.radio(
        "AI mode",
        options=["hybrid", "agent"],
        format_func=lambda x: (
            "Hybrid (live scrape + AI analysis)" if x == "hybrid" else "Full agent (tools)"
        ),
        index=0,
        help="Hybrid is more reliable. Full agent lets Gemini call search/score tools directly.",
    )

    live_mode = st.toggle(
        "Live search (browser)",
        value=True,
        help="Playwright loads real Carousell/OLX listings.",
    )
    os.environ["PRICEHUNT_USE_PLAYWRIGHT"] = "1" if live_mode else "0"

    fetch_locations = st.toggle(
        "Meet-up locations",
        value=True,
        help="Opens each listing page for the seller's meet-up places (~10–20s).",
    )
    os.environ["PRICEHUNT_FETCH_LOCATIONS"] = "1" if fetch_locations else "0"

    seller_profiles = st.toggle(
        "Seller ratings (slower)",
        value=False,
        help="Visits seller profiles for star ratings. Adds ~15–25s.",
    )
    os.environ["PRICEHUNT_SELLER_PROFILES"] = "1" if seller_profiles else "0"

    if live_mode:
        st.caption("Carousell + OLX via live browser")

    st.divider()
    st.markdown("##### Session memory")
    if st.session_state.memory:
        for entry in reversed(st.session_state.memory[-5:]):
            top = entry.get("top") or {}
            st.markdown(
                f"""
                <div class="ph-history-item">
                    <div class="ph-history-query">{entry["query"]}</div>
                    <div class="ph-history-meta">≤ ₱{entry["budget"]:,} · {(top.get("title") or "—")[:40]}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.caption("AI remembers prior searches this session.")

    st.divider()
    st.caption("PriceHunt · Carousell + OLX Philippines")

render_hero()

_apply_pending_product()

st.markdown('<div class="ph-search-panel">', unsafe_allow_html=True)

user_request = st.text_area(
    "Tell PriceHunt what you need (English or Taglish)",
    placeholder='e.g. "ref medyo bago around 5k" or "iPhone 14 good condition under 30k"',
    height=88,
    key="user_request",
)

col1, col2, col3 = st.columns([2, 1.2, 1])
with col1:
    product = st.text_input(
        "Or type product keywords",
        key="product_query",
        placeholder="iPhone 14, refrigerator, MacBook Air M1…",
    )
    typed = (product or user_request or "").strip()
    suggestions = list(cached_suggestions(typed)) if typed else list(cached_suggestions(""))
    if suggestions and typed:
        st.caption("Carousell suggestions:")
        sug_cols = st.columns(min(4, len(suggestions[:4])))
        for col, term in zip(sug_cols, suggestions[:4]):
            with col:
                if st.button(term, key=f"sug_{term}", use_container_width=True):
                    _queue_product(term)
                    st.rerun()

with col2:
    budget = st.number_input(
        "Max budget (₱)",
        min_value=500,
        value=50000,
        step=500,
        help="iPhones and laptops often cost more than ₱25k — raise if you see no results.",
    )

with col3:
    st.markdown("<div style='height:1.6rem'></div>", unsafe_allow_html=True)
    search_clicked = st.button("Search", type="primary", use_container_width=True)
    st.caption("Live Carousell & OLX + AI analysis")

st.markdown("</div>", unsafe_allow_html=True)

if search_clicked:
    product_kw = (product or "").strip()
    combined = (user_request or product_kw or "").strip()

    if not combined:
        st.warning("Describe what you want or enter a product name.")
    else:
        intent = interpret_user_query(combined, default_budget=int(budget))
        query_for_search = (product_kw or str(intent["query"]) or combined).strip()
        search_budget = int(intent["budget"] or budget)

        if seller_profiles and fetch_locations:
            est = "25–50s"
        elif seller_profiles or fetch_locations:
            est = "15–35s"
        else:
            est = "8–20s"
        spinner_msg = (
            f"Searching Carousell & OLX for **{query_for_search}** ({est}), "
            + ("then AI analysis…" if api_ok else "please wait…")
        )
        with st.spinner(spinner_msg):
            try:
                result = run_pricehunt(
                    combined,
                    budget=search_budget,
                    search_query=product_kw or None,
                    chat_history=st.session_state.chat_history,
                    mode=ai_mode,
                )
                data = result["data"]
                narrative = result["narrative"]

                if api_ok:
                    st.session_state.chat_history.append(HumanMessage(content=combined))
                    st.session_state.chat_history.append(AIMessage(content=narrative[:8000]))

                st.session_state.last_result = {
                    "data": data,
                    "narrative": narrative,
                    "query": data.get("query"),
                    "budget": data.get("budget"),
                }
                remember_search(
                    str(data.get("query", query_for_search)),
                    int(data.get("budget", search_budget)),
                    data.get("top"),
                    narrative,
                )

                interp = data.get("interpreted") or intent
                if interp.get("query") and interp.get("raw") != interp.get("query"):
                    st.info(
                        f"Searching: **{query_for_search}** · budget **₱{search_budget:,}**"
                        + (f" · {interp.get('preferences')}" if interp.get("preferences") else "")
                    )

                if not api_ok:
                    st.info(
                        "Live listings loaded. Add `GOOGLE_API_KEY` to `.env` and restart "
                        "Streamlit to enable **AI analysis** above the results."
                    )
                elif data.get("gemini_error"):
                    st.warning(
                        f"AI analysis unavailable ({data['gemini_error']}). "
                        "Live listings are shown below."
                    )

                over = sum(1 for L in data.get("listings") or [] if L.get("over_budget"))
                if over:
                    st.warning(
                        f"{over} listing(s) are slightly above your ₱{search_budget:,} budget "
                        "but shown so you still see real market prices."
                    )
                if not data.get("listings"):
                    st.warning(
                        "No live listings returned. Keep **Live search** on, try a higher budget, "
                        "or run: `py -m playwright install chromium`"
                    )
            except Exception as exc:
                st.error(f"Search failed: {exc}")
                if is_gemini_quota_error(exc):
                    st.info(
                        "Set `GEMINI_MODEL=gemini-2.5-flash` in `.env` and restart Streamlit."
                    )
                elif is_gemini_model_error(exc):
                    st.info("Set `GEMINI_MODEL=gemini-2.5-flash` in `.env` and restart.")

if st.session_state.last_result:
    result = st.session_state.last_result
    data = result.get("data")

    if data:
        if result.get("narrative"):
            st.markdown("### AI analysis")
            render_gemini_text(result["narrative"])

        st.markdown("### Live listings from Carousell & OLX")
        render_results(data)
        if data.get("listings"):
            with st.expander("Developer · raw JSON"):
                st.json(data["listings"])
else:
    render_empty_state()

with st.expander("Ask about earlier searches (AI memory)"):
    follow_up = st.text_input(
        "Follow-up question",
        placeholder='e.g. "Is this better than what I searched before?"',
        key="follow_up",
    )
    if st.button("Ask PriceHunt", use_container_width=True):
        if not follow_up.strip():
            st.warning("Enter a question.")
        elif not api_ok:
            st.error("Gemini API key required.")
        else:
            with st.spinner("Thinking…"):
                try:
                    answer = run_pricehunt(
                        follow_up,
                        budget=int(budget),
                        chat_history=st.session_state.chat_history,
                        mode="hybrid",
                    )
                    render_gemini_text(answer["narrative"])
                except Exception as exc:
                    st.error(str(exc))
