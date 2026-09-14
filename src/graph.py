"""用 LangGraph 把各节点接成完整工作流，并对外暴露 run_agent()。

设计说明：本项目不做服务端会话持久化（Roadmap 里的 Memory/RAG 阶段才做），
所以“追问 -> 用户回答”这个循环是靠调用方把上一轮解析出的 request 原样带回来
（FastAPI 的 known_fields 字段）实现的，而不是在一次 graph.invoke() 内部转圈。
这也是 docs/requirements.md 里说明过的设计取舍，不是遗漏。
"""
from __future__ import annotations

import time
from typing import Any

from langgraph.graph import END, StateGraph

from src.nodes import (
    ask_clarification_node,
    ask_redeye_confirmation_node,
    explain_failure_node,
    generate_response_node,
    normalize_and_dedupe_node,
    parse_input_node,
    rank_and_tier_node,
    resolve_airport_code_node,
    route_after_airport,
    route_after_parse,
    route_after_search,
    search_flights_node,
    verify_fare_node,
)
from src.state import AgentState

_compiled_graph = None


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("parse_input", parse_input_node)
    graph.add_node("ask_clarification", ask_clarification_node)
    graph.add_node("resolve_airport_code", resolve_airport_code_node)
    graph.add_node("search_flights", search_flights_node)
    graph.add_node("ask_redeye_confirmation", ask_redeye_confirmation_node)
    graph.add_node("explain_failure", explain_failure_node)
    graph.add_node("normalize_and_dedupe", normalize_and_dedupe_node)
    graph.add_node("verify_fare", verify_fare_node)
    graph.add_node("rank_and_tier", rank_and_tier_node)
    graph.add_node("generate_response", generate_response_node)

    graph.set_entry_point("parse_input")

    graph.add_conditional_edges(
        "parse_input",
        route_after_parse,
        {"missing": "ask_clarification", "complete": "resolve_airport_code"},
    )
    graph.add_edge("ask_clarification", END)

    graph.add_conditional_edges(
        "resolve_airport_code",
        route_after_airport,
        {"error": "explain_failure", "ok": "search_flights"},
    )

    graph.add_conditional_edges(
        "search_flights",
        route_after_search,
        {
            "empty": "explain_failure",
            "ok": "normalize_and_dedupe",
            "need_redeye_confirmation": "ask_redeye_confirmation",
        },
    )

    graph.add_edge("normalize_and_dedupe", "verify_fare")
    graph.add_edge("verify_fare", "rank_and_tier")
    graph.add_edge("rank_and_tier", "generate_response")
    graph.add_edge("generate_response", END)
    graph.add_edge("explain_failure", END)
    graph.add_edge("ask_redeye_confirmation", END)

    return graph.compile()


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph


def run_agent(
    user_message: str,
    known_fields: dict[str, Any] | None = None,
    pending_confirmation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    initial_state: AgentState = {
        "user_message": user_message,
        "request": known_fields or {},
        "pending_confirmation": pending_confirmation,
    }
    final_state = get_graph().invoke(initial_state)
    elapsed = time.perf_counter() - t0

    metrics = dict(final_state.get("metrics") or {})
    metrics["total_elapsed_s"] = elapsed

    status = final_state.get("status")
    return {
        "status": status,
        "message": final_state.get("final_text"),
        "request": final_state.get("request"),
        "missing_fields": final_state.get("missing_fields", []),
        "results": final_state.get("ranked_results"),
        "error": final_state.get("search_error") or final_state.get("airport_error"),
        # 只有当前这一轮确实是"等待确认"状态时才把 pending_confirmation 传出去，
        # 客户端要在下一次 /query 请求里原样带回来。
        "pending_confirmation": final_state.get("pending_confirmation") if status == "clarification" else None,
        "relaxation_notes": final_state.get("relaxation_notes") or [],
        "metrics": metrics,
    }
