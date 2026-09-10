"""AUDIT_LOGS (spec sections 9, 33, 56). Append-only, never mutated."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import uuid_pk


class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_id: Mapped[uuid.UUID] = uuid_pk()
    actor: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
        doc="e.g. 'admin:<admin_id>', 'user:<user_id>', 'system'",
    )
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
