"""Shared mixins and enums used across models."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# --- Enums (spec sections 8, 14, 28, 10/11) ---------------------------------

class AdminRole(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    OPERATIONS_ADMIN = "OPERATIONS_ADMIN"
    MONITOR_ADMIN = "MONITOR_ADMIN"


class UserStatus(str, enum.Enum):
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class TeamStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    LOCKED = "LOCKED"
    DISQUALIFIED = "DISQUALIFIED"


class CompanyStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    HALTED = "HALTED"          # circuit breaker / admin halt
    DELISTED = "DELISTED"


class TradeType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(str, enum.Enum):
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"


class RejectionReason(str, enum.Enum):
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    INSUFFICIENT_SHARES = "INSUFFICIENT_SHARES"
    MARKET_PAUSED = "MARKET_PAUSED"
    MARKET_CLOSED = "MARKET_CLOSED"
    MARKET_FROZEN = "MARKET_FROZEN"
    INVALID_ORDER = "INVALID_ORDER"
    COMPANY_HALTED = "COMPANY_HALTED"
    NONE = "NONE"


class MarketState(str, enum.Enum):
    WAITING = "WAITING"
    LIVE = "LIVE"
    PAUSED = "PAUSED"
    EMERGENCY_FROZEN = "EMERGENCY_FROZEN"
    ENDING = "ENDING"
    CLOSED = "CLOSED"


class NewsType(str, enum.Enum):
    COMPANY_NEWS = "COMPANY_NEWS"
    CLUE = "CLUE"
    MARKET_NEWS = "MARKET_NEWS"
    BREAKING_NEWS = "BREAKING_NEWS"


class NewsStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    CANCELLED = "CANCELLED"


class MarketEventStatus(str, enum.Enum):
    PROPOSED = "PROPOSED"       # e.g. from AI generator, awaiting admin review
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"


class MarketEventType(str, enum.Enum):
    SINGLE_COMPANY = "SINGLE_COMPANY"
    MULTI_COMPANY = "MULTI_COMPANY"
    SECTOR_WIDE = "SECTOR_WIDE"
    MARKET_WIDE = "MARKET_WIDE"
