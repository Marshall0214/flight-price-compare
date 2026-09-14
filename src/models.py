"""Pydantic 数据模型：需求、航班报价、价格明细、结果、错误。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FlightSearchRequest(BaseModel):
    origin: Optional[str] = None
    destination: Optional[str] = None
    departure_date: Optional[str] = None  # ISO 日期 "YYYY-MM-DD"
    trip_duration_days: Optional[int] = None
    date_flexibility_days: int = 0
    checked_baggage_kg: int = 0
    avoid_red_eye: bool = False

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
