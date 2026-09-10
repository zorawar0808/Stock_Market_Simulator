"""
WebSocket connection manager (spec sections 48-50, 52).

Three logical channels, matching the three frontend apps:
  - participant connections, scoped by team_id (so a BUY by one teammate
    broadcasts only to that team's connected clients)
  - admin connections (global — see all market activity)
  - big-screen connections (global, read-only)

Every outbound message carries a monotonically increasing `sequence_number`.
Clients that detect a gap (received 1002 then 1005) must request a full
authoritative snapshot via a REST endpoint rather than trying to interpolate
— see spec section 48. This manager only tracks connections and sequence
numbers; it does not decide *when* to broadcast — the price engine / trade
endpoints / admin actions call `broadcast_to_team` / `broadcast_global` after
they commit.

This is a single-process in-memory implementation. For horizontal scaling
across multiple backend processes, replace the in-memory sets with Redis
pub/sub (spec section 3 — "Redis may be added if required for WebSocket
pub/sub, horizontal scaling, or distributed coordination") so a broadcast
issued on one process reaches clients connected to another.
"""
import itertools
import uuid
from collections import defaultdict

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._team_connections: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)
        self._admin_connections: set[WebSocket] = set()
        self._big_screen_connections: set[WebSocket] = set()
        self._sequence_counter = itertools.count(start=1)

    def next_sequence_number(self) -> int:
        return next(self._sequence_counter)

    # --- connection lifecycle -------------------------------------------------

    async def connect_participant(self, websocket: WebSocket, team_id: uuid.UUID) -> None:
        await websocket.accept()
        self._team_connections[team_id].add(websocket)

    def disconnect_participant(self, websocket: WebSocket, team_id: uuid.UUID) -> None:
        self._team_connections[team_id].discard(websocket)
        if not self._team_connections[team_id]:
            del self._team_connections[team_id]

    async def connect_admin(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._admin_connections.add(websocket)

    def disconnect_admin(self, websocket: WebSocket) -> None:
        self._admin_connections.discard(websocket)

    async def connect_big_screen(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._big_screen_connections.add(websocket)

    def disconnect_big_screen(self, websocket: WebSocket) -> None:
        self._big_screen_connections.discard(websocket)

    # --- broadcasting ----------------------------------------------------------

    async def broadcast_to_team(self, team_id: uuid.UUID, message: dict) -> None:
        message["sequence_number"] = self.next_sequence_number()
        dead: list[WebSocket] = []
        for ws in self._team_connections.get(team_id, set()):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._team_connections[team_id].discard(ws)

    async def broadcast_global(self, message: dict, *, include_big_screen: bool = True) -> None:
        """Used for leaderboard updates, market state changes, price snapshots, breaking news."""
        message["sequence_number"] = self.next_sequence_number()
        targets = list(itertools.chain.from_iterable(self._team_connections.values())) + list(
            self._admin_connections
        )
        if include_big_screen:
            targets += list(self._big_screen_connections)

        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        # Best-effort cleanup; a connection that failed to send will also be
        # cleaned up on its next receive-loop iteration in the route handler.
        for ws in dead:
            self._admin_connections.discard(ws)
            self._big_screen_connections.discard(ws)
            for team_set in self._team_connections.values():
                team_set.discard(ws)


manager = ConnectionManager()
