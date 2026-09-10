"""
Concurrency correctness tests (spec sections 12-14, 59).

Requires a real PostgreSQL instance pointed to by DATABASE_URL in backend/.env.

These tests use pytest-asyncio with a session-scoped event loop so the
module-level SQLAlchemy asyncpg engine/pool remains on one event loop for
the entire test session.

The tests rely on genuine SELECT ... FOR UPDATE row locking.
"""

import asyncio
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.database import AsyncSessionLocal, engine
from app.models.company import Company, Holding
from app.models.team import Portfolio
from app.services import market_service, trading_service
from app.services.team_service import create_team, register_participant


# ---------------------------------------------------------------------------
# Pytest / event-loop configuration
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _dispose_engine():
    """
    Dispose the global SQLAlchemy async engine on the same event loop used
    by the entire test session.

    This prevents asyncpg connections from being reused across different
    event loops.
    """
    yield

    await engine.dispose()


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

async def _ensure_market_live() -> None:
    """
    Ensure the singleton market is LIVE before a test begins.

    Tests may leave the market PAUSED, FROZEN, ENDING, or CLOSED, so this
    helper normalizes it back into a usable LIVE state.
    """
    async with AsyncSessionLocal() as db:
        state = await market_service.get_or_create_state(db)

        if state.state.value == "LIVE":
            await db.commit()
            return

        if state.state.value == "WAITING":
            await market_service.start_market(db)

        elif state.state.value == "PAUSED":
            await market_service.resume_market(db)

        elif state.state.value == "EMERGENCY_FROZEN":
            await market_service.unfreeze_to_live(db)

        elif state.state.value in ("ENDING", "CLOSED"):
            # Test-only recovery.
            state.state = market_service.MarketState.WAITING
            state.started_at = None
            state.paused_at = None
            state.ended_at = None
            state.total_paused_seconds = 0
            state.last_sequence_number = 0

            await db.flush()

            await market_service.start_market(db)

        await db.commit()


async def _make_company(current_price=100.0) -> uuid.UUID:
    """
    Create an isolated test company.
    """
    async with AsyncSessionLocal() as db:
        company = Company(
            name=f"TestCo-{uuid.uuid4().hex[:8]}",
            ticker=uuid.uuid4().hex[:6].upper(),
            sector="Test",
            description="Test company",
            initial_price=current_price,
            current_price=current_price,
            liquidity_depth=100000,
            fundamentals={},
            relationships={},
        )

        db.add(company)

        await db.commit()
        await db.refresh(company)

        return company.company_id


async def _setup_team_user_company(
    starting_capital=10000.0,
    price=100.0,
):
    """
    Create a fresh team, participant, and company for each test.
    """
    async with AsyncSessionLocal() as db:
        team = await create_team(
            db,
            team_name=f"Team-{uuid.uuid4().hex[:8]}",
            max_members=3,
            starting_capital=starting_capital,
        )

        team_id = team.team_id
        invite = team.invitation_code

        await db.commit()

    async with AsyncSessionLocal() as db:
        user = await register_participant(
            db,
            name="Tester",
            email=f"{uuid.uuid4().hex[:10]}@example.com",
            password="password123",
            invitation_code=invite,
        )

        user_id = user.user_id

        await db.commit()

    company_id = await _make_company(current_price=price)

    await _ensure_market_live()

    return team_id, user_id, company_id


# ---------------------------------------------------------------------------
# Spec 12 — concurrent BUY
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_buy_buy_never_overdraws():
    """
    Spec 12:

    Two teammates simultaneously BUY the team's entire cash balance.

    Exactly one transaction must succeed and the other must be rejected.
    The team's cash must never become negative.
    """
    team_id, user_id, company_id = await _setup_team_user_company(
        starting_capital=1000.0
    )

    async def buy(key):
        async with AsyncSessionLocal() as db:
            trade = await trading_service.execute_buy(
                db,
                team_id=team_id,
                user_id=user_id,
                company_id=company_id,
                amount=1000.0,
                idempotency_key=key,
            )

            # Direct service calls are responsible for their own transaction
            # in this test. Commit before releasing the row lock/session.
            await db.commit()

            return trade

    # Keys must be unique because idempotency_key is globally unique.
    t1, t2 = await asyncio.gather(
        buy(f"buy-a-{uuid.uuid4()}"),
        buy(f"buy-b-{uuid.uuid4()}"),
    )

    statuses = sorted([
        t1.status.value,
        t2.status.value,
    ])

    assert statuses == [
        "EXECUTED",
        "REJECTED",
    ], "Exactly one of the two concurrent buys must succeed"

    async with AsyncSessionLocal() as db:
        portfolio = await db.get(Portfolio, team_id)

        assert portfolio is not None
        assert float(portfolio.cash) >= 0
        assert float(portfolio.cash) == 0.0, (
            "Winning buy should have spent exactly the available cash"
        )


