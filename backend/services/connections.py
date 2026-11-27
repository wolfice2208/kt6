"""WebSocket-менеджер соединений.

Паттерн ConnectionManager (раздел 5 курса): комнаты по пользователю для
личных (targeted) уведомлений + общий broadcast для событий рынка.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = {}
        self._all: set[WebSocket] = set()

    @property
    def total_connections(self) -> int:
        return len(self._all)

    @property
    def rooms(self) -> dict[str, int]:
        return {room: len(sockets) for room, sockets in self._rooms.items()}

    async def connect(self, websocket: WebSocket, room: str) -> None:
        await websocket.accept()
        self._rooms.setdefault(room, set()).add(websocket)
        self._all.add(websocket)
        logger.info("WS подключён: room=%s, всего=%s", room, len(self._all))

    def disconnect(self, websocket: WebSocket, room: str) -> None:
        sockets = self._rooms.get(room)
        if sockets is not None:
            sockets.discard(websocket)
            if not sockets:
                self._rooms.pop(room, None)
        self._all.discard(websocket)
        logger.info("WS отключён: room=%s, всего=%s", room, len(self._all))

    async def _safe_send(self, websocket: WebSocket, payload: dict[str, Any]) -> bool:
        try:
            await websocket.send_json(payload)
            return True
        except Exception:  # соединение могло закрыться между итерациями
            return False

    async def send_to_room(self, room: str, payload: dict[str, Any]) -> int:
        """Личное (targeted) уведомление конкретному пользователю."""
        sockets = list(self._rooms.get(room, ()))
        if not sockets:
            return 0
        results = await asyncio.gather(*(self._safe_send(ws, payload) for ws in sockets))
        for ws, ok in zip(sockets, results):
            if not ok:
                self.disconnect(ws, room)
        return sum(1 for ok in results if ok)

    async def broadcast(self, payload: dict[str, Any]) -> int:
        """Общая рассылка всем подключённым клиентам."""
        sockets = list(self._all)
        if not sockets:
            return 0
        results = await asyncio.gather(*(self._safe_send(ws, payload) for ws in sockets))
        for ws, ok in zip(sockets, results):
            if not ok:
                room = next((name for name, group in self._rooms.items() if ws in group), "")
                self.disconnect(ws, room)
        return sum(1 for ok in results if ok)
