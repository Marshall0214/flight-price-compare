from datetime import datetime, timezone

import pytest

from src.models import FlightOffer
from src.pricing import (
    calculate_breakdown,
    convert_to_cny,
    dedupe_offers,
    rank_and_tier,
    refresh_fare,
)


def make_offer(**overrides) -> FlightOffer:
    base = dict(
        flight_id="TEST1",
        origin="SHA",
        destination="NRT",
        departure_time=datetime(2026, 9, 10, 9, 0, tzinfo=timezone.utc),
        arrival_time=datetime(2026, 9, 10, 13, 0, tzinfo=timezone.utc),
        is_red_eye=False,
        airline="MU",
        base_price=2000,
        currency="CNY",
        baggage_fee_per_20kg=200,
        tax_and_fees=100,
        source="mock",
        queried_at=datetime(2026, 9, 13, 10, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return FlightOffer(**base)


def test_convert_to_cny_identity():
    assert convert_to_cny(100, "CNY") == 100


def test_convert_to_cny_jpy():
    assert convert_to_cny(1000, "JPY") == pytest.approx(48.0)


def test_convert_to_cny_unknown_currency_raises():
    with pytest.raises(ValueError):
        convert_to_cny(100, "XXX")


def test_calculate_breakdown_baggage_rounds_up_to_20kg_units():
    offer = make_offer(baggage_fee_per_20kg=200)
    breakdown = calculate_breakdown(offer, checked_baggage_kg=21)
    assert breakdown.baggage_fee_cny == 400  # 21kg -> 2 个 20kg 单位


def test_calculate_breakdown_no_baggage_no_fee():
    offer = make_offer()
    breakdown = calculate_breakdown(offer, checked_baggage_kg=0)
    assert breakdown.baggage_fee_cny == 0


def test_calculate_breakdown_converts_jpy_to_cny():
    offer = make_offer(currency="JPY", base_price=30000, tax_and_fees=2000, baggage_fee_per_20kg=3000)
    breakdown = calculate_breakdown(offer, checked_baggage_kg=20)
    assert breakdown.base_price_cny == pytest.approx(1440.0)
    assert breakdown.baggage_fee_cny == pytest.approx(144.0)
    assert breakdown.tax_and_fees_cny == pytest.approx(96.0)


def test_dedupe_offers_keeps_the_cheaper_duplicate():
    expensive = make_offer(flight_id="MU5040", base_price=2100, source="mock_a")
    cheap = make_offer(flight_id="MU5040", base_price=2050, source="mock_b")
    result = dedupe_offers([expensive, cheap])
    assert len(result) == 1
    assert result[0].base_price == 2050


def test_dedupe_offers_keeps_distinct_flight_ids():
    a = make_offer(flight_id="A1")
    b = make_offer(flight_id="A2")
    result = dedupe_offers([a, b])
    assert len(result) == 2


def test_refresh_fare_updates_queried_at_only():
    offer = make_offer()
    now = datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc)
    refreshed = refresh_fare(offer, now=now)
    assert refreshed.queried_at == now
    assert refreshed.flight_id == offer.flight_id
    assert refreshed.base_price == offer.base_price


def test_rank_and_tier_picks_cheapest_and_most_comfortable():
    cheap_red_eye = make_offer(flight_id="R1", base_price=1500, is_red_eye=True)
    normal = make_offer(flight_id="R2", base_price=2000, is_red_eye=False)
    priced = [
        (cheap_red_eye, calculate_breakdown(cheap_red_eye, 0)),
        (normal, calculate_breakdown(normal, 0)),
    ]
    ranked = rank_and_tier(priced)
    assert ranked["cheapest"][0].flight_id == "R1"
    assert ranked["most_comfortable"][0].flight_id == "R2"


def test_rank_and_tier_empty_input_returns_empty_dict():
    assert rank_and_tier([]) == {}
