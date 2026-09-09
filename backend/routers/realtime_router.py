"""Real-time notifications (EPIC M3).

Primary transport: **WebSocket** (`/api/ws/notifications`) — event-driven, instant
push via ws_manager (a notification is delivered the moment it is created), plus
bi-directional client actions (ping/pong heartbeat, mark_read, mark_all_read).

Fallback transport: **SSE** (`/api/notifications/stream`) kept for clients/proxies
that cannot upgrade to WebSocket. EventSource cannot send an Authorization header,
so the token is passed via query (`?token=`).
"""
import asyncio
import json
import logging

import jwt
from fastapi import APIRouter, Request, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from db import db, ORG_ID
from core_utils import serialize_doc, now_iso
from security import get_jwt_secret, JWT_ALGORITHM
from ws_manager import manager

router = APIRouter(tags=["realtime"])
logger = logging.getLogger("sipro.realtime")


async def _user_from_token(token: str):
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            return None
    except jwt.PyJWTError:
        return None
    user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0, "password_hash": 0})
    if not user or not user.get("is_active", True):
        return None
    return user


@router.get("/notifications/stream")
async def notifications_stream(request: Request, token: str = ""):
    user = await _user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Token tidak valid untuk stream notifikasi")
    org = user.get("org_id", ORG_ID)
    email = user.get("email")

    async def event_gen():
        last_ts = now_iso()
        unread = await db.notifications.count_documents({"org_id": org, "user_email": email, "read": False})
        yield f"event: hello\ndata: {json.dumps({'unread': unread})}\n\n"
        while True:
            if await request.is_disconnected():
                break
            try:
                new = await db.notifications.find({
                    "org_id": org, "user_email": email, "created_at": {"$gt": last_ts},
                }, {"_id": 0}).sort("created_at", 1).to_list(20)
            except Exception:
                new = []
            for n in new:
                last_ts = n.get("created_at", last_ts)
                yield f"event: notification\ndata: {json.dumps(serialize_doc(n))}\n\n"
            unread = await db.notifications.count_documents({"org_id": org, "user_email": email, "read": False})
            yield f"event: ping\ndata: {json.dumps({'unread': unread})}\n\n"
            await asyncio.sleep(2)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}
    return StreamingResponse(event_gen(), media_type="text/event-stream", headers=headers)


async def _unread_count(org: str, email: str) -> int:
    return await db.notifications.count_documents(
        {"org_id": org, "user_email": email, "read": False})


@router.websocket("/ws/notifications")
async def notifications_ws(websocket: WebSocket, token: str = ""):
    """Bi-directional real-time channel (EPIC M3).

    Server -> client events: ``hello`` (initial unread), ``notification`` (instant
    push), ``unread`` (count refresh), ``pong`` (heartbeat ack).
    Client -> server actions (JSON): ``{"action":"ping"}``,
    ``{"action":"mark_read","id":...}``, ``{"action":"mark_all_read"}``.
    """
    user = await _user_from_token(token)
    if not user:
        # Accept then close with an app-level code so the client can read 4401
        # (a pre-accept close would surface as a generic HTTP 403 handshake reject).
        await websocket.accept()
        await websocket.close(code=4401)
        return
    org = user.get("org_id", ORG_ID)
    email = user.get("email")
    await manager.connect(email, websocket)
    try:
        await websocket.send_json({
            "event": "hello", "unread": await _unread_count(org, email),
            "transport": "websocket",
        })
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                continue
            action = msg.get("action")
            if action == "ping":
                await websocket.send_json({"event": "pong"})
            elif action == "mark_read" and msg.get("id"):
                await db.notifications.update_one(
                    {"org_id": org, "user_email": email, "id": msg["id"]},
                    {"$set": {"read": True}})
                await websocket.send_json({"event": "unread", "unread": await _unread_count(org, email)})
            elif action == "mark_all_read":
                await db.notifications.update_many(
                    {"org_id": org, "user_email": email, "read": False},
                    {"$set": {"read": True}})
                await websocket.send_json({"event": "unread", "unread": 0})
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.debug("ws loop error for %s", email, exc_info=True)
    finally:
        await manager.disconnect(email, websocket)
