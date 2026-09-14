"""LangGraph 图的各节点实现，以及节点之间的条件路由函数。

每个节点函数：接收 AgentState，返回要合并进状态的增量 dict（LangGraph 的标准写法）。
表格对照见 docs/requirements.md 第 7 节：哪些节点用 LLM、哪些用普通代码。
"""
from __future__ import annotations

import time
from datetime import date, timedelta

from src.llm import chat_json, chat_text
from src.models import FlightOffer, FlightSearchRequest, PriceBreakdown
from src.pricing import calculate_breakdown, dedupe_offers, rank_and_tier, refresh_fare
from src.state import AgentState
from src.tools.airport_codes import resolve_airport_code
from src.tools.search_flights import search_offers

PARSE_SYSTEM_PROMPT = """你是一个机票需求解析器。请只输出一个 JSON 对象，字段如下：
origin, destination, departure_date(YYYY-MM-DD), trip_duration_days(int),
date_flexibility_days(int), checked_baggage_kg(int), avoid_red_eye(bool),
priority_profile(PRICE_FIRST 或 COMFORT_FIRST 或 BALANCED)。

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
   注意：只要用户提到了任何关于日期弹性/浮动范围的说法（哪怕是"必须是那天，不能有任何浮动"这种
   明确表示零弹性的说法），就必须输出一个具体的 date_flexibility_days 数字（没有浮动就输出 0），
   不能因为数值是 0 就当作"没提到"输出 null——这两者对系统后续行为是不一样的。
6. 如果用户提到了往返/回程，并且明确说了返程日期（例如“9月10日去，9月15日回”），
   把 trip_duration_days 设为“返程日期 - 出发日期”的天数（此例中是 5）；
   如果用户直接说了行程天数（例如“玩5天”），直接使用该数字。
   如果用户没有提到往返或行程天数，trip_duration_days 保持 null（表示单程查询）。
   **注意区分 trip_duration_days 和 date_flexibility_days，这是两个完全不同的概念，
   很容易搞混**：trip_duration_days 是"在目的地玩几天/几号回来"，代表要不要查往返；
   date_flexibility_days 是"出发日期本身可以前后浮动几天"，跟要玩几天没有关系。
   比如"大概一周弹性"、"前后一周都可以"说的是出发日期能浮动一周，应该填
   date_flexibility_days=7，绝对不能填成 trip_duration_days=7（那会被误当成往返查询）；
   而"玩一周"、"待一周再回来"说的才是行程天数，应该填 trip_duration_days=7。
7. 根据用户对价格/舒适度的表达倾向判断 priority_profile：明显更看重便宜（比如"越便宜越好"）
   输出 PRICE_FIRST；明显愿意多花钱换舒适（比如"贵一点没关系，别让我太折腾"）输出 COMFORT_FIRST；
   没有表达出明显倾向、或者两者都提到时输出 null（保留默认的 BALANCED，不要强行归类）。
8. 如果本轮用户消息前面带有"[系统提示]"开头的说明，那是程序告诉你上一轮系统问了用户什么、
   该如何解读用户这句回复，请按说明来判断相应字段，不要把这句系统提示当成用户自己说的话。
9. 只输出 JSON，不要输出任何解释性文字。"""


def _log_llm_call(state: AgentState, node: str, usage: dict, elapsed: float | None = None) -> dict:
    metrics = dict(state.get("metrics") or {})
    calls = list(metrics.get("llm_calls") or [])
    entry: dict = {"node": node, "usage": usage}
    if elapsed is not None:
        entry["elapsed_s"] = elapsed
    calls.append(entry)
    metrics["llm_calls"] = calls
    return metrics


def _pending_confirmation_prompt(pending: dict | None) -> str:
    if not pending:
        return ""
    if pending.get("type") == "redeye":
        return (
            "\n[系统提示] 上一轮系统问了用户：完全没有不红眼的航班，是否愿意接受红眼航班？"
            "如果本轮用户消息是同意（比如'好的/可以/没关系/要/都行'），请把 avoid_red_eye 输出为 false；"
            "如果是拒绝（比如'不用了/算了/不要'），avoid_red_eye 保持 null（不要输出这个字段，维持原值）。"
        )
    return ""


