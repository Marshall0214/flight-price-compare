"""LangGraph 的共享状态定义。"""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    user_message: str
    request: dict[str, Any]
    missing_fields: list[str]
    clarification_question: str
    origin_codes: list[str]
    destination_codes: list[str]
    airport_error: dict[str, Any]
    raw_offers: list[dict[str, Any]]
    raw_return_offers: list[dict[str, Any]]
    priced_offers: list[dict[str, Any]]
    priced_return_offers: list[dict[str, Any]]
    ranked_results: dict[str, Any]
    search_error: dict[str, Any]
    final_text: str
    status: str  # "results" | "clarification" | "error"
    metrics: dict[str, Any]
