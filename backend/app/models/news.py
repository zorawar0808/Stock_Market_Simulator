"""
NEWS / newsletter CMS and the many-to-many company association
(spec sections 9, 28-34).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, Table, Column
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import NewsStatus, NewsType, TimestampMixin, uuid_pk

news_companies = Table(
    "news_companies",
    Base.metadata,
    Column("news_id", UUID(as_uuid=True), ForeignKey("news.news_id", ondelete="CASCADE"), primary_key=True),
    Column("company_id", UUID(as_uuid=True), ForeignKey("companies.company_id", ondelete="CASCADE"), primary_key=True),
)


class News(Base, TimestampMixin):
    """
    A single newsletter/news item. Corrections create a new revision
    (see NewsRevision) rather than mutating a published item in place
    (spec section 33).
    """
    __tablename__ = "news"

    news_id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(String(4000), nullable=False)
    type: Mapped[NewsType] = mapped_column(SAEnum(NewsType, name="news_type"), nullable=False)
    status: Mapped[NewsStatus] = mapped_column(
        SAEnum(NewsStatus, name="news_status"), nullable=False, default=NewsStatus.DRAFT
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("admins.admin_id"))

    companies: Mapped[list["Company"]] = relationship(secondary=news_companies)
    revisions: Mapped[list["NewsRevision"]] = relationship(back_populates="news", order_by="NewsRevision.revision_number")


class NewsRevision(Base):
    """Immutable snapshot of a News item's content at the time of a correction."""
    __tablename__ = "news_revisions"

    id: Mapped[uuid.UUID] = uuid_pk()
    news_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("news.news_id", ondelete="CASCADE"))
    revision_number: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(String(4000), nullable=False)
    edited_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("admins.admin_id"))
    edited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    news: Mapped["News"] = relationship(back_populates="revisions")
