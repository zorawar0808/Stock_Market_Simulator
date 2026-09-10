"""
The core BUY/SELL engine (spec sections 10-13).

Design invariants enforced here, not trusted from the client:
  - The client sends a currency `amount` (BUY) or amount/shares/sell_all
    (SELL). The server always computes shares and execution price.
  - Every mutation to team cash/holdings happens inside one DB transaction
    that holds a `SELECT ... FOR UPDATE` lock on that team's Portfolio row.
    Two teammates racing to spend the same cash therefore serialize: the
    second transaction blocks until the first commits, then re-reads the
    now-updated cash balance and is correctly rejected if it would overdraw.
  - Every trade attempt (successful or rejected) is persisted with a unique
    idempotency_key. If a client retries a request whose response it never
    saw, we detect the duplicate key and return the original result instead
    of executing (or re-rejecting) anything twice.
  - Market state is checked inside the same locked transaction so a trade
    can't sneak through between a PAUSE/FREEZE/CLOSE and the price read.
"""
import uuid
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import CompanyStatus, MarketState, RejectionReason, TradeStatus, TradeType
from app.models.company import Company, Holding
from app.models.team import Portfolio
from app.models.market_state import MarketStateRow
from app.models.trade import Trade
from app.services.exceptions import TradeRejected

SHARE_PRECISION = Decimal("0.000001")
CURRENCY_PRECISION = Decimal("0.0001")


def _q_shares(value: Decimal) -> Decimal:
    return value.quantize(SHARE_PRECISION, rounding=ROUND_DOWN)


def _q_currency(value: Decimal) -> Decimal:
    return value.quantize(CURRENCY_PRECISION, rounding=ROUND_DOWN)


async def _find_existing_trade(db: AsyncSession, idempotency_key: str) -> Trade | None:
    result = await db.execute(select(Trade).where(Trade.idempotency_key == idempotency_key))
    return result.scalar_one_or_none()


async def _load_market_state(db: AsyncSession) -> MarketStateRow:
    state = await db.get(MarketStateRow, 1)
    if state is None:
        # Should never happen once seeded, but fail closed rather than open.
        raise TradeRejected(RejectionReason.MARKET_CLOSED, "Market has not been initialized")
    return state


def _assert_market_open_for_trading(state: MarketStateRow) -> None:
    if state.state == MarketState.PAUSED:
        raise TradeRejected(RejectionReason.MARKET_PAUSED, "Market is currently paused")
    if state.state == MarketState.EMERGENCY_FROZEN:
        raise TradeRejected(RejectionReason.MARKET_FROZEN, "Market is in emergency freeze")
    if state.state in (MarketState.CLOSED, MarketState.ENDING):
        raise TradeRejected(RejectionReason.MARKET_CLOSED, "Market is closed")
    if state.state == MarketState.WAITING:
        raise TradeRejected(RejectionReason.MARKET_CLOSED, "Market has not started yet")
    # Only MarketState.LIVE reaches here.


