# E-Summit Live Stock Market Simulation

Production-grade multiplayer live stock market simulation platform. Server-authoritative
by design — the browser never calculates prices, cash, holdings, rankings, or timestamps.

This repo is scaffolded in the build priority order from the master spec:

1. Architecture (this scaffold)
2. DB schema / migrations (`backend/migrations`, `backend/app/models`)
3. Authentication (`backend/app/auth`)
4. Teams / invitation system (`backend/app/api/teams.py`)
5. Portfolio (`backend/app/models/portfolio.py`, `backend/app/api/portfolio.py`)
6. Atomic BUY/SELL (`backend/app/services/trading_service.py`)
7. Validation / idempotency / concurrency (built into `trading_service.py`)

Everything after that (full price-engine ticking, WebSocket broadcast wiring,
newsletter CMS, admin console UI, Big Screen app, AI event generator, load/failure
testing, UI polish) has clear extension points stubbed out but is intentionally not
fully built yet — build those next, in the order listed in the master spec, on top
of this foundation.

## Repository layout

```
/e-summit-market
├── apps/
│   ├── participant/     Vue 3 + Vite trading terminal (scaffold)
│   ├── admin/           Vue 3 + Vite admin console (scaffold)
│   └── big-screen/      Vue 3 + Vite spectator display (scaffold)
├── backend/             FastAPI backend — single source of truth
│   ├── app/
│   │   ├── models/      SQLAlchemy 2.0 ORM models (one file per entity)
│   │   ├── schemas/     Pydantic request/response schemas
│   │   ├── auth/        Password hashing, JWT, register/login
│   │   ├── services/    Business logic (trading, market state, audit)
│   │   ├── api/         FastAPI routers
│   │   ├── websocket/   Connection manager, sequence numbers, broadcast
│   │   └── middleware/  Rate limiting etc.
│   └── migrations/      Alembic migrations (schema is version-controlled)
├── market-engine/       Server-side price/liquidity/news/event simulation
│   ├── pricing/
│   ├── liquidity/
│   ├── events/
│   ├── news/
│   └── simulation/      Market clock + state machine
├── database/
│   └── seeds/           Seed script for ~30 fictional companies
├── tests/
│   ├── unit/
│   └── concurrency/     Concurrency correctness tests (BUY/BUY, SELL/SELL races)
└── docs/
    └── ARCHITECTURE.md
```

## Running the backend locally

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set DATABASE_URL to a real Postgres instance and a real JWT_SECRET

# Apply the schema
alembic upgrade head

# Seed ~30 fictional companies
python -m database.seeds.seed_companies   # run from repo root, see script header

# Run the API
uvicorn app.main:app --reload --port 8000
```

The backend needs a real PostgreSQL instance — it will not run correctly against
SQLite because the concurrency guarantees rely on `SELECT ... FOR UPDATE` row
locking, which the migration and services assume is Postgres.

## Running a frontend app locally

```bash
cd apps/participant   # or apps/admin, apps/big-screen
npm install
npm run dev
```

Each app is an independent Vite build. They all talk to the same backend via
`VITE_API_URL` / `VITE_WS_URL` (see `.env.example` in each app).

## What's implemented right now

- Full relational schema for every entity in the master spec (users, teams,
  portfolios, holdings, companies, trades, price snapshots, news + junction table,
  market events, audit logs, admin users, market state) with foreign keys, uniqueness
  constraints, and indexes.
- An Alembic migration that creates the entire schema in one revision.
- JWT-based auth with bcrypt password hashing, invitation-code registration with
  team-capacity validation, and a login endpoint.
- A trading service that performs BUY and SELL atomically under row-level locking,
  enforces `order value <= cash` and `shares to sell <= shares owned`, computes
  fractional shares server-side, and is idempotent via a unique `idempotency_key`
  on trades (duplicate submission returns the original result instead of executing
  twice).
- A minimal market state machine (WAITING → LIVE → PAUSED → EMERGENCY_FROZEN →
  ENDING → CLOSED) enforcing only the valid transitions from the spec.
- A skeleton WebSocket connection manager with monotonic sequence numbers per team,
  ready for the price-engine broadcast loop to plug into.
- A concurrency test showing exactly how to drive the "two teammates race for the
  last ₹1,000" and "two teammates race to sell the last shares" scenarios against a
  live Postgres instance.

## What to build next (in spec order)

Server clock loop → price engine ticking (aggregated order flow, liquidity,
fundamentals, circuit breakers) → WebSocket broadcast wiring → sequence/resync →
participant terminal UI → MY HOLDINGS/SELL UI → portfolio/trade history UI →
market overview/company detail/charts (TradingView Lightweight Charts) →
leaderboard → newsletter CMS (drafts/scheduling/publish/revisions) → admin console
UI → AI crisis event generator (proposal-only, human-approved) → audit UI → Big
Screen app → monitoring → backups/recovery → load/failure/security testing → UI
polish → production deployment.
