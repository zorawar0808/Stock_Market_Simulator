from datetime import timedelta

from sqlalchemy import select
from vercel.queue import send, subscribe

from app.database import AsyncSessionLocal
from app.models.base import MarketState
from app.models.market_state import MarketStateRow
from app.services.market_tick_queue import (
    MARKET_TICK_TOPIC,
    TICK_DELAY_SECONDS,
    MarketTickPayload,
)
from market_engine.simulation.clock import run_price_tick


async def get_market_sequence() -> int | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MarketStateRow.last_sequence_number).where(
                MarketStateRow.id == 1
            )
        )
        return result.scalar_one_or_none()


async def market_is_live() -> bool:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(MarketStateRow.state).where(
                MarketStateRow.id == 1
            )
        )
        state = result.scalar_one_or_none()
        return state == MarketState.LIVE


@subscribe(
    topic=MARKET_TICK_TOPIC,
    consumer_group="esummit-market-engine",
    max_concurrency=1,
)
async def process_market_tick(message: MarketTickPayload) -> None:
    expected_sequence = message.expected_sequence
    run_id = message.run_id

    # Vercel Queues is at-least-once.
    #
    # run_price_tick() locks market_state and checks the expected sequence,
    # preventing a redelivered/stale message from executing the same tick twice.
    await run_price_tick(expected_sequence=expected_sequence)

    if not await market_is_live():
        return

    current_sequence = await get_market_sequence()

    if current_sequence is None:
        return

    await send(
        MARKET_TICK_TOPIC,
        MarketTickPayload(
            expected_sequence=current_sequence,
            run_id=run_id,
        ),
        idempotency_key=f"market-tick-{run_id}-{current_sequence}",
        delay=timedelta(seconds=TICK_DELAY_SECONDS),
    )