async def _record_rejected_trade(
    db: AsyncSession,
    *,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    company_id: uuid.UUID,
    trade_type: TradeType,
    amount: Decimal,
    price: Decimal,
    idempotency_key: str,
    reason: RejectionReason,
) -> Trade:
    trade = Trade(
        team_id=team_id,
        user_id=user_id,
        company_id=company_id,
        type=trade_type,
        currency_amount=amount,
        shares=Decimal("0"),
        execution_price=price,
        status=TradeStatus.REJECTED,
        rejection_reason=reason,
        idempotency_key=idempotency_key,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(trade)
    return trade


async def execute_buy(
    db: AsyncSession,
    *,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    company_id: uuid.UUID,
    amount: float,
    idempotency_key: str,
) -> Trade:
    """
    Executes (or rejects) a BUY order atomically. Returns the persisted
    Trade row either way - callers/API layer decide the HTTP status from
    `trade.status` / `trade.rejection_reason`.

    Note: this relies on AsyncSession's implicit autobegin plus an explicit
    commit/rollback at the end, rather than `async with db.begin():`. The
    idempotency-check SELECT below already autobegins a transaction on this
    session, so wrapping the rest in an explicit `db.begin()` afterwards
    would raise "A transaction is already begun on this Session" - the
    whole point of autobegin is that you never need to open one yourself.
    """
    existing = await _find_existing_trade(db, idempotency_key)
    if existing is not None:
        return existing

    amount_dec = _q_currency(Decimal(str(amount)))
    company: Company | None = None

    try:
        # Lock the team's portfolio row first - this is the single
        # serialization point for all concurrent trades by this team.
        portfolio = (
            await db.execute(
                select(Portfolio).where(Portfolio.team_id == team_id).with_for_update()
            )
        ).scalar_one_or_none()
        if portfolio is None:
            raise TradeRejected(RejectionReason.INVALID_ORDER, "Team has no portfolio")

        company = await db.get(Company, company_id)
        if company is None:
            raise TradeRejected(RejectionReason.INVALID_ORDER, "Unknown company")

        market_state = await _load_market_state(db)

        try:
            _assert_market_open_for_trading(market_state)
            if company.status != CompanyStatus.ACTIVE:
                raise TradeRejected(RejectionReason.COMPANY_HALTED, f"{company.ticker} is halted")

            current_cash = Decimal(str(portfolio.cash))
            if amount_dec > current_cash:
                raise TradeRejected(
                    RejectionReason.INSUFFICIENT_FUNDS,
                    f"Order value {amount_dec} exceeds available cash {current_cash}",
                )

            price = Decimal(str(company.current_price))
            shares = _q_shares(amount_dec / price)
            if shares <= 0:
                raise TradeRejected(RejectionReason.INVALID_ORDER, "Order too small to acquire any shares")

            # --- Mutate authoritative state ---
            portfolio.cash = current_cash - amount_dec

            holding = (
                await db.execute(
                    select(Holding).where(
                        Holding.team_id == team_id, Holding.company_id == company_id
                    )
                )
            ).scalar_one_or_none()

            if holding is None:
                holding = Holding(
                    team_id=team_id,
                    company_id=company_id,
                    shares=shares,
                    average_purchase_price=price,
                )
                db.add(holding)
            else:
                old_shares = Decimal(str(holding.shares))
                old_avg = Decimal(str(holding.average_purchase_price))
                new_total_shares = old_shares + shares
                holding.average_purchase_price = _q_currency(
                    ((old_shares * old_avg) + (shares * price)) / new_total_shares
                )
                holding.shares = new_total_shares

            trade = Trade(
                team_id=team_id,
                user_id=user_id,
                company_id=company_id,
                type=TradeType.BUY,
                currency_amount=amount_dec,
                shares=shares,
                execution_price=price,
                status=TradeStatus.EXECUTED,
                rejection_reason=RejectionReason.NONE,
                idempotency_key=idempotency_key,
                timestamp=datetime.now(timezone.utc),
            )
            db.add(trade)

        except TradeRejected as rejection:
            price_at_rejection = Decimal(str(company.current_price)) if company else Decimal("0")
            trade = await _record_rejected_trade(
                db,
                team_id=team_id,
                user_id=user_id,
                company_id=company_id,
                trade_type=TradeType.BUY,
                amount=amount_dec,
                price=price_at_rejection,
                idempotency_key=idempotency_key,
                reason=rejection.reason,
            )

        await db.commit()
        await db.refresh(trade)
        return trade

    except IntegrityError:
        # Lost the race on the idempotency_key unique constraint - someone
        # else's identical retry landed first. Return their result.
        await db.rollback()
        existing = await _find_existing_trade(db, idempotency_key)
        if existing is not None:
            return existing
        raise
    except Exception:
        await db.rollback()
        raise


async def execute_sell(
    db: AsyncSession,
    *,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    company_id: uuid.UUID,
    idempotency_key: str,
    amount: float | None = None,
    shares: float | None = None,
    sell_all: bool = False,
) -> Trade:
    """
    Executes (or rejects) a SELL order atomically. Exactly one of
    amount / shares / sell_all should be provided (validated by the
    Pydantic schema at the API layer). See execute_buy's docstring for why
    this uses autobegin + explicit commit/rollback rather than
    `async with db.begin():`.
    """
    existing = await _find_existing_trade(db, idempotency_key)
    if existing is not None:
        return existing

    company: Company | None = None

    try:
        portfolio = (
            await db.execute(
                select(Portfolio).where(Portfolio.team_id == team_id).with_for_update()
            )
        ).scalar_one_or_none()
        if portfolio is None:
            raise TradeRejected(RejectionReason.INVALID_ORDER, "Team has no portfolio")

        company = await db.get(Company, company_id)
        if company is None:
            raise TradeRejected(RejectionReason.INVALID_ORDER, "Unknown company")

        market_state = await _load_market_state(db)

        holding = (
            await db.execute(
                select(Holding).where(Holding.team_id == team_id, Holding.company_id == company_id)
            )
        ).scalar_one_or_none()

        requested_amount_for_audit = Decimal(str(amount)) if amount is not None else Decimal("0")

        try:
            _assert_market_open_for_trading(market_state)
            if company.status != CompanyStatus.ACTIVE:
                raise TradeRejected(RejectionReason.COMPANY_HALTED, f"{company.ticker} is halted")
            if holding is None or Decimal(str(holding.shares)) <= 0:
                raise TradeRejected(RejectionReason.INSUFFICIENT_SHARES, "Team holds no shares of this company")

            price = Decimal(str(company.current_price))
            owned_shares = Decimal(str(holding.shares))

            if sell_all:
                shares_to_sell = owned_shares
            elif shares is not None:
                shares_to_sell = _q_shares(Decimal(str(shares)))
            elif amount is not None:
                shares_to_sell = _q_shares(Decimal(str(amount)) / price)
            else:
                raise TradeRejected(RejectionReason.INVALID_ORDER, "No sell quantity specified")

            if shares_to_sell <= 0:
                raise TradeRejected(RejectionReason.INVALID_ORDER, "Order too small")
            if shares_to_sell > owned_shares:
                raise TradeRejected(
                    RejectionReason.INSUFFICIENT_SHARES,
                    f"Requested {shares_to_sell} shares but team only owns {owned_shares}",
                )

            proceeds = _q_currency(shares_to_sell * price)

            # --- Mutate authoritative state ---
            portfolio.cash = Decimal(str(portfolio.cash)) + proceeds
            remaining_shares = owned_shares - shares_to_sell
            if remaining_shares <= 0:
                await db.delete(holding)
            else:
                holding.shares = remaining_shares
                # average_purchase_price is unchanged by a partial sell

            trade = Trade(
                team_id=team_id,
                user_id=user_id,
                company_id=company_id,
                type=TradeType.SELL,
                currency_amount=proceeds,
                shares=shares_to_sell,
                execution_price=price,
                status=TradeStatus.EXECUTED,
                rejection_reason=RejectionReason.NONE,
                idempotency_key=idempotency_key,
                timestamp=datetime.now(timezone.utc),
            )
            db.add(trade)

        except TradeRejected as rejection:
            price_at_rejection = Decimal(str(company.current_price)) if company else Decimal("0")
            trade = await _record_rejected_trade(
                db,
                team_id=team_id,
                user_id=user_id,
                company_id=company_id,
                trade_type=TradeType.SELL,
                amount=requested_amount_for_audit,
                price=price_at_rejection,
                idempotency_key=idempotency_key,
                reason=rejection.reason,
            )

        await db.commit()
        await db.refresh(trade)
        return trade

    except IntegrityError:
        await db.rollback()
        existing = await _find_existing_trade(db, idempotency_key)
        if existing is not None:
            return existing
        raise
    except Exception:
        await db.rollback()
        raise
