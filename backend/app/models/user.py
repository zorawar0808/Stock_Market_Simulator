"""
USERS (participants) and ADMINS (spec sections 7, 8).

Participants and admins are deliberately separate tables/entities: they have
different auth surfaces, different RBAC models, and mixing them invites the
"one shared admin account" anti-pattern the spec explicitly forbids.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import AdminRole, TimestampMixin, UserStatus, uuid_pk


class User(Base, TimestampMixin):
    """A participant account. Multiple users may share one team."""
    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("teams.team_id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status"), nullable=False, default=UserStatus.PENDING_VERIFICATION
    )
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    team: Mapped["Team"] = relationship(back_populates="users")
    trades: Mapped[list["Trade"]] = relationship(back_populates="user")


class Admin(Base, TimestampMixin):
    """
    An individual administrator account (never a single shared login -
    spec section 8). Every admin action is attributable to a specific
    admin_id in the audit log.
    """
    __tablename__ = "admins"

    admin_id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[AdminRole] = mapped_column(SAEnum(AdminRole, name="admin_role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admins.admin_id", ondelete="SET NULL"), nullable=True
    )
