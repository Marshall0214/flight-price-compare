"""LangGraph 的共享状态定义。"""
from __future__ import annotations

from typing import Any, Optional, TypedDict


class AgentState(TypedDict, total=False):
    user_message: str
    request: dict[str, Any]
    # 上一轮如果是"是否愿意放宽某条硬约束"的确认问题（目前只有红眼一种），
    # 客户端把上一次响应里的这个字段原样带回来，供 parse_input 判断本轮回复的含义。
    pending_confirmation: Optional[dict[str, Any]]
    missing_fields: list[str]
    clarification_question: str
    origin_codes: list[str]
    destination_codes: list[str]
    airport_error: dict[str, Any]
    raw_offers: list[dict[str, Any]]
    raw_return_offers: list[dict[str, Any]]
    # 搜索时是否自动放宽了"用户从没明确表态过"的弹性天数（比如原本没提弹性，
    # 精确日期查不到就自动往前后多看几天），以及有没有找到；用于最终回复里如实告知用户。
    relaxation_notes: list[dict[str, Any]]
    # 用户明确要求不要红眼航班，但只有红眼航班可选时置 True，触发追问而不是自主放宽。
    redeye_blocking: bool
    priced_offers: list[dict[str, Any]]
    priced_return_offers: list[dict[str, Any]]
    ranked_results: dict[str, Any]
    search_error: dict[str, Any]
    final_text: str
    status: str  # "results" | "clarification" | "error"
    metrics: dict[str, Any]
