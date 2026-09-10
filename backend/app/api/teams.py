"""Team + portfolio + holdings endpoints (spec sections 7, 9, 38, 40)."""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import get_current_user, require_role
from app.database import get_db
from app.models.base import AdminRole
from app.models.company import Company, Holding
from app.models.team import Portfolio, Team
from app.models.user import Admin, User
from app.schemas.team import HoldingOut, PortfolioOut, TeamCreateRequest, TeamOut
from app.services.audit_service import record as audit_record
from app.services.team_service import create_team

router = APIRouter(prefix="/api/teams", tags=["teams"])


@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def admin_create_team(
    payload: TeamCreateRequest,
    admin: Admin = Depends(require_role(AdminRole.SUPER_ADMIN, AdminRole.OPERATIONS_ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    team = await create_team(
        db,
        team_name=payload.team_name,
        max_members=payload.max_members,
        starting_capital=payload.starting_capital,
    )
    await audit_record(
        db, actor=f"admin:{admin.admin_id}", action="CREATE_TEAM",
        metadata={"team_id": str(team.team_id), "team_name": team.team_name},
    )
    await db.commit()
    return TeamOut(
        team_id=team.team_id,
        team_name=team.team_name,
        invitation_code=team.invitation_code,
        max_members=team.max_members,
        starting_capital=float(team.starting_capital),
        status=team.status.value,
        member_count=0,
    )


@router.get("/me/portfolio", response_model=PortfolioOut)
async def my_portfolio(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.team_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ACCOUNT NOT ASSIGNED TO A TEAM")
    portfolio = await db.get(Portfolio, current_user.team_id)
    if portfolio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found")
    return portfolio


@router.get("/me/holdings", response_model=list[HoldingOut])
async def my_holdings(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.team_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ACCOUNT NOT ASSIGNED TO A TEAM")

    result = await db.execute(
        select(Holding, Company)
        .join(Company, Company.company_id == Holding.company_id)
        .where(Holding.team_id == current_user.team_id, Holding.shares > 0)
    )
    rows = result.all()

    out: list[HoldingOut] = []
    for holding, company in rows:
        shares = Decimal(str(holding.shares))
        avg_price = Decimal(str(holding.average_purchase_price))
        current_price = Decimal(str(company.current_price))
        holding_value = shares * current_price
        cost_basis = shares * avg_price
        unrealized_pl = holding_value - cost_basis
        unrealized_pl_percent = (unrealized_pl / cost_basis * 100) if cost_basis > 0 else Decimal("0")

        out.append(
            HoldingOut(
                company_id=company.company_id,
                ticker=company.ticker,
                company_name=company.name,
                shares=float(shares),
                average_purchase_price=float(avg_price),
                current_price=float(current_price),
                holding_value=float(holding_value),
                unrealized_pl=float(unrealized_pl),
                unrealized_pl_percent=float(unrealized_pl_percent),
            )
        )

    # Default sort: highest holding value first (spec section 38).
    out.sort(key=lambda h: h.holding_value, reverse=True)
    return out
