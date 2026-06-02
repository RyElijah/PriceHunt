"""Test full agent (tools) mode — tools, graph invoke, run_pricehunt."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()


def test_tools() -> bool:
    from agent import _tool_search_carousell, _tool_score_listing

    os.environ["PRICEHUNT_USE_PLAYWRIGHT"] = "1"
    os.environ["PRICEHUNT_FETCH_LOCATIONS"] = "0"
    os.environ["PRICEHUNT_SELLER_PROFILES"] = "0"

    print("=== Tool: search_carousell ===")
    raw = _tool_search_carousell("iphone 14", 50000)
    data = json.loads(raw)
    print("count", data.get("count"), "error", data.get("error"))
    listings = data.get("listings") or []
    if not listings:
        print("FAIL: no listings from tool")
        return False

    print("=== Tool: score_listing ===")
    sample = listings[0]
    scored = json.loads(_tool_score_listing(json.dumps(sample, ensure_ascii=False)))
    print("scores", scored.get("value_score"), scored.get("trust_score"))
    if "value_score" not in scored:
        print("FAIL: score_listing")
        return False
    return True


def test_agent_invoke() -> bool:
    from agent import has_gemini_api_key, run_agent

    if not has_gemini_api_key():
        print("SKIP agent invoke: no GOOGLE_API_KEY")
        return True

    print("=== run_agent (short prompt, may take 2-3 min) ===")
    prompt = (
        "User request: iPhone 14 under 50000 PHP\n"
        "Interpreted product: iphone 14\n"
        "Budget: 50000 PHP\n"
        "Search Carousell and OLX, score at least 2 listings, give brief TOP PICK."
    )
    text = run_agent(prompt, chat_history=[])
    print("response length", len(text))
    print("preview:", text[:500].replace("\n", " "))
    if len(text) < 100:
        print("FAIL: response too short")
        return False
    if "search_carousell" in text.lower() and "error" in text.lower():
        print("WARN: possible tool error in response")
    return True


def test_run_pricehunt_agent_mode() -> bool:
    from agent import has_gemini_api_key, run_pricehunt

    if not has_gemini_api_key():
        print("SKIP run_pricehunt agent: no key")
        return True

    os.environ["PRICEHUNT_FETCH_LOCATIONS"] = "0"
    os.environ["PRICEHUNT_SELLER_PROFILES"] = "0"

    print("=== run_pricehunt mode=agent ===")
    result = run_pricehunt(
        "iPhone 14",
        budget=50000,
        search_query="iphone 14",
        mode="agent",
    )
    data = result["data"]
    narrative = result["narrative"]
    print("mode", result.get("mode"))
    print("listings in data", len(data.get("listings") or []))
    print("narrative len", len(narrative))
    print("double scrape issue: pipeline ran + agent tools?")
    return bool(narrative) and len(narrative) > 50


if __name__ == "__main__":
    ok = test_tools()
    if ok:
        ok = test_run_pricehunt_agent_mode()
    sys.exit(0 if ok else 1)
