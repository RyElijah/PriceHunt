"""
PriceHunt LangChain agent — Gemini with Carousell / OLX / scorer tools.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from tools.intent import interpret_user_query
from tools.scorer import reset_market_context, score_listing
from tools.scraper import search_carousell, search_olx
from tools.suggestions import autocorrect_query

load_dotenv()
logger = logging.getLogger(__name__)

_session_listings: list[dict[str, Any]] = []

SYSTEM_PROMPT = """You are PriceHunt Agent — an AI shopping assistant for Filipino buyers on Carousell and OLX (Philippines).

You are NOT a dumb scraper. You reason like a smart friend helping someone buy safely second-hand.

CAPABILITIES YOU MUST USE:
1. Natural language — Users write Taglish/English ("ref medyo bago around 5k"). Infer product, budget (PHP), and condition/location preferences before searching.
2. Live data only — Call search_carousell AND search_olx with interpreted keywords and budget. Never invent listings.
3. Trust reasoning — After score_listing on EACH real listing, explain suspicious deals in plain language (e.g. iPhone far below market = likely scam), not just "low score".
4. Judgment — When prices are close, weigh seller reviews, title quality, location, and flags together for your top pick.
5. Negotiation — Write a short, polite, persuasive message for the top listing (10–15% below ask, ≤5 sentences).
6. Errors — If a platform returns [] or errors, say which failed and suggest fixes (higher budget, simpler keywords, try later). Do not crash silently.
7. Memory — Use chat_history to answer "is this better than before?" by comparing prior searches.

WORKFLOW (mandatory):
1. Parse the user's request (product, budget, preferences).
2. search_carousell(query, budget) then search_olx(query, budget).
3. score_listing(listing_json) once per listing — never skip.
4. Rank by value_score + trust_score. Flag trust<40 or value<35.
5. Respond in the format below.

Never fabricate URLs, prices, or sellers.

---
SEARCH RESULTS FOR: [product] | Budget: ₱[amount]
Sources checked: Carousell ✓/✗ | OLX ✓/✗
Total listings found: [N]
What I understood from your request: [1 sentence]
---

TOP PICK: (title, price, seller, location, value/trust scores, why you trust it, link, flags)
OTHER LISTINGS (ranked, brief trust/value notes):
FLAGGED LISTINGS (explain WHY each is risky):
NEGOTIATION MESSAGE FOR TOP PICK:
---
"""

SYNTHESIS_PROMPT = """You are PriceHunt Agent analyzing REAL scraped listings from Carousell/OLX Philippines.

The user asked (natural language):
{user_message}

Structured interpretation:
- Product search: {query}
- Budget: ₱{budget:,} PHP
- Preferences: {preferences}

Session memory (prior searches this chat):
{memory}

Live listings with scores (JSON — only use this data):
{listings_json}

Write a complete PriceHunt response:
1. What you understood from their words (Taglish/English OK).
2. Carousell/OLX status and how many listings.
3. TOP PICK with trust reasoning in plain language (why safe or risky).
4. Other ranked picks (brief).
5. FLAGGED items — explain scams/cheap traps like a human would.
6. Negotiation message for top pick.
7. If they asked to compare with a prior search, compare using memory.