def parse_input_node(state: AgentState) -> AgentState:
    known = state.get("request") or {}
    user_message = state["user_message"]
    pending_note = _pending_confirmation_prompt(state.get("pending_confirmation"))

    t0 = time.perf_counter()
    parsed, usage = chat_json(
        PARSE_SYSTEM_PROMPT, f"已知信息: {known}\n本轮用户消息: {user_message}{pending_note}"
    )
    elapsed = time.perf_counter() - t0

    merged = {**known, **{k: v for k, v in parsed.items() if v is not None}}
    if parsed.get("date_flexibility_days") is not None:
        merged["date_flexibility_explicit"] = True

    pending = state.get("pending_confirmation")
    if pending and pending.get("type") == "redeye":
        # 代码根据"问过什么 + 用户回复后 avoid_red_eye 变成了什么"来判断用户是同意还是拒绝，
        # 不需要再让 LLM 多输出一个字段——同意时 avoid_red_eye 被改成了 false；
        # 拒绝时 avoid_red_eye 维持不变（仍是 true）。拒绝就记下来，避免下一轮又问一遍。
        merged["redeye_confirmation_declined"] = bool(merged.get("avoid_red_eye"))

    request = FlightSearchRequest(**merged)

    return {
        "request": request.model_dump(),
        "missing_fields": request.missing_required_fields(),
        "pending_confirmation": None,  # 本轮已经用掉了，不管有没有用上都要清空，避免影响下一轮
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


def _is_round_trip(request: dict) -> bool:
    """trip_duration_days 有值就代表用户想要往返（配合 departure_date 推出返程日期）；
    单程查询里这个字段应该是 null（见 PARSE_SYSTEM_PROMPT 规则 6）。"""
    return bool(request.get("trip_duration_days"))


# 用户从没提过弹性天数时，允许 Agent 自主往前后多看几天再重试一次的幅度。
# 这是一条写死的规则（参考真实 CRAG 实现：要不要重试通常也是规则/阈值判断，
# 不是让 LLM 去决定控制流），LLM 在这里不参与决策，只负责后面把这件事如实告诉用户。
AUTO_RELAX_WINDOW_DAYS = 3


def _search_leg_with_relaxation(
    origin_codes: list[str],
    destination_codes: list[str],
    departure_date: str | None,
    stated_flex: int,
    flex_explicit: bool,
    avoid_red_eye: bool,
) -> dict:
    """搜索单程一段航班，按需自动放宽日期窗口，并判断红眼限制是不是唯一的阻碍。

    返回 {"offers": [...], "relaxation_note": dict|None, "redeye_blocking": bool}。
    - 用户从没明确说过弹性天数时，查不到就自动放宽 AUTO_RELAX_WINDOW_DAYS 天再试一次。
    - 用户明确说过弹性天数（哪怕是 0）时，不允许自动超出这个范围，查不到就是真的查不到。
    - 放宽后依然没有，且用户要求了 avoid_red_eye，就用同样的日期窗口再看一次不过滤红眼的结果，
      判断"是不是只要肯坐红眼就有航班"，供上层决定要不要转去问用户。
    """

    def _filtered(offers, filter_red_eye: bool):
        if filter_red_eye:
            return [o for o in offers if not o.is_red_eye]
        return offers

    primary = _filtered(
        search_offers(origin_codes, destination_codes, departure_date, stated_flex), avoid_red_eye
    )
    if primary:
        return {"offers": primary, "relaxation_note": None, "redeye_blocking": False}

    used_flex = stated_flex
    widened_offers: list = []
    if not flex_explicit:
        used_flex = stated_flex + AUTO_RELAX_WINDOW_DAYS
        widened_offers = _filtered(
            search_offers(origin_codes, destination_codes, departure_date, used_flex), avoid_red_eye
        )

    if widened_offers:
        return {
            "offers": widened_offers,
            "relaxation_note": {"from_days": stated_flex, "to_days": used_flex},
            "redeye_blocking": False,
        }

    redeye_blocking = False
    if avoid_red_eye:
        probe = search_offers(origin_codes, destination_codes, departure_date, used_flex)
        redeye_blocking = bool(probe)

    return {"offers": [], "relaxation_note": None, "redeye_blocking": redeye_blocking}


def search_flights_node(state: AgentState) -> AgentState:
    request = state["request"]
    stated_flex = request.get("date_flexibility_days") or 0
    flex_explicit = bool(request.get("date_flexibility_explicit"))
    avoid_red_eye = bool(request.get("avoid_red_eye"))

    outbound = _search_leg_with_relaxation(
        state["origin_codes"], state["destination_codes"], request.get("departure_date"),
        stated_flex, flex_explicit, avoid_red_eye,
    )
    relaxation_notes = []
    if outbound["relaxation_note"]:
        relaxation_notes.append({**outbound["relaxation_note"], "leg": "outbound"})
    redeye_blocking = outbound["redeye_blocking"]

    return_offers: list = []
    if _is_round_trip(request) and request.get("departure_date"):
        return_date = (
            date.fromisoformat(request["departure_date"]) + timedelta(days=request["trip_duration_days"])
        ).isoformat()
        ret = _search_leg_with_relaxation(
            state["destination_codes"], state["origin_codes"], return_date,
            stated_flex, flex_explicit, avoid_red_eye,
        )
        return_offers = ret["offers"]
        if ret["relaxation_note"]:
            relaxation_notes.append({**ret["relaxation_note"], "leg": "return"})
        redeye_blocking = redeye_blocking or ret["redeye_blocking"]

    return {
        "raw_offers": [o.model_dump(mode="json") for o in outbound["offers"]],
        "raw_return_offers": [o.model_dump(mode="json") for o in return_offers],
        "relaxation_notes": relaxation_notes,
        "redeye_blocking": redeye_blocking,
    }


def route_after_search(state: AgentState) -> str:
    request = state["request"]
    has_outbound = bool(state.get("raw_offers"))
    needs_return = _is_round_trip(request)
    has_return = bool(state.get("raw_return_offers"))

    if has_outbound and (not needs_return or has_return):
        return "ok"
    # 已经问过一次、用户明确拒绝放宽红眼限制，就不能再问第二次，只能诚实地报告失败。
    if state.get("redeye_blocking") and not request.get("redeye_confirmation_declined"):
        return "need_redeye_confirmation"
    return "empty"


def ask_redeye_confirmation_node(state: AgentState) -> AgentState:
    text, usage = chat_text(
        "你是一个诚实的机票助手。用户明确要求不要红眼航班，但完全没有符合其他条件的非红眼航班，"
        "只有红眼航班可选。请用一句中文询问用户是否愿意接受红眼航班选项，不要擅自替用户做主，"
        "也不要编造具体的航班信息。",
        f"已知需求: {state.get('request')}",
    )
    return {
        "final_text": text,
        "status": "clarification",
        "pending_confirmation": {"type": "redeye"},
        "metrics": _log_llm_call(state, "ask_redeye_confirmation", usage),
    }


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


def _price_offers(raw_offers: list[dict], baggage_kg: int) -> list[dict]:
    offers = dedupe_offers([FlightOffer(**o) for o in raw_offers])
    return [
        {
            "offer": offer.model_dump(mode="json"),
            "breakdown": calculate_breakdown(offer, baggage_kg).model_dump(),
        }
        for offer in offers
    ]


def normalize_and_dedupe_node(state: AgentState) -> AgentState:
    baggage_kg = state["request"].get("checked_baggage_kg") or 0
    return {
        "priced_offers": _price_offers(state["raw_offers"], baggage_kg),
        "priced_return_offers": _price_offers(state.get("raw_return_offers") or [], baggage_kg),
    }


def _refresh_priced_offers(priced_offers: list[dict]) -> list[dict]:
    refreshed = []
    for item in priced_offers:
        offer = refresh_fare(FlightOffer(**item["offer"]))
        refreshed.append({"offer": offer.model_dump(mode="json"), "breakdown": item["breakdown"]})
    return refreshed


def verify_fare_node(state: AgentState) -> AgentState:
    return {
        "priced_offers": _refresh_priced_offers(state["priced_offers"]),
        "priced_return_offers": _refresh_priced_offers(state.get("priced_return_offers") or []),
    }


def _tier_entry(offer: FlightOffer, breakdown: PriceBreakdown) -> dict:
    return {
        "flight_id": offer.flight_id,
        "total_price_cny": breakdown.total_cny,
        "breakdown": breakdown.model_dump(),
        "source": offer.source,
        "queried_at": offer.queried_at.isoformat(),
    }


def rank_and_tier_node(state: AgentState) -> AgentState:
    def _to_pairs(priced_offers: list[dict]):
        return [
            (FlightOffer(**item["offer"]), PriceBreakdown(**item["breakdown"])) for item in priced_offers
        ]

    profile = state["request"].get("priority_profile", "BALANCED")
    ranked_out = rank_and_tier(_to_pairs(state["priced_offers"]), profile)
    ranked_ret = rank_and_tier(_to_pairs(state.get("priced_return_offers") or []), profile)

    result = {}
    for tier, (offer, breakdown) in ranked_out.items():
        entry = {"tier": tier, "outbound": _tier_entry(offer, breakdown)}
        if tier in ranked_ret:
            r_offer, r_breakdown = ranked_ret[tier]
            entry["return"] = _tier_entry(r_offer, r_breakdown)
            entry["total_price_cny"] = round(breakdown.total_cny + r_breakdown.total_cny, 2)
        else:
            entry["total_price_cny"] = breakdown.total_cny
        result[tier] = entry
    return {"ranked_results": result}


def generate_response_node(state: AgentState) -> AgentState:
    notes = state.get("relaxation_notes") or []
    note_prompt = (
        f"\n注意：本次搜索自动放宽了以下条件才找到结果，必须在回复里如实告诉用户做了什么调整，"
        f"不能假装是按用户原话精确查到的：{notes}"
        if notes
        else ""
    )
    text, usage = chat_text(
        "你是一个机票助手。请用简短的中文总结下面的查询结果，并提醒用户每条结果的数据来源和查询时间。",
        f"结果: {state.get('ranked_results')}{note_prompt}",
    )
    return {
        "final_text": text,
        "status": "results",
        "metrics": _log_llm_call(state, "generate_response", usage),
    }
