import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.rbac import require_role
from app.database import get_db
from app.models.base import AdminRole, MarketEventStatus
from app.models.user import Admin
from app.services import crisis_service
from app.services.audit_service import record as audit_record

router = APIRouter(prefix="/api/admin/crisis", tags=["admin-crisis"])

_ADMIN_ROLES = (
    AdminRole.SUPER_ADMIN,
    AdminRole.OPERATIONS_ADMIN,
)


@router.post("/seed")
async def seed_crisis_events(
    admin: Admin = Depends(require_role(*_ADMIN_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    events = await crisis_service.create_demo_events(
        db,
        admin.admin_id,
    )

    await db.commit()

    return [
        {
            "event_id": str(event.event_id),
            "headline": event.headline,
            "description": event.description,
            "type": event.type.value,
            "status": event.status.value,
            "affected_company_ids": event.affected_company_ids,
            "impact_direction": event.impact_direction,
            "impact_range_min": event.impact_range_min,
            "impact_range_max": event.impact_range_max,
        }
        for event in events
    ]



@router.post("/reset")
async def reset_crisis_events(
    admin=Depends(require_role(*_ADMIN_ROLES)),
    db=Depends(get_db),
):
    from sqlalchemy import update
    from app.models.market_event import MarketEvent

    demo_headlines = [
        event["headline"]
        for event in crisis_service.CRISIS_EVENTS
    ]

    await db.execute(
        update(MarketEvent)
        .where(MarketEvent.headline.in_(demo_headlines))
        .where(MarketEvent.source == "MANUAL")
        .values(
            status=MarketEventStatus.APPROVED,
            executed_at=None,
        )
    )

    await db.commit()

    return {"status": "reset"}

@router.get("/events")
async def list_crisis_events(
    admin: Admin = Depends(require_role(*_ADMIN_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    events = await crisis_service.get_crisis_events(db)

    return [
        {
            "event_id": str(event.event_id),
            "headline": event.headline,
            "description": event.description,
            "type": event.type.value,
            "status": event.status.value,
            "affected_company_ids": event.affected_company_ids,
            "impact_direction": event.impact_direction,
            "impact_range_min": event.impact_range_min,
            "impact_range_max": event.impact_range_max,
            "executed_at": event.executed_at,
        }
        for event in events
    ]


@router.post("/events/{event_id}/trigger")
async def trigger_crisis_event(
    event_id: str,
    admin: Admin = Depends(require_role(*_ADMIN_ROLES)),
    db: AsyncSession = Depends(get_db),
):
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid event ID",
        )

    event = await db.get(
        crisis_service.MarketEvent,
        event_uuid,
    )

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Crisis event not found",
        )

    if event.status == MarketEventStatus.EXECUTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Crisis event has already been executed",
        )

    await crisis_service.execute_event(
        db,
        event,
        admin.admin_id,
    )

    await audit_record(
        db,
        actor=f"admin:{admin.admin_id}",
        action="CRISIS_EVENT_TRIGGERED",
        metadata={
            "event_id": str(event.event_id),
            "headline": event.headline,
            "affected_company_ids": event.affected_company_ids,
        },
    )

    await db.commit()

    return {
        "event_id": str(event.event_id),
        "headline": event.headline,
        "description": event.description,
        "status": event.status.value,
        "executed_at": event.executed_at,
    }
