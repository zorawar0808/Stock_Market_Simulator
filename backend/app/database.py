"""
Database engine and session management.

The application uses SQLAlchemy 2.0's async engine (asyncpg driver) for all
request-time database access. Alembic migrations use the sync driver
(psycopg2) instead, since Alembic's migration runner is sync-only — see
migrations/env.py.

Connection pooling is configured conservatively for a ~150-team / 350+
participant event; tune pool_size/max_overflow against real load-test numbers
before the event (see backend/app/config.py + docs/ARCHITECTURE.md).
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model in the app."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a request-scoped DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
