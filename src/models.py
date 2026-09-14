"""Pydantic 数据模型：需求、航班报价、价格明细、结果、错误。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class FlightSearchRequest(BaseModel):
    origin: Optional[str] = None
    destination: Optional[str] = None
    departure_date: Optional[str] = None  # ISO 日期 "YYYY-MM-DD"
    trip_duration_days: Optional[int] = None
    date_flexibility_days: int = 0
    # 用户是否明确说过一个弹性天数（哪怕是 0，比如"必须是那天，不能有任何浮动"）。
    # 区分"用户从没提过弹性"（可以被 Agent 自主放宽去重试）和"用户明确说过弹性范围"
    # （属于用户明确表达的约束，不能被自主超出，只能靠这个字段做判断依据）。
    date_flexibility_explicit: bool = False
    checked_baggage_kg: int = 0
    avoid_red_eye: bool = False
    # 已经问过用户"要不要接受红眼"、且用户拒绝了，就不再重复问，
    # 直接诚实地报告没有符合条件的航班，而不是把同一个问题再问一遍。
    redeye_confirmation_declined: bool = False
    # 用户对价格/舒适度的倾向，由 LLM 从自然语言判断后填入这三个枚举值之一；
    # 只影响 best_overall 用哪套权重计算，权重计算本身仍然是确定性代码。
    priority_profile: Literal["PRICE_FIRST", "COMFORT_FIRST", "BALANCED"] = "BALANCED"

    def missing_required_fields(self) -> list[str]:
        missing = []
        if not self.origin:
            missing.append("origin")
        if not self.destination:
            missing.append("destination")
        if not self.departure_date:
            missing.append("departure_date")
        return missing


class ToolError(BaseModel):
    error_code: str
    message: str


class AirportResolution(BaseModel):
    resolved: list[str] = Field(default_factory=list)
    error: Optional[ToolError] = None


class FlightOffer(BaseModel):
    flight_id: str
    origin: str
    destination: str
    departure_time: datetime
    arrival_time: datetime
    is_red_eye: bool
    airline: str
    base_price: float
    currency: str
    baggage_fee_per_20kg: float
    tax_and_fees: float
    source: str
    queried_at: datetime


class PriceBreakdown(BaseModel):
    base_price_cny: float
    baggage_fee_cny: float
    tax_and_fees_cny: float

    @property
    def total_cny(self) -> float:
        return round(self.base_price_cny + self.baggage_fee_cny + self.tax_and_fees_cny, 2)


class SearchFlightsOutput(BaseModel):
    offers: list[FlightOffer] = Field(default_factory=list)
    error: Optional[ToolError] = None