Never invent listings not in the JSON. If JSON is empty, explain and suggest a higher budget or different keywords.
"""


class SearchInput(BaseModel):
    query: str = Field(description="Product search keywords, e.g. 'iPhone 13 128GB'")
    budget: int = Field(description="Maximum price in Philippine Pesos (PHP)")


class ListingInput(BaseModel):
    listing_json: str = Field(
        description="JSON string of one listing dict with title, price, location, seller_name, seller_reviews, url, image_url"
    )


def _track_listings(batch: list[dict[str, Any]]) -> None:
    global _session_listings
    seen = {L.get("url") for L in _session_listings if L.get("url")}
    for item in batch:
        url = item.get("url")
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        _session_listings.append(item)
    reset_market_context([int(L["price"]) for L in _session_listings if L.get("price")])


def _tool_search_carousell(query: str, budget: int) -> str:
    try:
        results = search_carousell(query, budget)
        _track_listings(results)
        return json.dumps(
            {"platform": "carousell", "count": len(results), "listings": results},
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.exception("search_carousell failed")
        return json.dumps({"error": str(exc), "platform": "carousell", "listings": []})


def _tool_search_olx(query: str, budget: int) -> str:
    try:
        results = search_olx(query, budget)
        _track_listings(results)
        return json.dumps(
            {"platform": "olx", "count": len(results), "listings": results},
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.exception("search_olx failed")
        return json.dumps({"error": str(exc), "platform": "olx", "listings": []})


def _tool_score_listing(listing_json: str) -> str:
    try:
        listing = json.loads(listing_json)
        if not isinstance(listing, dict):
            return json.dumps({"error": "listing_json must be a JSON object"})
        result = score_listing(listing)
        return json.dumps({**result, "title": listing.get("title")}, ensure_ascii=False)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"invalid JSON: {exc}"})
    except Exception as exc:
        logger.exception("score_listing failed")
        return json.dumps({"error": str(exc)})


def build_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            func=_tool_search_carousell,
            name="search_carousell",
            description="Search Carousell Philippines. Returns JSON array of listings within budget.",
            args_schema=SearchInput,
        ),
        StructuredTool.from_function(
            func=_tool_search_olx,
            name="search_olx",
            description="Search OLX Philippines (legacy; may redirect to Carousell). Returns JSON array of listings.",
            args_schema=SearchInput,
        ),
        StructuredTool.from_function(
            func=_tool_score_listing,
            name="score_listing",
            description="Score one listing. Pass the full listing as listing_json (JSON string). Returns value_score, trust_score, flags, recommendation.",
            args_schema=ListingInput,
        ),
    ]


DEFAULT_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]


def _gemini_models_to_try() -> list[str]:
    """Models to try in order (comma-separated GEMINI_MODEL overrides default list)."""
    custom = os.getenv("GEMINI_MODEL", "").strip()
    if custom and "," in custom:
        primary = [m.strip() for m in custom.split(",") if m.strip()]
    elif custom:
        primary = [custom]
    else:
        primary = []

    ordered: list[str] = []
    for name in primary + DEFAULT_GEMINI_MODELS:
        if name and name not in ordered:
            ordered.append(name)
    return ordered


def is_gemini_quota_error(exc: BaseException) -> bool:
    text = str(exc).upper()
    return "429" in text or "RESOURCE_EXHAUSTED" in text or "QUOTA" in text


def is_gemini_model_error(exc: BaseException) -> bool:
    text = str(exc).upper()
    if is_gemini_quota_error(exc):
        return False
    return "NOT_FOUND" in text or ("404" in text and "MODEL" in text)


def has_gemini_api_key() -> bool:
    return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))


def build_memory_summary(history: list | None) -> str:
    if not history:
        return "No prior searches in this session."
    lines: list[str] = []
    for msg in history[-6:]:
        role = getattr(msg, "type", "") or msg.__class__.__name__
        content = str(getattr(msg, "content", msg))[:400]
        lines.append(f"- {role}: {content}")
    return "\n".join(lines)


def _get_llm(model_name: str | None = None) -> ChatGoogleGenerativeAI:
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Set GOOGLE_API_KEY in .env")
    name = model_name or _gemini_models_to_try()[0]
    return ChatGoogleGenerativeAI(
        model=name,
        google_api_key=api_key,
        temperature=0.35,
    )


def synthesize_with_gemini(
    user_message: str,
    data: dict[str, Any],
    chat_history: list | None = None,
) -> str:
    """AI analysis layer over live scraped + scored listings."""
    listings = data.get("listings") or []
    prompt = SYNTHESIS_PROMPT.format(
        user_message=user_message,
        query=data.get("query", ""),
        budget=int(data.get("budget", 0)),
        preferences=data.get("preferences") or "none",
        memory=build_memory_summary(chat_history),
        listings_json=json.dumps(listings[:20], ensure_ascii=False, indent=2),
    )
    last_error: BaseException | None = None
    for model_name in _gemini_models_to_try():
        try:
            llm = _get_llm(model_name)
            response = llm.invoke(
                [
                    HumanMessage(content=prompt),
                ]
            )
            return str(response.content)
        except Exception as exc:
            last_error = exc
            if is_gemini_quota_error(exc) or is_gemini_model_error(exc):
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError("Gemini synthesis failed")


def create_pricehunt_agent(model_name: str | None = None):
    if not has_gemini_api_key():
        raise ValueError(
            "Set GOOGLE_API_KEY or GEMINI_API_KEY in your environment or .env file."
        )

    llm = _get_llm(model_name)

    return create_agent(
        model=llm,
        tools=build_tools(),
        system_prompt=SYSTEM_PROMPT,
        debug=os.getenv("PRICEHUNT_VERBOSE", "").lower() in ("1", "true"),
    )


def _extract_agent_text(result: dict[str, Any]) -> str:
    messages = result.get("messages") or []
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)
    return str(result)


def run_deterministic_pipeline(
    query: str, budget: int, *, autocorrect: bool = True
) -> dict[str, Any]:
    """
    Run search → score → rank without the LLM (faster, no API cost).
    Used by Streamlit when the user wants instant results.
    """
    query_raw = query
    query_corrected = False
    if autocorrect:
        corrected, was_corrected, _ = autocorrect_query(query)
        query = corrected
        query_corrected = was_corrected

    carousell_ok = True
    olx_ok = True
    all_listings: list[dict[str, Any]] = []

    def _merge(batch: list[dict[str, Any]]) -> None:
        seen = {L.get("url") for L in all_listings if L.get("url")}
        for item in batch:
            url = item.get("url")
            if url and url in seen:
                continue
            if url:
                seen.add(url)
            all_listings.append(item)

    use_playwright = os.getenv("PRICEHUNT_USE_PLAYWRIGHT", "1").strip() not in (
        "0",
        "false",
        "no",
    )
    live_batch: list[dict[str, Any]] = []

    if use_playwright:
        try:
            from tools.live_search import fetch_live_listings_for_pipeline
            from tools.scraper import MAX_LISTINGS, _filter_by_budget

            live_batch = fetch_live_listings_for_pipeline(query, max_items=MAX_LISTINGS)
            live_batch = _filter_by_budget(live_batch, budget)
            _merge(live_batch)
            carousell_ok = any(L.get("source") == "carousell" for L in live_batch)
            olx_ok = any(L.get("source") == "olx" for L in live_batch)
        except Exception:
            carousell_ok = False
            olx_ok = False
            logger.exception("Live marketplace search failed")

    if not live_batch:
        try:
            _merge(search_carousell(query, budget))
            carousell_ok = True
        except Exception:
            carousell_ok = False
            logger.exception("Carousell search failed")

        try:
            _merge(search_olx(query, budget))
            olx_ok = True
        except Exception:
            olx_ok = False
            logger.exception("OLX search failed")

    reset_market_context([L["price"] for L in all_listings])

    scored: list[dict[str, Any]] = []
    for listing in all_listings:
        try:
            scores = score_listing(listing)
        except Exception:
            logger.exception("Skipping listing due to score error: %s", listing.get("title"))
            continue
        scored.append({**listing, **scores, "combined": scores["value_score"] + scores["trust_score"]})

    scored.sort(key=lambda x: x["combined"], reverse=True)

    flagged = [
        s
        for s in scored
        if s["trust_score"] < 40 or s["value_score"] < 35
    ]

    top = scored[0] if scored else None
    negotiation = ""
    if top:
        offer = int(top["price"] * 0.88)
        negotiation = (
            f"Hi! I'm interested in your listing \"{top['title']}\" listed at ₱{top['price']:,}. "
            f"Would you consider ₱{offer:,}? I can meet up this week and pay cash. "
            f"Thanks!"
        )

    live_count = len(scored)

    return {
        "query": query,
        "query_raw": query_raw,
        "query_corrected": query_corrected,
        "budget": budget,
        "carousell_ok": carousell_ok,
        "olx_ok": olx_ok,
        "listings": scored,
        "flagged": flagged,
        "top": top,
        "negotiation": negotiation,
        "live_count": live_count,
    }


def _format_seller_line(item: dict[str, Any]) -> str:
    name = item.get("seller_name") or "Unknown"
    reviews = int(item.get("seller_reviews") or 0)
    rating = item.get("seller_rating")
    if rating is not None:
        try:
            return f"{name} ({float(rating):.1f}/5, {reviews} reviews)"
        except (TypeError, ValueError):
            pass
    return f"{name} ({reviews} reviews)"


def format_pipeline_response(data: dict[str, Any]) -> str:
    query = data["query"]
    budget = data["budget"]
    listings = data["listings"]
    flagged = data["flagged"]
    top = data["top"]
    carousell = "✓" if data["carousell_ok"] else "✗"
    olx = "✓" if data["olx_ok"] else "✗"

    if not listings:
        return (
            f"I could not find any listings for {query} under ₱{budget:,} "
            f"on Carousell or OLX right now. Try a higher budget or a broader search term."
        )

    def block(item: dict[str, Any], rank: str) -> str:
        flags = item.get("flags") or []
        flag_text = "\n".join(f"⚠️ {f}" for f in flags) if flags else ""
        return (
            f"{rank}\n"
            f"Title: {item['title']}\n"
            f"Price: ₱{item['price']:,}\n"
            f"Seller: {_format_seller_line(item)}\n"
            f"Location: {item['location']}\n"
            f"Value score: {item['value_score']}/100 | Trust score: {item['trust_score']}/100\n"
            f"Link: {item['url']}\n"
            f"{flag_text}"
        ).strip()

    lines = [
        "---",
        f"SEARCH RESULTS FOR: {query} | Budget: ₱{budget:,}",
        f"Sources checked: Carousell {carousell} | OLX {olx}",
        f"Total listings found: {len(listings)}",
        "---",
        "",
        "TOP PICK:",
        block(top, "") if top else "None",
        "",
        "OTHER LISTINGS (ranked):",
    ]
    for item in listings[1:4]:
        lines.append(block(item, ""))
        lines.append("")

    lines.append("FLAGGED LISTINGS (do not recommend):")
    if flagged:
        for item in flagged:
            reason = []
            if item["trust_score"] < 40:
                reason.append(f"trust {item['trust_score']}")
            if item["value_score"] < 35:
                reason.append(f"value {item['value_score']}")
            lines.append(f"- {item['title']} — {', '.join(reason)}")
    else:
        lines.append("No suspicious listings detected.")

    lines.extend(
        [
            "",
            "NEGOTIATION MESSAGE FOR TOP PICK:",
            data.get("negotiation") or "",
            "---",
        ]
    )
    return "\n".join(lines)


def _build_data_from_session_listings(
    query: str,
    budget: int,
    *,
    query_raw: str = "",
    query_corrected: bool = False,
    preferences: str = "",
    user_message: str = "",
    interpreted: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build pipeline-shaped result dict from listings collected by agent tools."""
    global _session_listings
    listings_batch = list(_session_listings)
    reset_market_context([int(L["price"]) for L in listings_batch if L.get("price")])

    scored: list[dict[str, Any]] = []
    for listing in listings_batch:
        try:
            scores = score_listing(listing)
        except Exception:
            logger.exception("Skipping listing due to score error: %s", listing.get("title"))
            continue
        scored.append(
            {**listing, **scores, "combined": scores["value_score"] + scores["trust_score"]}
        )

    scored.sort(key=lambda x: x["combined"], reverse=True)
    flagged = [s for s in scored if s["trust_score"] < 40 or s["value_score"] < 35]
    top = scored[0] if scored else None
    negotiation = ""
    if top:
        offer = int(top["price"] * 0.88)
        negotiation = (
            f"Hi! I'm interested in your listing \"{top['title']}\" listed at ₱{top['price']:,}. "
            f"Would you consider ₱{offer:,}? I can meet up this week and pay cash. "
            f"Thanks!"
        )

    return {
        "query": query,
        "query_raw": query_raw or query,
        "query_corrected": query_corrected,
        "budget": budget,
        "carousell_ok": any(L.get("source") == "carousell" for L in scored),
        "olx_ok": any(L.get("source") == "olx" for L in scored),
        "listings": scored,
        "flagged": flagged,
        "top": top,
        "negotiation": negotiation,
        "live_count": len(scored),
        "preferences": preferences,
        "user_message": user_message,
        "interpreted": interpreted or {},
    }


