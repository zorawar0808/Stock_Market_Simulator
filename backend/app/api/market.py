"""
Market status, companies and leaderboard endpoints.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.company import Company
from app.models.team import Portfolio, Team
from app.schemas.company import CompanyOut
from app.services import market_service

router = APIRouter(prefix="/api/market", tags=["market"])


def _compute_remaining_seconds(row) -> float | None:
    if row.started_at is None:
        return None

    now = datetime.now(timezone.utc)
    reference_time = row.paused_at if row.paused_at is not None else now
    elapsed = (
        reference_time - row.started_at
    ).total_seconds() - float(row.total_paused_seconds)

    return max(0.0, float(row.duration_seconds) - elapsed)


@router.get("/status")
async def market_status(db: AsyncSession = Depends(get_db)):
    row = await market_service.get_or_create_state(db)
    await db.commit()

    remaining = _compute_remaining_seconds(row)

    return {
        "state": row.state.value,
        "started_at": row.started_at,
        "duration_seconds": row.duration_seconds,
        "remaining_seconds": remaining,
        "server_time": datetime.now(timezone.utc),
    }


@router.get("/companies", response_model=list[CompanyOut])
async def companies(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Company)
        .where(Company.status == "ACTIVE")
        .order_by(Company.ticker)
    )

    companies = result.scalars().all()

    return [
        CompanyOut(
            company_id=str(company.company_id),
            name=company.name,
            ticker=company.ticker,
            sector=company.sector,
            description=company.description,
            initial_price=float(company.initial_price),
            current_price=float(company.current_price),
        )
        for company in companies
    ]


@router.get("/leaderboard")
async def leaderboard(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Team.team_id, Team.team_name, Portfolio)
        .join(Portfolio, Portfolio.team_id == Team.team_id)
        .order_by(Portfolio.net_worth.desc())
    )

    rows = result.all()

    return [
        {
            "rank": idx + 1,
            "team_id": str(team_id),
            "team_name": team_name,
            "cash": float(portfolio.cash),
            "portfolio_value": float(portfolio.portfolio_value),
            "net_worth": float(portfolio.net_worth),
            "return_percent": float(portfolio.return_percent),
        }
        for idx, (team_id, team_name, portfolio) in enumerate(rows)
    ]


@router.get("/companies/{company_id}/history")
async def company_price_history(
    company_id: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        import uuid

        company_uuid = uuid.UUID(company_id)
    except ValueError:
        return []

    from app.models.company import PriceSnapshot

    result = await db.execute(
        select(PriceSnapshot)
        .where(PriceSnapshot.company_id == company_uuid)
        .order_by(PriceSnapshot.timestamp.desc())
        .limit(500)
    )

    snapshots = list(reversed(result.scalars().all()))

    return [
        {
            "price": float(snapshot.price),
            "sequence_number": snapshot.sequence_number,
            "timestamp": snapshot.timestamp,
        }
        for snapshot in snapshots
    ]
