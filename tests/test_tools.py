from src.tools.airport_codes import resolve_airport_code
from src.tools.search_flights import search_flights_tool, search_offers


def test_resolve_airport_code_by_city_name():
    result = resolve_airport_code("上海")
    assert result.error is None
    assert set(result.resolved) == {"SHA", "PVG"}


def test_resolve_airport_code_by_code():
    result = resolve_airport_code("nrt")
    assert result.error is None
    assert result.resolved == ["NRT"]


def test_resolve_airport_code_unknown_returns_structured_error():
    result = resolve_airport_code("ABC")
    assert result.resolved == []
    assert result.error is not None
    assert result.error.error_code == "UNKNOWN_LOCATION"


def test_resolve_airport_code_missing_input():
    result = resolve_airport_code(None)
    assert result.error is not None
    assert result.error.error_code == "MISSING_LOCATION"


def test_search_offers_finds_matching_route_and_date():
    offers = search_offers(["SHA", "PVG"], ["NRT", "HND"], "2026-09-10")
    flight_ids = {o.flight_id for o in offers}
    assert "MU5042" in flight_ids
    assert "MU5040" in flight_ids
    assert "NH920" in flight_ids


def test_search_offers_respects_date_flexibility():
    offers = search_offers(["SHA"], ["NRT"], "2026-09-11", date_flexibility_days=1)
    flight_ids = {o.flight_id for o in offers}
    assert "MU5042" in flight_ids  # 09-10，落在 09-11 ±1 天范围内


def test_search_offers_no_match_returns_empty_list():
    offers = search_offers(["SIN"], ["SHA"], "2026-09-10")
    assert offers == []


def test_search_flights_tool_returns_error_for_unknown_city():
    result = search_flights_tool("ABC", "东京", "2026-09-10")
    assert result.offers == []
    assert result.error is not None
    assert result.error.error_code == "UNKNOWN_LOCATION"


def test_search_flights_tool_resolves_city_names_end_to_end():
    result = search_flights_tool("上海", "东京", "2026-09-10")
    assert result.error is None
    assert len(result.offers) >= 2
