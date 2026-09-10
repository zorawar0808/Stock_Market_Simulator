"""
Singleton MARKET_STATE row (spec sections 14-20).

A single-row table (id is always 1) is the authoritative state machine.
Booleans-as-state is explicitly forbidden by the spec; this table stores one
enum column plus the timing fields needed to compute "paused time doesn't
count toward duration" on resume.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import MarketState


class MarketStateRow(Base):
    __tablename__ = "market_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    state: Mapped[MarketState] = mapped_column(
        SAEnum(MarketState, name="market_state_enum"), nullable=False, default=MarketState.WAITING
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_paused_seconds: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Global monotonic counter for WebSocket sequence numbers (spec section 48)
    last_sequence_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
