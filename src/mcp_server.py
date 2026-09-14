"""最小 MCP Server（基于 mcp 2.x 的 MCPServer）：只暴露 search_flights 一个工具。

复用 src/tools/search_flights.py 里的 search_flights_tool，
证明同一套工具函数既能被 LangGraph 图内部调用，也能被外部 MCP 客户端调用。
运行: python -m src.mcp_server
"""
from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from src.tools.search_flights import search_flights_tool

mcp = MCPServer("flight-price-compare")


@mcp.tool()
def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    date_flexibility_days: int = 0,
) -> dict:
    """按出发地、目的地、出发日期查询模拟航班报价。

    origin/destination 可以是城市名（如“上海”）或机场代码（如“SHA”）。
    departure_date 格式为 YYYY-MM-DD。无法识别的城市/机场代码或无匹配航班时，
    返回结构化 error 而不是抛异常。
    """
    result = search_flights_tool(origin, destination, departure_date, date_flexibility_days)
    return result.model_dump(mode="json")


if __name__ == "__main__":
    mcp.run()
