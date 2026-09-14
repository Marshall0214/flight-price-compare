"""不涉及 LLM 调用的节点级测试：search_flights_node 的红眼过滤规则，
以及往返（trip_duration_days）场景下的去程/回程搜索与合并计价。"""
from src.models import FlightOffer, PriceBreakdown
from src.nodes import normalize_and_dedupe_node, rank_and_tier_node, route_after_search, search_flights_node


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


def test_one_way_request_has_no_return_offers():
    state = {
        "request": {
            "origin": "SHA",
            "destination": "NRT",
            "departure_date": "2026-09-10",
            "date_flexibility_days": 0,
            "avoid_red_eye": False,
            "trip_duration_days": None,
        },
        "origin_codes": ["SHA", "PVG"],
        "destination_codes": ["NRT", "HND"],
    }
    result = search_flights_node(state)
    assert result["raw_return_offers"] == []


def test_round_trip_searches_return_leg_on_computed_date():
    # 09-10 出发，玩 5 天 -> 回程应该搜 09-15（mock 数据里 MU5043/NH921 正好在这天）
    state = {
        "request": {
            "origin": "SHA",
            "destination": "NRT",
            "departure_date": "2026-09-10",
            "date_flexibility_days": 0,
            "avoid_red_eye": False,
            "trip_duration_days": 5,
        },
        "origin_codes": ["SHA", "PVG"],
        "destination_codes": ["NRT", "HND"],
    }
    result = search_flights_node(state)
    return_ids = {o["flight_id"] for o in result["raw_return_offers"]}
    assert "MU5043" in return_ids
    assert "NH921" in return_ids


def test_route_after_search_fails_when_return_leg_has_no_offers():
    state = {
        "request": {"departure_date": "2026-09-10", "trip_duration_days": 1},
        "raw_offers": [{"flight_id": "X"}],
        "raw_return_offers": [],
    }
    assert route_after_search(state) == "empty"


def test_route_after_search_ok_for_one_way_without_return_offers():
    state = {
        "request": {"departure_date": "2026-09-10", "trip_duration_days": None},
        "raw_offers": [{"flight_id": "X"}],
        "raw_return_offers": [],
    }
    assert route_after_search(state) == "ok"


def _make_offer_dict(flight_id: str, base_price: float, is_red_eye: bool = False) -> dict:
    return FlightOffer(
        flight_id=flight_id,
        origin="SHA",
        destination="NRT",
        departure_time="2026-09-10T09:00:00+08:00",
        arrival_time="2026-09-10T13:00:00+09:00",
        is_red_eye=is_red_eye,
        airline="MU",
        base_price=base_price,
        currency="CNY",
        baggage_fee_per_20kg=0,
        tax_and_fees=0,
        source="mock",
        queried_at="2026-09-13T10:00:00+08:00",
    ).model_dump(mode="json")


def test_rank_and_tier_node_combines_outbound_and_return_totals():
    state = {
        "request": {"checked_baggage_kg": 0},
        "raw_offers": [_make_offer_dict("OUT1", 1000)],
        "raw_return_offers": [_make_offer_dict("RET1", 800)],
    }
    priced_state = normalize_and_dedupe_node(state)
    state.update(priced_state)
    ranked_state = rank_and_tier_node(state)

    cheapest = ranked_state["ranked_results"]["cheapest"]
    assert cheapest["outbound"]["flight_id"] == "OUT1"
    assert cheapest["return"]["flight_id"] == "RET1"
    assert cheapest["total_price_cny"] == 1800.0


def test_rank_and_tier_node_one_way_has_no_return_key():
    state = {
        "request": {"checked_baggage_kg": 0},
        "raw_offers": [_make_offer_dict("OUT1", 1000)],
        "raw_return_offers": [],
    }
    priced_state = normalize_and_dedupe_node(state)
    state.update(priced_state)
    ranked_state = rank_and_tier_node(state)

    cheapest = ranked_state["ranked_results"]["cheapest"]
    assert "return" not in cheapest
    assert cheapest["total_price_cny"] == 1000.0
