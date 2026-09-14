"""Streamlit 本地演示页：对话式调用 flight-price-compare 的 /query 接口。

仅用于本地演示和录制 GIF，不代表在线部署。后端 /query 本身无状态
（见 src/graph.py 的设计说明），所有对话状态（known_fields /
pending_confirmation）都由这个页面在 st.session_state 里维护，
每轮原样回传给 /query，复用现有的客户端持有状态协议，不需要改动
任何后端代码。

运行方式（需要先在另一个终端启动 `uvicorn src.app:app --reload`）：
    streamlit run demo/streamlit_app.py
"""
from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st

FASTAPI_URL = os.environ.get("FASTAPI_URL", "http://127.0.0.1:8000")

TIER_LABELS = {
    "cheapest": "💰 最便宜",
    "best_overall": "⭐ 综合最优",
    "most_comfortable": "🛋️ 最舒适",
}

st.set_page_config(page_title="机票比价 Agent", page_icon="✈️")
st.title("✈️ 机票比价 Agent")
st.caption(f"后端: {FASTAPI_URL}/query · 本地演示用，非在线部署")

if "turns" not in st.session_state:
    st.session_state.turns: list[dict[str, Any]] = []
if "known_fields" not in st.session_state:
    st.session_state.known_fields: dict[str, Any] = {}
if "pending_confirmation" not in st.session_state:
    st.session_state.pending_confirmation: dict[str, Any] | None = None

with st.sidebar:
    st.subheader("当前会话状态")
    st.json(st.session_state.known_fields or {"(暂无已知字段)": True})
    if st.session_state.pending_confirmation:
        st.warning(f"等待确认: {st.session_state.pending_confirmation}")
    if st.button("重新开始对话"):
        st.session_state.turns = []
        st.session_state.known_fields = {}
        st.session_state.pending_confirmation = None
        st.rerun()


def render_leg(label: str, leg: dict[str, Any]) -> None:
    red_eye = " 🌙红眼" if leg.get("is_red_eye") else ""
    st.markdown(
        f"**{label}** · {leg.get('airline', '?')} {leg.get('flight_id', '?')}{red_eye}  \n"
        f"{leg.get('departure_time', '?')} → {leg.get('arrival_time', '?')}"
    )


def render_results(results: dict[str, Any]) -> None:
    tiers = list(results.items())
    cols = st.columns(len(tiers) or 1)
    for col, (tier, entry) in zip(cols, tiers):
        with col:
            st.markdown(f"#### {TIER_LABELS.get(tier, tier)}")
            st.metric("总价 (CNY)", entry.get("total_price_cny"))
            outbound = entry.get("outbound") or {}
            if outbound:
                render_leg("去程", outbound)
            if entry.get("return"):
                render_leg("回程", entry["return"])
            st.caption(f"来源: {outbound.get('source', '?')} · 查询于 {outbound.get('queried_at', '?')}")


def render_turn(turn: dict[str, Any]) -> None:
    with st.chat_message(turn["role"]):
        st.write(turn["text"])
        if turn.get("relaxation_notes"):
            st.info(f"本次自动放宽了以下条件才找到结果，不是按你的原话精确查到的：{turn['relaxation_notes']}")
        if turn.get("results"):
            render_results(turn["results"])
        if turn.get("error"):
            error = turn["error"]
            st.error(f"{error.get('error_code', '?')}: {error.get('message', '')}")


for turn in st.session_state.turns:
    render_turn(turn)

user_input = st.chat_input("例如：帮我看看9月从上海去东京，玩5天，带20kg行李，不要红眼航班")
if user_input:
    st.session_state.turns.append({"role": "user", "text": user_input})

    data: dict[str, Any] | None = None
    error_text = ""
    with st.spinner("查询中…"):
        try:
            resp = requests.post(
                f"{FASTAPI_URL}/query",
                json={
                    "message": user_input,
                    "known_fields": st.session_state.known_fields,
                    "pending_confirmation": st.session_state.pending_confirmation,
                },
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            error_text = f"请求失败：{exc}（请确认 `uvicorn src.app:app --reload` 已在另一个终端启动）"

    if data is None:
        st.session_state.turns.append({"role": "assistant", "text": error_text})
    else:
        st.session_state.known_fields = data.get("request") or {}
        st.session_state.pending_confirmation = data.get("pending_confirmation")
        st.session_state.turns.append(
            {
                "role": "assistant",
                "text": data.get("message") or "(无文本回复)",
                "results": data.get("results"),
                "relaxation_notes": data.get("relaxation_notes"),
                "error": data.get("error"),
            }
        )
    st.rerun()
