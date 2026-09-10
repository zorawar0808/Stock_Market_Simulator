"""
Import every model module here so that:
  - `Base.metadata` is fully populated for Alembic autogenerate, and
  - relationship() string references resolve correctly.
"""
from app.models.base import (  # noqa: F401
    AdminRole,
    CompanyStatus,
    MarketEventStatus,
    MarketEventType,
    MarketState,
    NewsStatus,
    NewsType,
    RejectionReason,
    TeamStatus,
    TradeStatus,
    TradeType,
    UserStatus,
)
from app.models.user import Admin, User  # noqa: F401
from app.models.team import Team, Portfolio  # noqa: F401
from app.models.company import Company, Holding, PriceSnapshot  # noqa: F401
from app.models.trade import Trade  # noqa: F401
from app.models.news import News, NewsRevision, news_companies  # noqa: F401
from app.models.market_event import MarketEvent  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.market_state import MarketStateRow  # noqa: F401
