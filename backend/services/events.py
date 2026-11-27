"""Внутренняя шина событий: источник → SSE-подписчики.

Ingestion публикует события, SSE-роутер раздаёт их всем подключённым клиентам.
Очередь на подписчика ограничена, чтобы медленный клиент не тормозил воркер:
при переполнении выбрасываем самое старое событие.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self, max_queue_size: int = 200) -> None:
        self._max_queue_size = max_queue_size
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._max_queue_size)
        self._subscribers.add(queue)
        logger.debug("SSE-подписчик добавлен, всего: %s", len(self._subscribers))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(queue)
        logger.debug("SSE-подписчик удалён, всего: %s", len(self._subscribers))

    async def publish(self, event_type: str, data: dict[str, Any]) -> None:
        event = {"type": event_type, "data": data}
        for queue in list(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:  # pragma: no cover - гонка
                    pass
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover
                logger.warning("Не удалось доставить событие подписчику")
