"""
Server-side price calculation for the E-Summit live market.

The engine is framework-agnostic. It receives already-aggregated inputs from
the market clock and returns the next authoritative company price.

Price movement is composed of:

    order-flow impact
    + fundamental drift
    + sentiment
    + news/event shock
    + controlled noise

Order-flow impact uses a diminishing-response curve so progressively larger
orders have progressively less proportional influence on price.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import math


@dataclass(frozen=True)
class OrderFlow:
    company_id: str
    buy_pressure: Decimal
    sell_pressure: Decimal

    @property
    def net_pressure(self) -> Decimal:
        return self.buy_pressure - self.sell_pressure

    @property
    def total_volume(self) -> Decimal:
        return self.buy_pressure + self.sell_pressure


# ---------------------------------------------------------------------------
# Safety rails
# ---------------------------------------------------------------------------

# Maximum total movement in a single tick.
MAX_TICK_MOVEMENT_PERCENT = Decimal("0.08")

# Maximum contribution that aggregated order flow can make before the final
# per-tick safety cap is applied.
MAX_ORDER_FLOW_IMPACT = Decimal("0.06")

# Liquidity-normalized pressure at which order-flow response starts becoming
# noticeably less sensitive.
ORDER_FLOW_RESPONSE_SCALE = Decimal("0.05")

# Absolute minimum company price.
PRICE_FLOOR = Decimal("1.00")

# Used by the multi-tick circuit-breaker layer in the market clock.
CIRCUIT_BREAKER_PERCENT = Decimal("0.25")


def _diminishing_order_flow_impact(
    *,
    net_pressure: Decimal,
    liquidity_depth: Decimal,
) -> Decimal:
    """
    Convert net currency pressure into percentage price impact.

    The response follows a tanh curve:

        impact = max_impact * tanh(
            normalized_pressure / response_scale
        )

    For small orders this behaves approximately linearly.

    As order pressure becomes very large, the response approaches
    MAX_ORDER_FLOW_IMPACT rather than increasing without bound.

    This prevents a team spending a huge amount of virtual cash in one tick
    from mechanically forcing an unrealistic price jump.
    """
    if liquidity_depth <= 0:
        raise ValueError("liquidity_depth must be positive")

    if net_pressure == 0:
        return Decimal("0")

    normalized_pressure = net_pressure / liquidity_depth

    # Decimal -> float is acceptable only inside this bounded mathematical
    # transformation. The authoritative result is converted back to Decimal
    # immediately and the final price is quantized deterministically.
    x = float(
        normalized_pressure / ORDER_FLOW_RESPONSE_SCALE
    )

    impact = float(MAX_ORDER_FLOW_IMPACT) * math.tanh(x)

    return Decimal(str(impact))


def compute_next_price(
    *,
    current_price: Decimal,
    order_flow: OrderFlow,
    liquidity_depth: Decimal,
    fundamental_drift: Decimal = Decimal("0"),
    sentiment: Decimal = Decimal("0"),
    news_shock: Decimal = Decimal("0"),
    noise: Decimal = Decimal("0"),
) -> Decimal:
    """
    Calculate the next authoritative company price.

    Percentage-like inputs use decimal fractions:

        Decimal("0.01")  -> +1%
        Decimal("-0.05") -> -5%

    Circuit breakers requiring multiple ticks of history are handled by the
    market clock rather than this pure calculation function.
    """
    if current_price <= 0:
        raise ValueError("current_price must be positive")

    if liquidity_depth <= 0:
        raise ValueError("liquidity_depth must be positive")

    market_pressure = _diminishing_order_flow_impact(
        net_pressure=order_flow.net_pressure,
        liquidity_depth=liquidity_depth,
    )

    total_move_percent = (
        market_pressure
        + fundamental_drift
        + sentiment
        + news_shock
        + noise
    )

    # Absolute per-tick safety rail.
    total_move_percent = max(
        -MAX_TICK_MOVEMENT_PERCENT,
        min(MAX_TICK_MOVEMENT_PERCENT, total_move_percent),
    )

    new_price = current_price * (
        Decimal("1") + total_move_percent
    )

    # Absolute price floor.
    new_price = max(PRICE_FLOOR, new_price)

    # Company.current_price is Numeric(14, 4), so make the precision
    # deterministic before returning to the database layer.
    return new_price.quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )
