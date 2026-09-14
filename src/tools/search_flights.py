"""航班搜索工具（search_flights）。

`search_offers` 是给 LangGraph 图内部节点用的低层函数（假设机场代码已解析好）。
`search_flights_tool` 是给外部调用方（比如 MCP Server）用的高层函数：
自己完成城市名解析 + 搜索，输入输出都是清晰的 Pydantic Schema，
这样同一套底层逻辑既能被内部图调用，也能被外部 MCP 客户端调用，不需要重复实现。
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from src.models import FlightOffer, SearchFlightsOutput
from src.tools.airport_codes import resolve_airport_code

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "mock_flights.json"


@lru_cache(maxsize=1)
def _load_offers() -> list[FlightOffer]:
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return [FlightOffer(**item) for item in raw]


def search_offers(
    origin_codes: list[str],
    destination_codes: list[str],
    departure_date: str | None,
    date_flexibility_days: int = 0,
) -> list[FlightOffer]:
    if not departure_date:
        return []

    target = date.fromisoformat(departure_date)
    low = target - timedelta(days=date_flexibility_days)
    high = target + timedelta(days=date_flexibility_days)

    results = []
    for offer in _load_offers():
        if offer.origin not in origin_codes or offer.destination not in destination_codes:
            continue
        if not (low <= offer.departure_time.date() <= high):
            continue
        results.append(offer)
    return results


def search_flights_tool(
    origin: str,
    destination: str,
    departure_date: str,
    date_flexibility_days: int = 0,
) -> SearchFlightsOutput:
    origin_res = resolve_airport_code(origin)
    if origin_res.error:
        return SearchFlightsOutput(offers=[], error=origin_res.error)

    dest_res = resolve_airport_code(destination)
    if dest_res.error:
        return SearchFlightsOutput(offers=[], error=dest_res.error)

    offers = search_offers(origin_res.resolved, dest_res.resolved, departure_date, date_flexibility_days)
    return SearchFlightsOutput(offers=offers, error=None)
