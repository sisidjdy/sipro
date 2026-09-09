"""In-process WebSocket connection manager for real-time push (EPIC M3).

Keeps per-user sets of active WebSocket connections so events (notifications,
mentions, SLA breaches) can be pushed the instant they happen — event-driven,
replacing the ~2s SSE poll. Decoupled from db/engine (callers pass ready
JSON-serializable payloads) to avoid circular imports.

In-process only (no external broker) per Dok 13. For multi-worker deployments a
pub/sub fan-out (e.g. Redis) would be layered here; single-worker uvicorn (our
setup) needs no broker.
"""
import asyncio
import logging
from collections import defaultdict
from typing import Any, Dict, Set

from fastapi import WebSocket

logger = logging.getLogger("sipro.ws")


class ConnectionManager:
    """Tracks active sockets keyed by user_email (a user may have many tabs)."""

    def __init__(self) -> None:
        self._conns: Dict[str, Set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, user_email: str, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._conns[user_email].add(ws)
        logger.info("WS connect %s (user_conns=%d, total=%d)",
                    user_email, self.count(user_email), self.total())

    async def disconnect(self, user_email: str, ws: WebSocket) -> None:
        async with self._lock:
            conns = self._conns.get(user_email)
            if conns and ws in conns:
                conns.discard(ws)
                if not conns:
                    self._conns.pop(user_email, None)

    def count(self, user_email: str) -> int:
        return len(self._conns.get(user_email, ()))

    def total(self) -> int:
        return sum(len(s) for s in self._conns.values())

    def is_online(self, user_email: str) -> bool:
        return self.count(user_email) > 0

    async def send_personal(self, user_email: str, message: Dict[str, Any]) -> int:
        """Send a JSON message to all of one user's sockets. Returns #delivered.

        Never raises: dead sockets are pruned silently so callers (e.g.
        create_notification) are never blocked by transport errors.
        """
        conns = list(self._conns.get(user_email, ()))
        if not conns:
            return 0
        delivered = 0
        dead = []
        for ws in conns:
            try:
                await ws.send_json(message)
                delivered += 1
            except Exception:  # noqa: BLE001 - transport error -> prune
                dead.append(ws)
        for ws in dead:
            await self.disconnect(user_email, ws)
        return delivered


# Module-level singleton (in-process bus).
manager = ConnectionManager()
