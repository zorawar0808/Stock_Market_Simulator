"""
Admin market controls (spec sections 18, 51). Every control action is
audit-logged with the specific admin who performed it — never a shared
account (spec section 8).
"""
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import require_role
from app.database import get_db
from app.models.base import AdminRole
from app.models.user import Admin
from app.services import market_service
from app.services.audit_service import record as audit_record
from vercel.queue import send
from app.services.market_tick_queue import (
    MARKET_TICK_TOPIC,
    MarketTickPayload,
)

router = APIRouter(prefix="/api/admin/market", tags=["admin-market"])

_CONTROL_ADMIN_ROLES = (AdminRole.SUPER_ADMIN, AdminRole.OPERATIONS_ADMIN)
# Emergency freeze must be reachable by MONITOR_ADMIN too (spec section 8:
# monitor admins "primarily handle... emergency freeze").
_FREEZE_ADMIN_ROLES = (AdminRole.SUPER_ADMIN, AdminRole.OPERATIONS_ADMIN, AdminRole.MONITOR_ADMIN)


async def _run(
    action_name: str,
    fn,
    admin: Admin,
    db: AsyncSession,
    *,
    start_price_engine: bool = False,
):
    try:
        state = await fn(db)
    except market_service.InvalidTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot {action_name}: market is currently {exc.current.value}",
        )

    await audit_record(
        db,
        actor=f"admin:{admin.admin_id}",
        action=action_name.upper(),
        metadata={"resulting_state": state.state.value},
    )

    # Commit the state transition BEFORE enqueueing the worker.
    # The worker must never see an uncommitted LIVE state.
    await db.commit()

    if start_price_engine:
        sequence = int(state.last_sequence_number)
        run_id = state.started_at.isoformat() if state.started_at else "unknown"

        await send(
            MARKET_TICK_TOPIC,
            MarketTickPayload(
                expected_sequence=sequence,
                run_id=run_id,
            ),
            idempotency_key=f"market-kickoff-{run_id}-{uuid4()}",
            delay=timedelta(seconds=1),
        )

    return {"state": state.state.value}


@router.post("/start")
async def start(admin: Admin = Depends(require_role(*_CONTROL_ADMIN_ROLES)), db: AsyncSession = Depends(get_db)):
    return await _run("market start", market_service.start_market, admin, db, start_price_engine=True)


@router.post("/pause")
async def pause(admin: Admin = Depends(require_role(*_CONTROL_ADMIN_ROLES)), db: AsyncSession = Depends(get_db)):
    return await _run("market pause", market_service.pause_market, admin, db)


@router.post("/resume")
async def resume(admin: Admin = Depends(require_role(*_CONTROL_ADMIN_ROLES)), db: AsyncSession = Depends(get_db)):
    return await _run("market resume", market_service.resume_market, admin, db, start_price_engine=True)


@router.post("/end")
async def end(admin: Admin = Depends(require_role(*_CONTROL_ADMIN_ROLES)), db: AsyncSession = Depends(get_db)):
    # NOTE: this only performs the state transition (ENDING -> CLOSED). Full
    # settlement (final price capture, portfolio valuation, ranking, locking
    # the leaderboard — spec section 61) still needs to be wired in here
    # before this is production-ready. See README "What to build next".
    return await _run("market end", market_service.end_market, admin, db)


@router.post("/emergency-freeze")
async def emergency_freeze(
    admin: Admin = Depends(require_role(*_FREEZE_ADMIN_ROLES)), db: AsyncSession = Depends(get_db)
):
    return await _run("emergency freeze", market_service.emergency_freeze, admin, db)


@router.post("/unfreeze")
async def unfreeze(
    admin: Admin = Depends(require_role(*_FREEZE_ADMIN_ROLES)), db: AsyncSession = Depends(get_db)
):
    return await _run("unfreeze", market_service.unfreeze_to_live, admin, db, start_price_engine=True)


@router.post("/reset-to-original")
async def reset_to_original(
    admin: Admin = Depends(require_role(*_CONTROL_ADMIN_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    try:
        state = await market_service.reset_market_to_original(db)
    except market_service.MarketResetBlocked as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Cannot reset market while it is LIVE. "
                "Pause or emergency-freeze the market first."
            ),
        )

    await audit_record(
        db,
        actor=f"admin:{admin.admin_id}",
        action="MARKET_RESET_TO_ORIGINAL",
        metadata={
            "resulting_state": state.state.value,
            "description": (
                "Restored all company prices to initial prices, "
                "cleared price snapshots, and recalculated portfolios."
            ),
        },
    )

    await db.commit()

    return {
        "status": "reset",
        "state": state.state.value,
    }