def run_agent(user_input: str, chat_history: list | None = None) -> str:
    """Run the LangChain + Gemini ReAct agent (tool-calling). Tries fallback models on errors."""
    global _session_listings
    _session_listings = []

    messages: list = list(chat_history or [])
    messages.append(HumanMessage(content=user_input))
    last_error: BaseException | None = None

    for model_name in _gemini_models_to_try():
        try:
            graph = create_pricehunt_agent(model_name)
            result = graph.invoke({"messages": messages})
            return _extract_agent_text(result)
        except Exception as exc:
            last_error = exc
            if is_gemini_quota_error(exc) or is_gemini_model_error(exc):
                logger.warning(
                    "Gemini model %s unavailable (%s), trying next…", model_name, exc
                )
                continue
            raise

    if last_error:
        raise last_error
    raise RuntimeError("No Gemini model available")


def run_pricehunt(
    user_message: str,
    *,
    budget: int = 25000,
    search_query: str | None = None,
    chat_history: list | None = None,
    mode: str = "hybrid",
) -> dict[str, Any]:
    """
    Full PriceHunt flow: interpret NL → live Carousell+OLX → score → Gemini analysis.

    mode:
      - hybrid (default): live scrape + Gemini synthesis (reliable data + AI reasoning)
      - agent: Gemini ReAct tool-calling only
    """
    intent = interpret_user_query(user_message, default_budget=budget)
    query = str(search_query or intent["query"] or user_message).strip()
    search_budget = int(intent["budget"] or budget)
    preferences = str(intent.get("preferences") or "")

    query_for_search = query
    agent_mode = mode == "agent"
    narrative = ""
    data: dict[str, Any]

    if agent_mode:
        global _session_listings
        _session_listings = []

    if agent_mode and has_gemini_api_key():
        agent_prompt = (
            f"User request: {user_message}\n"
            f"Interpreted product keywords for search: {query_for_search}\n"
            f"Budget: ₱{search_budget:,} PHP\n"
            f"Preferences: {preferences or 'none'}\n\n"
            "Required steps:\n"
            f"1. Call search_carousell(query={query_for_search!r}, budget={search_budget})\n"
            f"2. Call search_olx(query={query_for_search!r}, budget={search_budget})\n"
            "3. Call score_listing(listing_json=...) for each listing you will recommend "
            "(at least the top 5 by price/trust).\n"
            "4. Respond with TOP PICK, other listings, flagged items, and negotiation message.\n"
            "Use only data returned from tools. Do not invent listings."
        )
        try:
            narrative = run_agent(agent_prompt, chat_history)
            data = _build_data_from_session_listings(
                query_for_search,
                search_budget,
                preferences=preferences,
                user_message=user_message,
                interpreted=intent,
            )
            if not data.get("listings"):
                logger.warning("Agent tools returned no listings; running hybrid pipeline")
                data = run_deterministic_pipeline(
                    query_for_search, search_budget, autocorrect=False
                )
                data["preferences"] = preferences
                data["user_message"] = user_message
                data["interpreted"] = intent
        except Exception as exc:
            logger.exception("Agent mode failed — falling back to hybrid pipeline")
            data = run_deterministic_pipeline(query_for_search, search_budget, autocorrect=False)
            data["preferences"] = preferences
            data["user_message"] = user_message
            data["interpreted"] = intent
            data["gemini_error"] = str(exc)
            try:
                narrative = synthesize_with_gemini(user_message, data, chat_history)
                narrative = (
                    f"**Note:** Full agent mode failed ({exc}). "
                    f"Showing hybrid analysis instead.\n\n{narrative}"
                )
            except Exception as exc2:
                narrative = format_pipeline_response(data)
                narrative = (
                    f"**AI note:** Agent and Gemini unavailable.\n\n{narrative}"
                )
                data["gemini_error"] = str(exc2)
    elif agent_mode:
        data = run_deterministic_pipeline(query_for_search, search_budget, autocorrect=False)
        data["preferences"] = preferences
        data["user_message"] = user_message
        data["interpreted"] = intent
        narrative = format_pipeline_response(data)
        data["gemini_error"] = "No GOOGLE_API_KEY in .env"
    else:
        data = run_deterministic_pipeline(query_for_search, search_budget, autocorrect=False)
        data["preferences"] = preferences
        data["user_message"] = user_message
        data["interpreted"] = intent

        if has_gemini_api_key():
            try:
                narrative = synthesize_with_gemini(user_message, data, chat_history)
            except Exception as exc:
                logger.exception("Gemini layer failed")
                data["gemini_error"] = str(exc)
                narrative = format_pipeline_response(data)
                narrative = (
                    f"**AI note:** Gemini unavailable ({exc}). "
                    f"Showing live scrape results below.\n\n{narrative}"
                )
        else:
            narrative = format_pipeline_response(data)
            data["gemini_error"] = "No GOOGLE_API_KEY in .env"

    return {
        "data": data,
        "narrative": narrative,
        "mode": "agent" if agent_mode else "hybrid",
    }
