"""
Participant trading endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import get_current_user
from app.database import get_db
from app.models.trade import Trade
from app.models.user import User
from app.schemas.trade import BuyRequest, SellRequest, TradeOut
from app.services import trading_service

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.post("/buy", response_model=TradeOut)
async def buy(
    payload: BuyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.team_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ACCOUNT NOT ASSIGNED TO A TEAM",
        )

    trade = await trading_service.execute_buy(
        db,
        team_id=current_user.team_id,
        user_id=current_user.user_id,
        company_id=payload.company_id,
        amount=payload.amount,
        idempotency_key=payload.idempotency_key,
    )

    return trade


@router.post("/sell", response_model=TradeOut)
async def sell(
    payload: SellRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.team_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ACCOUNT NOT ASSIGNED TO A TEAM",
        )

    trade = await trading_service.execute_sell(
        db,
        team_id=current_user.team_id,
        user_id=current_user.user_id,
        company_id=payload.company_id,
        idempotency_key=payload.idempotency_key,
        amount=payload.amount,
        shares=payload.shares,
        sell_all=payload.sell_all,
    )

    return trade


@router.get("/history", response_model=list[TradeOut])
async def trade_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.team_id is None:
        return []

    result = await db.execute(
        select(Trade)
        .where(Trade.team_id == current_user.team_id)
        .order_by(Trade.timestamp.desc())
        .limit(100)
    )

    return result.scalars().all()
