"""不涉及 LLM 调用的节点级测试：search_flights_node 的红眼过滤规则。"""
from src.nodes import search_flights_node


def test_avoid_red_eye_filters_out_red_eye_flights():
    state = {
        "request": {
            "origin": "SHA",
            "destination": "NRT",
            "departure_date": "2026-09-10",
            "date_flexibility_days": 0,
            "avoid_red_eye": True,
        },
        "origin_codes": ["SHA", "PVG"],
        "destination_codes": ["NRT", "HND"],
    }
    result = search_flights_node(state)
    flight_ids = {o["flight_id"] for o in result["raw_offers"]}
    assert "MU5042" not in flight_ids  # MU5042 是红眼航班，必须被过滤掉
    assert "MU5040" in flight_ids
    assert "NH920" in flight_ids


def test_without_avoid_red_eye_keeps_red_eye_flights():
    state = {
        "request": {
            "origin": "SHA",
            "destination": "NRT",
            "departure_date": "2026-09-10",
            "date_flexibility_days": 0,
            "avoid_red_eye": False,
        },
        "origin_codes": ["SHA", "PVG"],
        "destination_codes": ["NRT", "HND"],
    }
    result = search_flights_node(state)
    flight_ids = {o["flight_id"] for o in result["raw_offers"]}
    assert "MU5042" in flight_ids
