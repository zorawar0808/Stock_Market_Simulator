"""
TEAMS and PORTFOLIOS (spec section 9).

A team's cash/holdings are the shared authoritative financial state for
every participant on that team. Portfolio is 1:1 with Team but kept as a
separate table so it can be locked (`SELECT ... FOR UPDATE`) independently
of team metadata during trade execution (spec section 12 - Atomic Concurrency).
"""
import uuid

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Numeric, String, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TeamStatus, TimestampMixin, uuid_pk


class Team(Base, TimestampMixin):
    __tablename__ = "teams"

    team_id: Mapped[uuid.UUID] = uuid_pk()
    team_name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    invitation_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    max_members: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    starting_capital: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=10000)
    status: Mapped[TeamStatus] = mapped_column(
        SAEnum(TeamStatus, name="team_status"), nullable=False, default=TeamStatus.ACTIVE
    )

    users: Mapped[list["User"]] = relationship(back_populates="team")
    portfolio: Mapped["Portfolio"] = relationship(back_populates="team", uselist=False)
    holdings: Mapped[list["Holding"]] = relationship(back_populates="team")
    trades: Mapped[list["Trade"]] = relationship(back_populates="team")

    @property
    def member_count(self) -> int:
        return len(self.users)


class Portfolio(Base, TimestampMixin):
    """
    Shared financial state for a team. This row is the lock target for
    every BUY/SELL (see services/trading_service.py) so that concurrent
    teammate trades against the same team serialize correctly instead of
    racing on cash.
    """
    __tablename__ = "portfolios"

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.team_id", ondelete="CASCADE"), primary_key=True
    )
    cash: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    # Denormalized, recomputed by the market engine every tick (spec section 21)
    # and also recomputable on-demand from holdings + current prices.
    portfolio_value: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    net_worth: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    return_percent: Mapped[float] = mapped_column(Numeric(9, 4), nullable=False, default=0)

    team: Mapped["Team"] = relationship(back_populates="portfolio")
