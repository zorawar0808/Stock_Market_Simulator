"""
COMPANIES, HOLDINGS, PRICE_SNAPSHOTS (spec sections 9, 21-26).

Hidden fundamentals/liquidity/relationships live on the company row but are
explicitly excluded from any participant-facing Pydantic schema (see
app/schemas) - never serialized to the API or WebSocket payloads verbatim.
"""
import uuid

from sqlalchemy import BigInteger, DateTime, Enum as SAEnum, ForeignKey, JSON, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import CompanyStatus, TimestampMixin, uuid_pk


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    company_id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    ticker: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    sector: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False, default="")

    initial_price: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    current_price: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    status: Mapped[CompanyStatus] = mapped_column(
        SAEnum(CompanyStatus, name="company_status"), nullable=False, default=CompanyStatus.ACTIVE
    )

    # --- Hidden, organizer-only fields (spec sections 23-25). NEVER exposed
    # via a participant-facing schema. ---
    liquidity_depth: Mapped[float] = mapped_column(
        Numeric(14, 4), nullable=False, default=100000,
        doc="Higher = more capital required to move price significantly. Hidden.",
    )
    fundamentals: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict,
        doc="Hidden attributes: technology, marketing, talent, patents, "
            "partnerships, regulatory/geographic/commodity/debt/consumer/"
            "supply-chain exposure, etc. Never serialized to participants.",
    )
    relationships: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict,
        doc="Hidden cross-company relationships: suppliers, customers, "
            "competitors, partners, dependencies. Never exposed unless an "
            "admin intentionally publishes it via a newsletter/news item.",
    )

    holdings: Mapped[list["Holding"]] = relationship(back_populates="company")
    trades: Mapped[list["Trade"]] = relationship(back_populates="company")
    price_snapshots: Mapped[list["PriceSnapshot"]] = relationship(back_populates="company")


class Holding(Base, TimestampMixin):
    """A team's position in a single company. Rows are removed when shares hit 0."""
    __tablename__ = "holdings"

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.team_id", ondelete="CASCADE"), primary_key=True
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.company_id", ondelete="CASCADE"), primary_key=True
    )
    shares: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    average_purchase_price: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0)

    team: Mapped["Team"] = relationship(back_populates="holdings")
    company: Mapped["Company"] = relationship(back_populates="holdings")


class PriceSnapshot(Base):
    """
    Immutable append-only price history, one row per company per tick.
    `sequence_number` is global-monotonic and mirrors the WebSocket
    sequence numbers used for gap detection/resync (spec section 48).
    """
    __tablename__ = "price_snapshots"

    id: Mapped[uuid.UUID] = uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.company_id", ondelete="CASCADE"), index=True
    )
    price: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    sequence_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    timestamp: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)

    company: Mapped["Company"] = relationship(back_populates="price_snapshots")
