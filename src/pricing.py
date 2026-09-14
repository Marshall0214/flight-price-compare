"""确定性业务逻辑：价格计算、币种换算、去重、验价、排序分档。

这里的所有函数都不调用 LLM——涉及金额和排序的地方必须是普通代码，
这也是本项目在 README/需求分析里反复强调的设计边界，方便写 pytest 覆盖。
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from src.models import FlightOffer, PriceBreakdown

# 静态汇率表（mock 数据用），不接入真实汇率 API。
EXCHANGE_RATES_TO_CNY: dict[str, float] = {
    "CNY": 1.0,
    "JPY": 0.048,
    "USD": 7.1,
}


def convert_to_cny(amount: float, currency: str) -> float:
    rate = EXCHANGE_RATES_TO_CNY.get(currency.upper())
    if rate is None:
        raise ValueError(f"不支持的币种: {currency}")
    return amount * rate


def calculate_breakdown(offer: FlightOffer, checked_baggage_kg: int) -> PriceBreakdown:
    base_cny = convert_to_cny(offer.base_price, offer.currency)
    tax_cny = convert_to_cny(offer.tax_and_fees, offer.currency)
    baggage_units = math.ceil(checked_baggage_kg / 20) if checked_baggage_kg > 0 else 0
    baggage_fee_cny = convert_to_cny(offer.baggage_fee_per_20kg, offer.currency) * baggage_units
    return PriceBreakdown(
        base_price_cny=round(base_cny, 2),
        baggage_fee_cny=round(baggage_fee_cny, 2),
        tax_and_fees_cny=round(tax_cny, 2),
    )


def dedupe_offers(offers: list[FlightOffer]) -> list[FlightOffer]:
    """按 flight_id 去重，多个来源报价同一航班时保留换算成人民币后更便宜的那条。"""
    best_by_id: dict[str, FlightOffer] = {}
    for offer in offers:
        existing = best_by_id.get(offer.flight_id)
        if existing is None or convert_to_cny(offer.base_price, offer.currency) < convert_to_cny(
            existing.base_price, existing.currency
        ):
            best_by_id[offer.flight_id] = offer
    return list(best_by_id.values())


def refresh_fare(offer: FlightOffer, now: datetime | None = None) -> FlightOffer:
    """模拟“重新验价”：mock 数据本身不会变化，这里用刷新 queried_at 代表已重新核实过价格。

    接入真实机票 API 后，这里应该替换成一次真实的重新查询，并在价格变化时更新 total 或返回验价失败。
    """
    now = now or datetime.now(timezone.utc)
    return offer.model_copy(update={"queried_at": now})


def rank_and_tier(
    priced_offers: list[tuple[FlightOffer, PriceBreakdown]],
) -> dict[str, tuple[FlightOffer, PriceBreakdown]]:
    """计算最便宜 / 综合最优 / 最舒适三档结果。"""
    if not priced_offers:
        return {}

    def total(pair: tuple[FlightOffer, PriceBreakdown]) -> float:
        return pair[1].total_cny

    cheapest = min(priced_offers, key=total)
    most_comfortable = min(priced_offers, key=lambda pair: (pair[0].is_red_eye, total(pair)))

    prices = [total(pair) for pair in priced_offers]
    min_price, max_price = min(prices), max(prices)

    def score(pair: tuple[FlightOffer, PriceBreakdown]) -> float:
        price_norm = 0.0 if max_price == min_price else (total(pair) - min_price) / (max_price - min_price)
        comfort_penalty = 0.3 if pair[0].is_red_eye else 0.0
        return price_norm * 0.7 + comfort_penalty

    best_overall = min(priced_offers, key=score)

    return {
        "cheapest": cheapest,
        "best_overall": best_overall,
        "most_comfortable": most_comfortable,
    }
