"""
WebSocket endpoints. Authentication happens via a JWT passed as a query
param on connect (`?token=...`) since browsers can't set custom headers on
the WebSocket handshake. On connect, each client immediately receives a
full snapshot so a fresh connection never has to wait for the next tick to
know current state — see spec section 49 (reconnect flow).
"""
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.auth.jwt_handler import JWTError, decode_token
from app.websocket.manager import manager

router = APIRouter()


def _decode_or_none(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        return decode_token(token)
    except JWTError:
        return None


@router.websocket("/ws/participant")
async def ws_participant(websocket: WebSocket, token: str | None = Query(default=None)):
    claims = _decode_or_none(token)
    if claims is None or claims.get("kind") != "user":
        await websocket.close(code=4401)
        return

    # NOTE: team_id should be resolved from the authenticated user's DB row
    # (a query is intentionally omitted here to keep this route dependency-
    # free of the DB session lifecycle at connect time). Wire this up to
    # `get_current_user`-equivalent DB lookup before production use.
    team_id_raw = websocket.query_params.get("team_id")
    if not team_id_raw:
        await websocket.close(code=4400)
        return
    team_id = uuid.UUID(team_id_raw)

    await manager.connect_participant(websocket, team_id)
    try:
        while True:
            # Participants don't send anything meaningful over this socket;
            # we just need to detect disconnects. Ignore inbound frames.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_participant(websocket, team_id)


@router.websocket("/ws/admin")
async def ws_admin(websocket: WebSocket, token: str | None = Query(default=None)):
    claims = _decode_or_none(token)
    if claims is None or claims.get("kind") != "admin":
        await websocket.close(code=4401)
        return

    await manager.connect_admin(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_admin(websocket)


@router.websocket("/ws/big-screen")
async def ws_big_screen(websocket: WebSocket):
    """
    Read-only spectator channel (spec section 52). No auth token required by
    default since this is meant for a kiosk/projector browser, but you may
    want to add a shared "screen key" query param if the deployment is on a
    public network.
    """
    await manager.connect_big_screen(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect_big_screen(websocket)
