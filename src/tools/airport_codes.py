"""城市名 <-> 机场代码 解析工具（resolve_airport_code）。

以 MCP tool 的思路设计：输入一个字符串（城市名或机场代码），
输出结构化结果（AirportResolution），无法识别时返回结构化错误而不是抛异常。
"""
from __future__ import annotations

from src.models import AirportResolution, ToolError

CITY_TO_AIRPORTS: dict[str, list[str]] = {
    "上海": ["SHA", "PVG"],
    "东京": ["NRT", "HND"],
    "新加坡": ["SIN"],
    "北京": ["PEK", "PKX"],
    "曼谷": ["BKK"],
}

KNOWN_AIRPORT_CODES: set[str] = {code for codes in CITY_TO_AIRPORTS.values() for code in codes}


def resolve_airport_code(place: str | None) -> AirportResolution:
    if not place:
        return AirportResolution(
            error=ToolError(error_code="MISSING_LOCATION", message="缺少出发地或目的地")
        )

    place = place.strip()
    upper = place.upper()

    if upper in KNOWN_AIRPORT_CODES:
        return AirportResolution(resolved=[upper])

    if place in CITY_TO_AIRPORTS:
        return AirportResolution(resolved=CITY_TO_AIRPORTS[place])

    return AirportResolution(
        error=ToolError(error_code="UNKNOWN_LOCATION", message=f"无法识别的城市或机场代码: {place}")
    )
