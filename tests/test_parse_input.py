"""parse_input_node 的合并逻辑测试：用 mock 的 chat_json 代替真实 LLM 调用，
只验证纯代码部分的合并规则（date_flexibility_explicit 追踪、pending_confirmation 清空）。"""
from unittest.mock import patch

from src.nodes import parse_input_node


def _run_parse(user_message: str, known: dict, parsed_response: dict, pending_confirmation=None):
    state = {"user_message": user_message, "request": known, "pending_confirmation": pending_confirmation}
    with patch("src.nodes.chat_json", return_value=(parsed_response, {"total_tokens": 1})):
        return parse_input_node(state)


def test_date_flexibility_marked_explicit_when_user_states_zero():
    # 用户明确说"必须是那天，不能有任何浮动" -> LLM 应该输出 0 而不是 null，
    # 程序据此把 date_flexibility_explicit 标记为 True。
    result = _run_parse(
        "必须是9月8日这天，不能有任何浮动",
        known={},
        parsed_response={
            "origin": "上海", "destination": "东京", "departure_date": "2026-09-08",
            "trip_duration_days": None, "date_flexibility_days": 0,
            "checked_baggage_kg": None, "avoid_red_eye": None, "priority_profile": None,
        },
    )
    assert result["request"]["date_flexibility_explicit"] is True
    assert result["request"]["date_flexibility_days"] == 0


def test_date_flexibility_not_explicit_when_not_mentioned():
    result = _run_parse(
        "帮我查9月8日从上海到东京的机票",
        known={},
        parsed_response={
            "origin": "上海", "destination": "东京", "departure_date": "2026-09-08",
            "trip_duration_days": None, "date_flexibility_days": None,
            "checked_baggage_kg": None, "avoid_red_eye": None, "priority_profile": None,
        },
    )
    assert result["request"]["date_flexibility_explicit"] is False


def test_date_flexibility_explicit_stays_true_once_set_across_turns():
    known = {"origin": "上海", "destination": "东京", "date_flexibility_days": 2, "date_flexibility_explicit": True}
    result = _run_parse(
        "改成从北京出发",
        known=known,
        parsed_response={
            "origin": "北京", "destination": None, "departure_date": None,
            "trip_duration_days": None, "date_flexibility_days": None,
            "checked_baggage_kg": None, "avoid_red_eye": None, "priority_profile": None,
        },
    )
    assert result["request"]["date_flexibility_explicit"] is True
    assert result["request"]["origin"] == "北京"


def test_pending_confirmation_is_always_cleared_after_parse():
    result = _run_parse(
        "好的，可以",
        known={"origin": "上海", "destination": "东京", "departure_date": "2026-09-26", "avoid_red_eye": True},
        parsed_response={
            "origin": None, "destination": None, "departure_date": None,
            "trip_duration_days": None, "date_flexibility_days": None,
            "checked_baggage_kg": None, "avoid_red_eye": False, "priority_profile": None,
        },
        pending_confirmation={"type": "redeye"},
    )
    assert result["pending_confirmation"] is None
    assert result["request"]["avoid_red_eye"] is False


def test_priority_profile_defaults_to_balanced_when_not_mentioned():
    result = _run_parse(
        "帮我查9月10日从上海到东京的机票",
        known={},
        parsed_response={
            "origin": "上海", "destination": "东京", "departure_date": "2026-09-10",
            "trip_duration_days": None, "date_flexibility_days": None,
            "checked_baggage_kg": None, "avoid_red_eye": None, "priority_profile": None,
        },
    )
    assert result["request"]["priority_profile"] == "BALANCED"


def test_priority_profile_set_when_user_states_preference():
    result = _run_parse(
        "越便宜越好",
        known={"origin": "上海", "destination": "东京", "departure_date": "2026-09-10"},
        parsed_response={
            "origin": None, "destination": None, "departure_date": None,
            "trip_duration_days": None, "date_flexibility_days": None,
            "checked_baggage_kg": None, "avoid_red_eye": None, "priority_profile": "PRICE_FIRST",
        },
    )
    assert result["request"]["priority_profile"] == "PRICE_FIRST"
