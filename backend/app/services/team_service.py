"""
Team creation and participant registration (spec section 7).

Invitation codes are validated for capacity here, inside the same
transaction as the user insert, using a row lock on the team so two
participants racing to grab the last open slot on a team can't both
succeed.
"""
import random
import string
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.models.base import TeamStatus, UserStatus
from app.models.team import Portfolio, Team
from app.models.user import User


class RegistrationError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _generate_invitation_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choices(alphabet, k=length))


async def create_team(
    db: AsyncSession,
    *,
    team_name: str,
    max_members: int,
    starting_capital: float,
) -> Team:
    code = _generate_invitation_code()
    # Extremely unlikely to collide, but guard anyway.
    for _ in range(5):
        exists = await db.execute(select(Team).where(Team.invitation_code == code))
        if exists.scalar_one_or_none() is None:
            break
        code = _generate_invitation_code()

    team = Team(
        team_name=team_name,
        invitation_code=code,
        max_members=max_members,
        starting_capital=starting_capital,
        status=TeamStatus.ACTIVE,
    )
    db.add(team)
    await db.flush()  # populate team.team_id

    portfolio = Portfolio(
        team_id=team.team_id,
        cash=starting_capital,
        portfolio_value=0,
        net_worth=starting_capital,
        return_percent=0,
    )
    db.add(portfolio)
    await db.commit()
    await db.refresh(team)
    return team


async def register_participant(
    db: AsyncSession,
    *,
    name: str,
    email: str,
    password: str,
    invitation_code: str,
) -> User:
    # NOTE: relies on AsyncSession's implicit autobegin rather than an
    # explicit `async with db.begin()` block. Explicit begin() raises
    # InvalidRequestError if this session already has an autobegun
    # transaction in flight (e.g. because a caller committed a prior
    # operation on the same session earlier in the request) — autobegin +
    # explicit commit/rollback is the robust pattern used throughout this
    # codebase (see trading_service.py).
    team = (
        await db.execute(
            select(Team).where(Team.invitation_code == invitation_code).with_for_update()
        )
    ).scalar_one_or_none()
    if team is None:
        await db.rollback()
        raise RegistrationError("Invalid invitation code")
    if team.status != TeamStatus.ACTIVE:
        await db.rollback()
        raise RegistrationError("This team is not currently accepting new members")

    member_count = (
        await db.execute(select(func.count()).select_from(User).where(User.team_id == team.team_id))
    ).scalar_one()
    if member_count >= team.max_members:
        await db.rollback()
        raise RegistrationError("This team has reached its maximum number of participants")

    user = User(
        name=name,
        email=email,
        password_hash=hash_password(password),
        team_id=team.team_id,
        status=UserStatus.PENDING_VERIFICATION,
        email_verified=False,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise RegistrationError("An account with this email already exists")

    await db.refresh(user)
    return user
