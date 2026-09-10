"""
TRADES (spec sections 9-13, 56).

Every trade - executed or rejected - is recorded. The unique constraint on
(idempotency_key) is what makes retried client requests safe: a second
insert attempt with the same key raises IntegrityError, which the service
layer catches and turns into "return the original result" rather than a
second execution (spec section 13 - Idempotency).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import RejectionReason, TradeStatus, TradeType, uuid_pk


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_trades_idempotency_key"),
    )

    trade_id: Mapped[uuid.UUID] = uuid_pk()
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.team_id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.company_id", ondelete="RESTRICT"), index=True
    )

    type: Mapped[TradeType] = mapped_column(SAEnum(TradeType, name="trade_type"), nullable=False)
    currency_amount: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    shares: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
    execution_price: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)

    status: Mapped[TradeStatus] = mapped_column(SAEnum(TradeStatus, name="trade_status"), nullable=False)
    rejection_reason: Mapped[RejectionReason] = mapped_column(
        SAEnum(RejectionReason, name="rejection_reason"), nullable=False, default=RejectionReason.NONE
    )

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    team: Mapped["Team"] = relationship(back_populates="trades")
    user: Mapped["User"] = relationship(back_populates="trades")
    company: Mapped["Company"] = relationship(back_populates="trades")
