import asyncio
import random
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.base import (
    MarketEventStatus,
    MarketState,
    TradeStatus,
    TradeType,
)
from app.models.company import Company, Holding, PriceSnapshot
from app.models.market_event import MarketEvent
from app.models.market_state import MarketStateRow
from app.models.team import Team, Portfolio
from app.models.trade import Trade

from market_engine.pricing.engine import OrderFlow, compute_next_price


async def run_price_engine_loop(interval_seconds: int = 4) -> None:
    while True:
        try:
            await run_price_tick()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[MARKET ENGINE] Tick error: {exc}")

        await asyncio.sleep(interval_seconds)


async def run_price_tick() -> None:
    async with AsyncSessionLocal() as db:
        state_result = await db.execute(
            select(MarketStateRow).where(MarketStateRow.id == 1)
        )
        state = state_result.scalar_one_or_none()

        if state is None or state.state != MarketState.LIVE:
            return

        latest_snapshot_result = await db.execute(
            select(func.max(PriceSnapshot.timestamp))
        )
        last_tick_time = latest_snapshot_result.scalar_one()

        if last_tick_time is None:
            last_tick_time = state.started_at

        if last_tick_time is None:
            return

        now = datetime.now(timezone.utc)

        # ---------------------------------------------------------
        # EXECUTED TRADES SINCE THE LAST PRICE TICK
        # ---------------------------------------------------------
        trade_result = await db.execute(
            select(Trade).where(
                Trade.status == TradeStatus.EXECUTED,
                Trade.timestamp > last_tick_time,
                Trade.timestamp <= now,
            )
        )
        trades = trade_result.scalars().all()

        buy_pressure = defaultdict(lambda: Decimal("0"))
        sell_pressure = defaultdict(lambda: Decimal("0"))

        for trade in trades:
            amount = Decimal(str(trade.currency_amount))

            if trade.type == TradeType.BUY:
                buy_pressure[trade.company_id] += amount

            elif trade.type == TradeType.SELL:
                sell_pressure[trade.company_id] += amount

        # ---------------------------------------------------------
        # CRISIS / NEWS SHOCKS SINCE THE LAST PRICE TICK
        # ---------------------------------------------------------
        event_result = await db.execute(
            select(MarketEvent).where(
                MarketEvent.status == MarketEventStatus.EXECUTED,
                MarketEvent.executed_at > last_tick_time,
                MarketEvent.executed_at <= now,
            )
        )
        events = event_result.scalars().all()

        news_shocks = defaultdict(lambda: Decimal("0"))

        for event in events:
            # Use the midpoint of the configured impact range.
            impact_min = Decimal(str(event.impact_range_min))
            impact_max = Decimal(str(event.impact_range_max))
            shock = (impact_min + impact_max) / Decimal("2")

            for company_id in event.affected_company_ids or []:
                news_shocks[str(company_id)] += shock

        # ---------------------------------------------------------
        # LOCK COMPANIES AND UPDATE PRICES
        # ---------------------------------------------------------
        companies_result = await db.execute(
            select(Company).with_for_update()
        )
        companies = companies_result.scalars().all()

        state_result = await db.execute(
            select(MarketStateRow)
            .where(MarketStateRow.id == 1)
            .with_for_update()
        )
        state = state_result.scalar_one()

        state.last_sequence_number += 1
        sequence_number = state.last_sequence_number

        for company in companies:
            company_id = str(company.company_id)

            order_flow = OrderFlow(
                company_id=company_id,
                buy_pressure=buy_pressure[company.company_id],
                sell_pressure=sell_pressure[company.company_id],
            )

            new_price = compute_next_price(
                current_price=Decimal(str(company.current_price)),
                order_flow=order_flow,
                liquidity_depth=Decimal(str(company.liquidity_depth)),
                news_shock=news_shocks[company_id],
                noise=Decimal(str(random.uniform(-0.003, 0.003))),
            )

            company.current_price = new_price

            db.add(
                PriceSnapshot(
                    company_id=company.company_id,
                    price=new_price,
                    sequence_number=sequence_number,
                    timestamp=now,
                )
            )

        await recompute_portfolios(db)

        await db.commit()

        print(
            f"[MARKET ENGINE] Tick {sequence_number} | "
            f"Trades: {len(trades)} | "
            f"Events: {len(events)} | "
            f"Companies: {len(companies)}"
        )


async def recompute_portfolios(db) -> None:
    teams_result = await db.execute(select(Team))
    teams = teams_result.scalars().all()

    holdings_result = await db.execute(
        select(Holding, Company)
        .join(Company, Holding.company_id == Company.company_id)
    )
    holding_rows = holdings_result.all()

    portfolio_values = defaultdict(lambda: Decimal("0"))

    for holding, company in holding_rows:
        shares = Decimal(str(holding.shares))
        price = Decimal(str(company.current_price))

        portfolio_values[holding.team_id] += shares * price

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