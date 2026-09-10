"""
Market state machine transitions and emergency market reset.
"""

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import MarketState
from app.models.market_state import MarketStateRow
from app.models.company import Company, Holding, PriceSnapshot
from app.models.team import Team, Portfolio


_VALID_TRANSITIONS: dict[MarketState, set[MarketState]] = {
    MarketState.WAITING: {MarketState.LIVE},
    MarketState.LIVE: {
        MarketState.PAUSED,
        MarketState.EMERGENCY_FROZEN,
        MarketState.ENDING,
    },
    MarketState.PAUSED: {
        MarketState.LIVE,
        MarketState.EMERGENCY_FROZEN,
        MarketState.ENDING,
    },
    MarketState.EMERGENCY_FROZEN: {
        MarketState.LIVE,
        MarketState.PAUSED,
        MarketState.ENDING,
    },
    MarketState.ENDING: {MarketState.CLOSED},
    MarketState.CLOSED: {MarketState.LIVE},
}


class InvalidTransition(Exception):
    def __init__(self, current: MarketState, target: MarketState):
        self.current = current
        self.target = target
        super().__init__(
            f"Cannot transition from {current.value} to {target.value}"
        )


class MarketResetBlocked(Exception):
    def __init__(self, current: MarketState):
        self.current = current
        super().__init__(
            f"Market reset is blocked while market is {current.value}"
        )


async def get_or_create_state(db: AsyncSession) -> MarketStateRow:
    state = await db.get(MarketStateRow, 1)

    if state is None:
        state = MarketStateRow(
            id=1,
            state=MarketState.WAITING,
        )
        db.add(state)
        await db.flush()
        return state

    if state.state == MarketState.LIVE and state.started_at is not None:
        now = datetime.now(timezone.utc)

        elapsed = (
            now - state.started_at
        ).total_seconds() - float(state.total_paused_seconds)

        if elapsed >= float(state.duration_seconds):
            state.state = MarketState.ENDING
            await db.flush()

            state.state = MarketState.CLOSED
            state.ended_at = now
            await db.flush()

    return state


async def _transition(
    db: AsyncSession,
    state: MarketStateRow,
    target: MarketState,
) -> MarketStateRow:
    if target not in _VALID_TRANSITIONS.get(state.state, set()):
        raise InvalidTransition(state.state, target)

    state.state = target
    return state


async def start_market(db: AsyncSession) -> MarketStateRow:
    state = await get_or_create_state(db)

    await _transition(
        db,
        state,
        MarketState.LIVE,
    )

    now = datetime.now(timezone.utc)

    state.started_at = now
    state.paused_at = None
    state.ended_at = None
    state.total_paused_seconds = 0

    await db.flush()
    return state


async def pause_market(db: AsyncSession) -> MarketStateRow:
    state = await get_or_create_state(db)

    await _transition(
        db,
        state,
        MarketState.PAUSED,
    )

    state.paused_at = datetime.now(timezone.utc)

    await db.flush()
    return state


async def resume_market(db: AsyncSession) -> MarketStateRow:
    state = await get_or_create_state(db)

    await _transition(
        db,
        state,
        MarketState.LIVE,
    )

    if state.paused_at is not None:
        paused_duration = (
            datetime.now(timezone.utc) - state.paused_at
        ).total_seconds()

        state.total_paused_seconds = (
            float(state.total_paused_seconds) + paused_duration
        )

        state.paused_at = None

    await db.flush()
    return state


async def emergency_freeze(db: AsyncSession) -> MarketStateRow:
    state = await get_or_create_state(db)

    await _transition(
        db,
        state,
        MarketState.EMERGENCY_FROZEN,
    )

    if state.paused_at is None:
        state.paused_at = datetime.now(timezone.utc)

    await db.flush()
    return state


async def unfreeze_to_live(db: AsyncSession) -> MarketStateRow:
    state = await get_or_create_state(db)

    await _transition(
        db,
        state,
        MarketState.LIVE,
    )

    if state.paused_at is not None:
        paused_duration = (
            datetime.now(timezone.utc) - state.paused_at
        ).total_seconds()

        state.total_paused_seconds = (
            float(state.total_paused_seconds) + paused_duration
        )

        state.paused_at = None

    await db.flush()
    return state


async def end_market(db: AsyncSession) -> MarketStateRow:
    state = await get_or_create_state(db)

    await _transition(
        db,
        state,
        MarketState.ENDING,
    )

    await db.flush()

    state.ended_at = datetime.now(timezone.utc)

    await _transition(
        db,
        state,
        MarketState.CLOSED,
    )

    await db.flush()
    return state


async def reset_market_to_original(db: AsyncSession) -> MarketStateRow:
    """
    Emergency/testing failsafe.

    Restores every company's current price to its initial price,
    removes generated price snapshots, recalculates portfolio values,
    and places the market back into WAITING.

    Participant cash, holdings, and trade history are intentionally
    preserved. This is a price/state reset, not a destructive database reset.

    The reset is blocked while LIVE to prevent the price engine from
    writing new prices concurrently with the reset.
    """
    state = await get_or_create_state(db)

    if state.state == MarketState.LIVE:
        raise MarketResetBlocked(state.state)

    # Lock the market state so another admin cannot modify it during reset.
    state_result = await db.execute(
        select(MarketStateRow)
        .where(MarketStateRow.id == 1)
        .with_for_update()
    )
    state = state_result.scalar_one()

    if state.state == MarketState.LIVE:
        raise MarketResetBlocked(state.state)

    # Lock all companies before changing their prices.
    company_result = await db.execute(
        select(Company).with_for_update()
    )
    companies = company_result.scalars().all()

    for company in companies:
        company.current_price = company.initial_price

    # Old snapshots represent the manipulated market history and must not
    # become the price engine's next tick boundary.
    await db.execute(delete(PriceSnapshot))

    # Recalculate portfolio valuations using the restored prices.
    holdings_result = await db.execute(
        select(Holding, Company)
        .join(
            Company,
            Holding.company_id == Company.company_id,
        )
    )
    holding_rows = holdings_result.all()

    portfolio_values = defaultdict(lambda: Decimal("0"))

    for holding, company in holding_rows:
        shares = Decimal(str(holding.shares))
        price = Decimal(str(company.current_price))
        portfolio_values[holding.team_id] += shares * price

    teams_result = await db.execute(select(Team))
    teams = teams_result.scalars().all()

    for team in teams:
        portfolio_result = await db.execute(
            select(Portfolio)
            .where(Portfolio.team_id == team.team_id)
            .with_for_update()
        )
        portfolio = portfolio_result.scalar_one_or_none()

        if portfolio is None:
            continue

        portfolio_value = portfolio_values[team.team_id]
        cash = Decimal(str(portfolio.cash))
        net_worth = cash + portfolio_value
        starting_capital = Decimal(str(team.starting_capital))

        if starting_capital > 0:
            return_percent = (
                (net_worth - starting_capital)
                / starting_capital
                * Decimal("100")
            )
        else:
            return_percent = Decimal("0")

        portfolio.portfolio_value = portfolio_value
        portfolio.net_worth = net_worth
        portfolio.return_percent = return_percent

    # A reset is a fresh starting point for the market engine.
    state.state = MarketState.WAITING
    state.started_at = None
    state.paused_at = None
    state.ended_at = None
    state.total_paused_seconds = 0
    state.last_sequence_number = 0

    await db.flush()

    return state
