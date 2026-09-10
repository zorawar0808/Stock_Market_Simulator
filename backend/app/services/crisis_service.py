import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import MarketEventStatus, MarketEventType, NewsStatus, NewsType
from app.models.company import Company
from app.models.market_event import MarketEvent
from app.models.news import News


CRISIS_EVENTS = [
    {
        "key": "market_crash",
        "type": MarketEventType.MARKET_WIDE,
        "headline": "BREAKING: Major Market Shock Sends Stocks Tumbling",
        "description": (
            "A sudden economic shock has triggered widespread investor panic, "
            "sending stock prices sharply lower across the market."
        ),
        "impact_direction": "NEGATIVE",
        "impact_min": -0.10,
        "impact_max": -0.06,
    },
    {
        "key": "market_correction",
        "type": MarketEventType.MARKET_WIDE,
        "headline": "BREAKING: Markets Face a Sharp Correction",
        "description": (
            "Investor confidence has weakened, triggering a broad market "
            "correction and putting moderate downward pressure on stock prices."
        ),
        "impact_direction": "NEGATIVE",
        "impact_min": -0.03,
        "impact_max": -0.01,
    },
    {
        "key": "market_rally",
        "type": MarketEventType.MULTI_COMPANY,
        "headline": "BREAKING: Major Breakthrough Sends Selected Stocks Soaring",
        "description": (
            "A wave of positive developments has boosted investor confidence "
            "in a select group of companies, driving strong buying interest."
        ),
        "impact_direction": "POSITIVE",
        "impact_min": 0.04,
        "impact_max": 0.08,
    },
]


async def get_crisis_events(db: AsyncSession):
    result = await db.execute(
        select(MarketEvent)
        .where(MarketEvent.source == "MANUAL")
        .order_by(MarketEvent.created_at.asc())
    )
    return result.scalars().all()


async def create_demo_events(db: AsyncSession, admin_id: uuid.UUID):
    existing = await get_crisis_events(db)

    if existing:
        return existing

    companies_result = await db.execute(
        select(Company)
        .where(Company.status == "ACTIVE")
        .order_by(Company.ticker)
    )
    companies = companies_result.scalars().all()

    events = []

    # ============================================================
    # EVENT 1 — MARKET CRASH
    # Affects EVERY active company.
    # ============================================================
    all_company_ids = [
        str(company.company_id)
        for company in companies
    ]

    events.append(
        MarketEvent(
            type=MarketEventType.MARKET_WIDE,
            status=MarketEventStatus.APPROVED,
            headline=CRISIS_EVENTS[0]["headline"],
            description=CRISIS_EVENTS[0]["description"],
            affected_company_ids=all_company_ids,
            impact_direction="NEGATIVE",
            impact_range_min=CRISIS_EVENTS[0]["impact_min"],
            impact_range_max=CRISIS_EVENTS[0]["impact_max"],
            source="MANUAL",
            created_by=admin_id,
            approved_by=admin_id,
            approved_at=datetime.now(timezone.utc),
        )
    )

    # ============================================================
    # EVENT 2 — MARKET CORRECTION
    # Affects EVERY active company, but with a smaller shock.
    # ============================================================
    events.append(
        MarketEvent(
            type=MarketEventType.MARKET_WIDE,
            status=MarketEventStatus.APPROVED,
            headline=CRISIS_EVENTS[1]["headline"],
            description=CRISIS_EVENTS[1]["description"],
            affected_company_ids=all_company_ids,
            impact_direction="NEGATIVE",
            impact_range_min=CRISIS_EVENTS[1]["impact_min"],
            impact_range_max=CRISIS_EVENTS[1]["impact_max"],
            source="MANUAL",
            created_by=admin_id,
            approved_by=admin_id,
            approved_at=datetime.now(timezone.utc),
        )
    )

    # ============================================================
    # EVENT 3 — SELECTED COMPANY RALLY
    #
    # These are deliberately chosen companies that participants
    # can potentially discover through the newsletters/clues.
    #
    # AETR  - Aether Aerospace
    # QNTM  - QuantumEdge
    # SABL  - Sable Robotics
    # VRTX2 - Vertex Semiconductors
    # ============================================================
    rally_tickers = {
        "AETR",
        "QNTM",
        "SABL",
        "VRTX2",
    }

    rally_company_ids = [
        str(company.company_id)
        for company in companies
        if company.ticker in rally_tickers
    ]

    events.append(
        MarketEvent(
            type=MarketEventType.MULTI_COMPANY,
            status=MarketEventStatus.APPROVED,
            headline=CRISIS_EVENTS[2]["headline"],
            description=CRISIS_EVENTS[2]["description"],
            affected_company_ids=rally_company_ids,
            impact_direction="POSITIVE",
            impact_range_min=CRISIS_EVENTS[2]["impact_min"],
            impact_range_max=CRISIS_EVENTS[2]["impact_max"],
            source="MANUAL",
            created_by=admin_id,
            approved_by=admin_id,
            approved_at=datetime.now(timezone.utc),
        )
    )

    db.add_all(events)
    await db.flush()

    return events


async def execute_event(
    db: AsyncSession,
    event: MarketEvent,
    admin_id: uuid.UUID,
):
    if event.status == MarketEventStatus.EXECUTED:
        return event

    now = datetime.now(timezone.utc)

    event.status = MarketEventStatus.EXECUTED
    event.executed_at = now
    event.approved_by = admin_id
    event.approved_at = event.approved_at or now

    company_ids = [
        uuid.UUID(str(company_id))
        for company_id in (event.affected_company_ids or [])
    ]

    companies = []

    if company_ids:
        result = await db.execute(
            select(Company).where(
                Company.company_id.in_(company_ids)
            )
        )
        companies = result.scalars().all()

    news = News(
        title=event.headline,
        content=event.description,
        type=NewsType.BREAKING_NEWS,
        status=NewsStatus.PUBLISHED,
        published_at=now,
        created_by=admin_id,
        companies=companies,
    )

    db.add(news)
    await db.flush()

    return event
