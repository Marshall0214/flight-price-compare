"""LangGraph 图的各节点实现，以及节点之间的条件路由函数。

每个节点函数：接收 AgentState，返回要合并进状态的增量 dict（LangGraph 的标准写法）。
表格对照见 docs/requirements.md 第 7 节：哪些节点用 LLM、哪些用普通代码。
"""
from __future__ import annotations

import time

from src.llm import chat_json, chat_text
from src.models import FlightOffer, FlightSearchRequest, PriceBreakdown
from src.pricing import calculate_breakdown, dedupe_offers, rank_and_tier, refresh_fare
from src.state import AgentState
from src.tools.airport_codes import resolve_airport_code
from src.tools.search_flights import search_offers

PARSE_SYSTEM_PROMPT = """你是一个机票需求解析器。请只输出一个 JSON 对象，字段如下：
origin, destination, departure_date(YYYY-MM-DD), trip_duration_days(int),
date_flexibility_days(int), checked_baggage_kg(int), avoid_red_eye(bool)。

重要规则：
1. 只提取“本轮用户消息”中新出现或用户明确想要修改的字段。
2. 本轮消息没有提到的字段，一律输出 null（包括数值型和布尔型字段，
   不要用 0 / false 之类的默认值去填充未提及的字段）。
3. 已知信息只是给你参考、避免重复提问，不需要在输出中重复它们的值，程序会自动合并。
4. 出发地、目的地完全没有提及时不允许猜测，保持 null。
5. 日期如果是模糊表达（如“上旬”表示 1-10 日、“中旬”表示 11-20 日、“下旬”表示 21-月末，
   或“月初/月中/月末”等类似说法），不要输出 null：把 departure_date 设为该区间的中间日期，
   并把 date_flexibility_days 设为能覆盖整个区间所需的天数（例如“上旬”约为中间日期 ±5 天）；
   如果用户同时另外说了具体的弹性天数，以用户明确说的天数为准。用户完全没提年份时默认使用 2026 年。
   只有在用户完全没有给出任何日期线索时，departure_date 才保持 null。
6. 只输出 JSON，不要输出任何解释性文字。"""


def _log_llm_call(state: AgentState, node: str, usage: dict, elapsed: float | None = None) -> dict:
    metrics = dict(state.get("metrics") or {})
    calls = list(metrics.get("llm_calls") or [])
    entry: dict = {"node": node, "usage": usage}
    if elapsed is not None:
        entry["elapsed_s"] = elapsed
    calls.append(entry)
    metrics["llm_calls"] = calls
    return metrics


def parse_input_node(state: AgentState) -> AgentState:
    known = state.get("request") or {}
    user_message = state["user_message"]

    t0 = time.perf_counter()
    parsed, usage = chat_json(PARSE_SYSTEM_PROMPT, f"已知信息: {known}\n本轮用户消息: {user_message}")
    elapsed = time.perf_counter() - t0

    merged = {**known, **{k: v for k, v in parsed.items() if v is not None}}
    request = FlightSearchRequest(**merged)

    return {
        "request": request.model_dump(),
        "missing_fields": request.missing_required_fields(),
        "metrics": _log_llm_call(state, "parse_input", usage, elapsed),
    }


def route_after_parse(state: AgentState) -> str:
    return "missing" if state.get("missing_fields") else "complete"


def ask_clarification_node(state: AgentState) -> AgentState:
    missing = state["missing_fields"]
    text, usage = chat_text(
        "你是一个友好的机票助手。请用一句中文追问用户缺失的信息，不要猜测具体值。",
        f"缺失字段: {missing}\n已知信息: {state.get('request')}",
    )
    return {
        "clarification_question": text,
        "final_text": text,
        "status": "clarification",
        "metrics": _log_llm_call(state, "ask_clarification", usage),
    }


def resolve_airport_code_node(state: AgentState) -> AgentState:
    request = state["request"]
    origin_res = resolve_airport_code(request.get("origin"))
    if origin_res.error:
        return {"airport_error": origin_res.error.model_dump()}

    dest_res = resolve_airport_code(request.get("destination"))
    if dest_res.error:
        return {"airport_error": dest_res.error.model_dump()}

    return {"origin_codes": origin_res.resolved, "destination_codes": dest_res.resolved}


def route_after_airport(state: AgentState) -> str:
    return "error" if state.get("airport_error") else "ok"


def search_flights_node(state: AgentState) -> AgentState:
    request = state["request"]
    offers = search_offers(
        state["origin_codes"],
        state["destination_codes"],
        request.get("departure_date"),
        request.get("date_flexibility_days") or 0,
    )
    # avoid_red_eye 是用户明确表达的硬约束（"不要红眼航班"），不是软偏好，
    # 所以在这里直接过滤掉，而不是留到 rank_and_tier 只做轻微降权。
    if request.get("avoid_red_eye"):
        offers = [o for o in offers if not o.is_red_eye]
    return {"raw_offers": [o.model_dump(mode="json") for o in offers]}


def route_after_search(state: AgentState) -> str:
    return "ok" if state.get("raw_offers") else "empty"


def explain_failure_node(state: AgentState) -> AgentState:
    reason = state.get("airport_error") or {
        "error_code": "NO_RESULTS",
        "message": "没有找到符合条件的航班",
    }
    text, usage = chat_text(
        "你是一个诚实的机票助手。请用一句中文清楚说明查询失败的原因，不要编造航班信息。",
        f"失败原因: {reason}",
    )
    return {
        "final_text": text,
        "status": "error",
        "search_error": reason,
        "metrics": _log_llm_call(state, "explain_failure", usage),
    }


def normalize_and_dedupe_node(state: AgentState) -> AgentState:
    offers = [FlightOffer(**o) for o in state["raw_offers"]]
    offers = dedupe_offers(offers)
    baggage_kg = state["request"].get("checked_baggage_kg") or 0

    priced = [
        {
            "offer": offer.model_dump(mode="json"),
            "breakdown": calculate_breakdown(offer, baggage_kg).model_dump(),
        }
        for offer in offers
    ]
    return {"priced_offers": priced}


def verify_fare_node(state: AgentState) -> AgentState:
    refreshed = []
    for item in state["priced_offers"]:
        offer = refresh_fare(FlightOffer(**item["offer"]))
        refreshed.append({"offer": offer.model_dump(mode="json"), "breakdown": item["breakdown"]})
    return {"priced_offers": refreshed}


def rank_and_tier_node(state: AgentState) -> AgentState:
    pairs = [
        (FlightOffer(**item["offer"]), PriceBreakdown(**item["breakdown"]))
        for item in state["priced_offers"]
    ]
    ranked = rank_and_tier(pairs)

    result = {}
    for tier, (offer, breakdown) in ranked.items():
        result[tier] = {
            "tier": tier,
            "flight_id": offer.flight_id,
            "total_price_cny": breakdown.total_cny,
            "breakdown": breakdown.model_dump(),
            "source": offer.source,
            "queried_at": offer.queried_at.isoformat(),
        }
    return {"ranked_results": result}


def generate_response_node(state: AgentState) -> AgentState:
    text, usage = chat_text(
        "你是一个机票助手。请用简短的中文总结下面的查询结果，并提醒用户每条结果的数据来源和查询时间。",
        f"结果: {state.get('ranked_results')}",
    )
    return {
        "final_text": text,
        "status": "results",
        "metrics": _log_llm_call(state, "generate_response", usage),
    }