# ---------------------------------------------------------------------------
# Spec 12 — concurrent SELL
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_sell_sell_never_oversells():
    """
    Spec 12:

    Two teammates simultaneously SELL the team's entire share balance.

    Exactly one transaction must succeed and the other must be rejected.
    The holding must be completely liquidated and must never become negative.
    """
    team_id, user_id, company_id = await _setup_team_user_company(
        starting_capital=1000.0,
        price=100.0,
    )

    # First buy the entire portfolio so there is something to sell.
    async with AsyncSessionLocal() as db:
        buy_trade = await trading_service.execute_buy(
            db,
            team_id=team_id,
            user_id=user_id,
            company_id=company_id,
            amount=1000.0,
            idempotency_key=f"initial-buy-{uuid.uuid4()}",
        )

        # IMPORTANT:
        # execute_buy() is called directly here rather than through the API
        # endpoint. Persist the transaction before opening the concurrent
        # SELL transactions.
        await db.commit()

        assert buy_trade.status.value == "EXECUTED"
        assert buy_trade.shares is not None

        owned_shares = float(buy_trade.shares)

    async def sell(key):
        async with AsyncSessionLocal() as db:
            trade = await trading_service.execute_sell(
                db,
                team_id=team_id,
                user_id=user_id,
                company_id=company_id,
                idempotency_key=key,
                shares=owned_shares,
            )

            # Commit while this transaction still owns any row locks.
            await db.commit()

            return trade

    t1, t2 = await asyncio.gather(
        sell(f"sell-a-{uuid.uuid4()}"),
        sell(f"sell-b-{uuid.uuid4()}"),
    )

    statuses = sorted([
        t1.status.value,
        t2.status.value,
    ])

    assert statuses == [
        "EXECUTED",
        "REJECTED",
    ], "Exactly one of the two concurrent sells must succeed"

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Holding).where(
                Holding.team_id == team_id,
                Holding.company_id == company_id,
            )
        )

        remaining = result.scalar_one_or_none()

        assert remaining is None, (
            "Holding should be fully liquidated, not partially or double-sold"
        )


# ---------------------------------------------------------------------------
# Spec 13 — idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_idempotency_key_replay_does_not_reexecute():
    """
    Spec 13:

    Retrying an already accepted trade with the same idempotency key must
    return the original trade rather than executing another trade.
    """
    team_id, user_id, company_id = await _setup_team_user_company(
        starting_capital=1000.0
    )

    idempotency_key = f"dupe-key-{uuid.uuid4()}"

    # First request.
    async with AsyncSessionLocal() as db:
        first = await trading_service.execute_buy(
            db,
            team_id=team_id,
            user_id=user_id,
            company_id=company_id,
            amount=500.0,
            idempotency_key=idempotency_key,
        )

        assert first.status.value == "EXECUTED"

        # Persist the original transaction before replaying it from another
        # database session.
        await db.commit()

    # Replay the exact same request.
    async with AsyncSessionLocal() as db:
        second = await trading_service.execute_buy(
            db,
            team_id=team_id,
            user_id=user_id,
            company_id=company_id,
            amount=500.0,
            idempotency_key=idempotency_key,
        )

        await db.commit()

    assert first.trade_id == second.trade_id, (
        "Replaying the same idempotency key must return the same trade"
    )

    async with AsyncSessionLocal() as db:
        portfolio = await db.get(Portfolio, team_id)

        assert portfolio is not None
        assert float(portfolio.cash) == 500.0, (
            "Cash must only be deducted once despite the replayed request"
        )


# ---------------------------------------------------------------------------
# Spec 14 / 58 — paused market rejection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_buy_rejected_when_market_paused():
    """
    Spec 14, 58:

    Trading must be rejected while the market is PAUSED, with the correct
    rejection reason.
    """
    team_id, user_id, company_id = await _setup_team_user_company()

    # Pause the market and COMMIT the state transition before opening the
    # separate session that attempts the trade.
    async with AsyncSessionLocal() as db:
        await market_service.pause_market(db)
        await db.commit()

    try:
        async with AsyncSessionLocal() as db:
            trade = await trading_service.execute_buy(
                db,
                team_id=team_id,
                user_id=user_id,
                company_id=company_id,
                amount=100.0,
                idempotency_key=f"buy-during-pause-{uuid.uuid4()}",
            )

            await db.commit()

        assert trade.status.value == "REJECTED"
        assert trade.rejection_reason.value == "MARKET_PAUSED"

    finally:
        # Always restore LIVE state, even if the assertions above fail.
        async with AsyncSessionLocal() as db:
            state = await market_service.get_or_create_state(db)

            if state.state.value == "PAUSED":
                await market_service.resume_market(db)

            await db.commit()