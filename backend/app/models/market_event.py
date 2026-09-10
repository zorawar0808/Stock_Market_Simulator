"""MARKET_EVENTS (spec sections 9, 27, 35 - AI crisis generator)."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, JSON, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import MarketEventStatus, MarketEventType, TimestampMixin, uuid_pk


class MarketEvent(Base, TimestampMixin):
    __tablename__ = "market_events"

    event_id: Mapped[uuid.UUID] = uuid_pk()
    type: Mapped[MarketEventType] = mapped_column(SAEnum(MarketEventType, name="market_event_type"), nullable=False)
    status: Mapped[MarketEventStatus] = mapped_column(
        SAEnum(MarketEventStatus, name="market_event_status"), nullable=False, default=MarketEventStatus.PROPOSED
    )
    headline: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False, default="")

    # Company IDs affected + proposed/approved impact, stored as JSON since
    # cardinality and impact shape vary by event type (single/multi/sector/market).
    affected_company_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    impact_direction: Mapped[str] = mapped_column(String(20), nullable=False, default="NEUTRAL")  # POSITIVE/NEGATIVE/NEUTRAL/AMBIGUOUS
    impact_range_min: Mapped[float] = mapped_column(nullable=False, default=0)
    impact_range_max: Mapped[float] = mapped_column(nullable=False, default=0)

    # Provenance - was this proposed by the AI generator or created manually?
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="MANUAL")  # MANUAL / AI_GENERATED
    ai_prompt: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    ai_reasoning: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("admins.admin_id"), nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("admins.admin_id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
