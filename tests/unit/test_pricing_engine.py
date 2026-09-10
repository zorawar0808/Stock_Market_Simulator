from decimal import Decimal

import pytest

from market_engine.pricing.engine import (
    MAX_TICK_MOVEMENT_PERCENT,
    PRICE_FLOOR,
    OrderFlow,
    compute_next_price,
)


def flow(buy: str = "0", sell: str = "0") -> OrderFlow:
    return OrderFlow(
        company_id="test-company",
        buy_pressure=Decimal(buy),
        sell_pressure=Decimal(sell),
    )


def test_zero_order_flow_keeps_price_unchanged():
    price = compute_next_price(
        current_price=Decimal("100"),
        order_flow=flow(),
        liquidity_depth=Decimal("100000"),
    )

    assert price == Decimal("100.0000")


def test_small_buy_pressure_moves_price_up():
    price = compute_next_price(
        current_price=Decimal("100"),
        order_flow=flow(buy="1000"),
        liquidity_depth=Decimal("100000"),
    )

    assert price > Decimal("100.0000")


def test_small_sell_pressure_moves_price_down():
    price = compute_next_price(
        current_price=Decimal("100"),
        order_flow=flow(sell="1000"),
        liquidity_depth=Decimal("100000"),
    )

    assert price < Decimal("100.0000")


def test_buy_and_sell_pressure_cancel():
    price = compute_next_price(
        current_price=Decimal("100"),
        order_flow=flow(buy="5000", sell="5000"),
        liquidity_depth=Decimal("100000"),
    )

    assert price == Decimal("100.0000")


def test_order_flow_has_diminishing_returns():
    small = compute_next_price(
        current_price=Decimal("100"),
        order_flow=flow(buy="10000"),
        liquidity_depth=Decimal("100000"),
    )

    large = compute_next_price(
        current_price=Decimal("100"),
        order_flow=flow(buy="50000"),
        liquidity_depth=Decimal("100000"),
    )

    small_move = small - Decimal("100")
    large_move = large - Decimal("100")

    # Five times the capital pressure should produce less than five times
    # the price movement.
    assert large_move > small_move
    assert large_move < small_move * Decimal("5")


def test_fundamental_drift_is_applied():
    price = compute_next_price(
        current_price=Decimal("100"),
        order_flow=flow(),
        liquidity_depth=Decimal("100000"),
        fundamental_drift=Decimal("0.01"),
    )

    assert price == Decimal("101.0000")


def test_news_shock_is_applied():
    price = compute_next_price(
        current_price=Decimal("100"),
        order_flow=flow(),
        liquidity_depth=Decimal("100000"),
        news_shock=Decimal("-0.05"),
    )

    assert price == Decimal("95.0000")


def test_total_movement_is_capped():
    price = compute_next_price(
        current_price=Decimal("100"),
        order_flow=flow(buy="1000000"),
        liquidity_depth=Decimal("100000"),
        fundamental_drift=Decimal("0.08"),
        news_shock=Decimal("0.08"),
    )

    assert price == Decimal("108.0000")


def test_downward_movement_is_capped():
    price = compute_next_price(
        current_price=Decimal("100"),
        order_flow=flow(sell="1000000"),
        liquidity_depth=Decimal("100000"),
        fundamental_drift=Decimal("-0.08"),
        news_shock=Decimal("-0.08"),
    )

    assert price == Decimal("92.0000")


def test_price_floor_is_enforced():
    price = compute_next_price(
        current_price=Decimal("1.01"),
        order_flow=flow(sell="10000000"),
        liquidity_depth=Decimal("100000"),
        news_shock=Decimal("-0.08"),
    )

    assert price >= PRICE_FLOOR


def test_invalid_liquidity_is_rejected():
    with pytest.raises(ValueError):
        compute_next_price(
            current_price=Decimal("100"),
            order_flow=flow(),
            liquidity_depth=Decimal("0"),
        )


def test_negative_price_is_rejected():
    with pytest.raises(ValueError):
        compute_next_price(
            current_price=Decimal("-1"),
            order_flow=flow(),
            liquidity_depth=Decimal("100000"),
        )


def test_output_has_four_decimal_places():
    price = compute_next_price(
        current_price=Decimal("123.456789"),
        order_flow=flow(buy="1234"),
        liquidity_depth=Decimal("100000"),
    )

    assert price.as_tuple().exponent == -4
