"""
Seed ~30 fictional companies (spec sections 1, 42).

Run from the repo root (not backend/) so `database.seeds` resolves as a
package alongside `backend.app`:

    cd e-summit-market
    PYTHONPATH=backend python3 -m database.seeds.seed_companies

Hidden fundamentals/liquidity/relationships are intentionally varied here so
the organizer has raw material for ~8 strong positive catalysts, ~7 strong
negative catalysts, ~5 market-wide exposures, ~5 ambiguous clues, and ~5
noise items (spec section 34) once the newsletter CMS is built. This script
only creates the companies; it does not create newsletters.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.company import Company  # noqa: E402

COMPANIES = [
    # (name, ticker, sector, initial_price, liquidity_depth, description)
    ("QuantumEdge", "QNTM", "Deep Tech", 100.00, 120000, "Quantum computing hardware startup chasing error-corrected qubits."),
    ("Solara Grid", "SLRA", "Clean Energy", 85.00, 90000, "Distributed solar microgrid operator for tier-2 cities."),
    ("Nimbus Cloud", "NMBS", "Cloud Infra", 140.00, 150000, "Multi-region cloud storage and compute for SMBs."),
    ("Verdant Foods", "VRDT", "Agri-Tech", 42.00, 60000, "Vertical farming and lab-grown produce distribution."),
    ("Orbital Metals", "ORBM", "Mining", 65.00, 70000, "Asteroid-mining feasibility and rare-earth extraction R&D."),
    ("Pulse Health", "PULS", "Healthtech", 110.00, 95000, "Wearable diagnostics and remote patient monitoring."),
    ("Ferrox Dynamics", "FRRX", "Industrial", 78.00, 85000, "Advanced alloys and additive manufacturing for aerospace."),
    ("Lumen Optics", "LUMN", "Semiconductors", 132.00, 110000, "Photonic chip design for high-speed data transmission."),
    ("Cascade Logistics", "CSCD", "Logistics", 55.00, 65000, "Last-mile delivery network with autonomous micro-hubs."),
    ("Meridian Bank Digital", "MRDB", "Fintech", 98.00, 130000, "Neobank offering embedded lending for gig-economy workers."),
    ("Aether Aerospace", "AETR", "Aerospace", 175.00, 100000, "Small-satellite launch services and orbital logistics."),
    ("BrightLeaf Bio", "BRLF", "Biotech", 60.00, 55000, "mRNA therapeutics platform in early clinical trials."),
    ("Ironclad Cyber", "IRNC", "Cybersecurity", 120.00, 80000, "Zero-trust network security for critical infrastructure."),
    ("Terraform Homes", "TRFM", "Real Estate Tech", 45.00, 50000, "Modular 3D-printed housing for rapid urban development."),
    ("Wavelength Media", "WVLN", "Media/Streaming", 38.00, 45000, "Short-form video streaming platform for regional languages."),
    ("Cobalt Motors", "CBLT", "EV/Automotive", 210.00, 160000, "Electric commercial fleet vehicles and battery swapping."),
    ("Sable Robotics", "SABL", "Robotics", 92.00, 75000, "Warehouse automation and pick-and-place robotic arms."),
    ("GreenSpan Materials", "GRSP", "Materials Science", 50.00, 60000, "Biodegradable packaging materials at industrial scale."),
    ("Vantage Insurance Tech", "VNTG", "Insurtech", 70.00, 68000, "AI-driven underwriting for climate-risk insurance."),
    ("Halcyon Games", "HLCN", "Gaming", 33.00, 40000, "Mobile-first multiplayer game studio with live-ops titles."),
    ("Redwood Data", "RDWD", "Data/Analytics", 105.00, 90000, "Enterprise data pipeline and analytics-as-a-service."),
    ("Pinnacle Defense Systems", "PNCL", "Defense", 190.00, 140000, "Autonomous drone systems for border and perimeter security."),
    ("Amber Chemicals", "AMBR", "Chemicals", 58.00, 62000, "Specialty chemicals for battery electrolyte manufacturing."),
    ("Skyline Freight Rail", "SKFR", "Transportation", 80.00, 88000, "Regional freight rail electrification and scheduling software."),
    ("Nordic Aqua Farms", "NRDA", "Aquaculture", 40.00, 42000, "Land-based sustainable salmon and shrimp farming."),
    ("Vertex Semiconductors", "VRTX2", "Semiconductors", 160.00, 125000, "Custom ASIC design for edge-AI inference chips."),
    ("Solstice Retail", "SLST", "E-commerce", 47.00, 52000, "Social-commerce marketplace for independent creators."),
    ("Argon Space Materials", "ARGN", "Materials/Aerospace", 115.00, 78000, "Heat-shield ceramics for reusable launch vehicles."),
    ("Beacon Education", "BCON", "Edtech", 36.00, 38000, "Adaptive-learning platform for vocational upskilling."),
    ("Cinder Foundries", "CNDR", "Manufacturing", 63.00, 58000, "Precision casting for EV drivetrain components."),
]


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(Company.ticker))).scalars().all()
        existing_set = set(existing)

        created = 0
        for name, ticker, sector, initial_price, liquidity_depth, description in COMPANIES:
            if ticker in existing_set:
                continue
            db.add(
                Company(
                    name=name,
                    ticker=ticker,
                    sector=sector,
                    description=description,
                    initial_price=initial_price,
                    current_price=initial_price,
                    liquidity_depth=liquidity_depth,
                    # Hidden fundamentals/relationships left empty here -
                    # populate through the admin console once built (spec
                    # section 24-25). Never exposed to participants directly.
                    fundamentals={},
                    relationships={},
                )
            )
            created += 1

        await db.commit()
        print(f"Seeded {created} new companies ({len(existing_set)} already existed).")


if __name__ == "__main__":
    asyncio.run(seed())
