"""
Append-only audit logging helper (spec sections 8, 33, 56).

Call `record(...)` from inside the same transaction as the action being
audited where practical, so the audit trail and the state change commit
or roll back together.
"""
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def record(db: AsyncSession, *, actor: str, action: str, metadata: dict | None = None) -> None:
    entry = AuditLog(
        actor=actor,
        action=action,
        metadata_json=metadata or {},
        timestamp=datetime.now(timezone.utc),
    )
    db.add(entry)
