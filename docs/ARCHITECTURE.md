# Architecture Notes

## What "server-authoritative" means in this codebase, concretely

Every number a client ever sees — cash, shares, price, rank, countdown — is
read from Postgres, computed by a service in `backend/app/services/`, or
both. No endpoint accepts a client-supplied price, share count, balance, or
timestamp and treats it as fact. The clearest example is
`backend/app/services/trading_service.py`: a BUY request carries only a
currency amount and an idempotency key; the server looks up the current
price under a row lock and computes shares itself.

## The concurrency guarantee, and how it's verified

Every financial mutation for a team acquires `SELECT ... FOR UPDATE` on
that team's `Portfolio` row before touching cash or holdings. Two teammates
racing to spend the same money therefore can't both succeed: the second
transaction blocks on the lock, then re-reads the now-updated cash balance
once the first commits, and correctly rejects if it would overdraw.

This isn't just a design claim — `tests/concurrency/test_trading_concurrency.py`
drives real concurrent asyncio tasks against a live Postgres instance and
asserts the outcome:

- two simultaneous BUYs for the team's entire cash balance → exactly one
  executes, the other is rejected with `INSUFFICIENT_FUNDS`, final cash is
  exactly zero (never negative, never double-spent)
- two simultaneous SELLs of a team's entire share balance → exactly one
  executes, the other is rejected with `INSUFFICIENT_SHARES`
- replaying an already-processed idempotency key returns the original
  trade rather than executing (or re-rejecting) anything a second time
- a BUY submitted while the market is PAUSED is rejected with
  `MARKET_PAUSED` rather than silently succeeding

Run them yourself: `cd backend && python3 -m pytest ../tests/concurrency -v`
(needs `DATABASE_URL` in `.env` pointed at a real, empty-or-disposable
Postgres database — these tests create and mutate real rows).

## Why the trading service doesn't use `async with db.begin()`

If you look closely at `trading_service.py`, you'll notice it relies on
SQLAlchemy's session autobegin plus an explicit `commit()`/`rollback()` at
the end, rather than wrapping the function body in
`async with db.begin():`. This is deliberate, not an oversight: the
idempotency-check `SELECT` at the top of each function already autobegins a
transaction on the session, so a subsequent explicit `db.begin()` raises
`InvalidRequestError: A transaction is already begun on this Session`. This
is a real bug that showed up during development (see git history / the
in-repo comments) and the fix generalizes to any service function in this
codebase: don't mix "let the session autobegin" with "explicitly begin a
transaction" on the same session.

## The market_state singleton

`market_state` is a single-row table (`id=1`) — there is exactly one market
per event, and every state-machine transition (`backend/app/services/
market_service.py`) reads and writes that one row under the transitions
table in the spec. Pausing doesn't shift `started_at`; it accumulates
`total_paused_seconds` so a countdown computed as
`duration_seconds - (elapsed - total_paused_seconds)` is correct regardless
of how many times the market was paused and resumed.

## What's real vs. what's a documented stub

Real, tested, and running against Postgres: the full schema and migration,
auth, team/invitation registration, the trading engine, the state machine,
the admin market-control endpoints, the leaderboard/status endpoints, and
three Vite/Vue apps that talk to all of the above.

Documented stubs with clear extension points, not yet implemented: the
price-engine tick loop (`market-engine/simulation/clock.py` — the pure
pricing math in `market-engine/pricing/engine.py` is implemented and
unit-verified, but nothing calls it on a timer yet), the WebSocket
broadcast wiring (the connection manager exists; nothing calls
`broadcast_to_team`/`broadcast_global` yet), the newsletter CMS, the AI
crisis-event generator, and full settlement logic in `end_market`. See the
root README's "What to build next" section for the order to build these in.
