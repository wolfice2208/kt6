"""Клиент официального API STALZONE (EXBO).

Документация: https://eapi.stalcraft.net/
* demo-контур: https://dapi.stalzone.com (публичные токены из документации);
* production:   https://eapi.stalcraft.net (токен приложения после одобрения заявки).

Ключевые свойства клиента:
* ограничитель запросов (token bucket), синхронизированный с заголовками
  ``x-ratelimit-*`` — приложение не «долбит» API и не получает 429;
* ретраи с экспоненциальной задержкой и уважением к ``Retry-After``;
* обновление токена по 401 и по истечении срока;
* единая точка адаптации формата ответа — если схема изменится (API в бете),
  правится только этот файл.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Iterable, Mapping

import httpx

from config import Settings
from services.mock_source import MockSource

logger = logging.getLogger(__name__)


class SourceError(RuntimeError):
    """Ошибка источника данных (сеть, токен, формат ответа)."""


class RateLimiter:
    """Token bucket: не больше N запросов в минуту на всё приложение."""

    def __init__(self, per_minute: int) -> None:
        self._rate_per_second = max(per_minute, 1) / 60.0
        self._capacity = float(max(per_minute, 1))
        self._tokens = self._capacity
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self._tokens = min(self._capacity, self._tokens + (now - self._updated_at) * self._rate_per_second)
                self._updated_at = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait_for = (1.0 - self._tokens) / self._rate_per_second
                await asyncio.sleep(min(wait_for, 5.0))

    def sync_from_headers(self, headers: Mapping[str, str]) -> None:
        """Подстраивается под остаток лимита, который сообщает сервер."""
        remaining = headers.get("x-ratelimit-remaining")
        if remaining is None:
            return
        try:
            self._tokens = min(self._tokens, float(remaining))
        except ValueError:
            pass


def _extract_list(payload: Any, keys: Iterable[str]) -> list[dict[str, Any]]:
    """Достаёт список объектов из ответа API, устойчиво к обёрткам."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
            if isinstance(value, dict) and value and all(isinstance(v, dict) for v in value.values()):
                return [row for row in value.values() if isinstance(row, dict)]
    return []


class StalzoneClient:
    """Каталог лотов и истории продаж официального API."""

    name = "stalzone"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.resolved_api_base.rstrip("/")
        self._limiter = RateLimiter(settings.max_requests_per_minute)
        self._token = settings.stalzone_app_token.strip()
        self._token_refresh_at = 0.0  # 0 = токен не нужен/получен из .env
        self._token_lock = asyncio.Lock()
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=settings.stalzone_timeout_seconds,
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "application/json",
            },
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    async def close(self) -> None:
        await self._client.aclose()

    # ---------- авторизация ----------

    async def _ensure_token(self) -> None:
        if self._token_refresh_at and time.monotonic() < self._token_refresh_at:
            return
        async with self._token_lock:
            if self._token_refresh_at and time.monotonic() < self._token_refresh_at:
                return
            if self._settings.stalzone_app_token.strip():
                # Токен выдан вручную — считаем его валидным, обновим только по 401.
                self._token = self._settings.stalzone_app_token.strip()
                self._token_refresh_at = time.monotonic() + 6 * 3600
                return
            if not (self._settings.stalzone_client_id and self._settings.stalzone_client_secret):
                raise SourceError(
                    "Не задан токен STALZONE: заполните STALZONE_APP_TOKEN "
                    "(или STALZONE_CLIENT_ID/STALZONE_CLIENT_SECRET) в backend/.env"
                )
            data = {
                "grant_type": "client_credentials",
                "client_id": self._settings.stalzone_client_id,
                "client_secret": self._settings.stalzone_client_secret,
            }
            if self._settings.stalzone_scope:
                data["scope"] = self._settings.stalzone_scope
            try:
                response = await self._client.post(self._settings.resolved_token_url, data=data)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise SourceError(f"Не удалось получить app-токен: {exc}") from exc
            token = payload.get("access_token")
            if not token:
                raise SourceError("Ответ OAuth не содержит access_token")
            self._token = token
            expires_in = float(payload.get("expires_in") or 3600)
            self._token_refresh_at = time.monotonic() + max(expires_in - 60, 60)
            logger.info("Получен app-токен STALZONE, действует %.0f c", expires_in)

    def invalidate_token(self) -> None:
        self._token_refresh_at = 0.0

    # ---------- низкоуровневые запросы ----------

    async def _request(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self._settings.http_retries + 1):
            await self._limiter.acquire()
            try:
                await self._ensure_token()
                response = await self._client.get(
                    path,
                    params=dict(params or {}),
                    headers={"Authorization": f"Bearer {self._token}"} if self._token else {},
                )
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("Сетевая ошибка %s (попытка %s/%s)", exc, attempt, self._settings.http_retries)
                await asyncio.sleep(min(2 ** attempt * 0.5, 8))
                continue

            self._limiter.sync_from_headers(response.headers)

            if response.status_code == 401:
                self.invalidate_token()
                last_error = SourceError("401: токен отклонён")
                logger.warning("Токен отклонён, обновляем (попытка %s)", attempt)
                continue
            if response.status_code == 429:
                retry_after = float(response.headers.get("retry-after", 1) or 1)
                logger.warning("429 rate limit, пауза %.1f c", retry_after)
                await asyncio.sleep(min(retry_after, 10))
                last_error = SourceError("429: превышен лимит запросов")
                continue
            if response.status_code >= 500:
                last_error = SourceError(f"{response.status_code}: ошибка на стороне API")
                await asyncio.sleep(min(2 ** attempt * 0.5, 8))
                continue
            if response.status_code == 404:
                return None
            try:
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise SourceError(f"Некорректный ответ API {path}: {exc}") from exc

        raise SourceError(f"Запрос {path} не удался: {last_error}")

    # ---------- контракт источника ----------

    async def fetch_lots(self, item_id: str, limit: int = 50) -> list[dict[str, Any]]:
        payload = await self._request(
            f"/{self._settings.stalzone_region}/auction/{item_id}/lots",
            {"limit": limit},
        )
        return _extract_list(payload, ("lots", "items", "data", "result"))

    async def fetch_history(self, item_id: str, limit: int = 200) -> list[dict[str, Any]]:
        payload = await self._request(
            f"/{self._settings.stalzone_region}/auction/{item_id}/history",
            {"limit": limit},
        )
        return _extract_list(payload, ("history", "items", "sales", "data", "result"))

    async def fetch_item_info(self, item_id: str) -> dict[str, Any] | None:
        """Информация о предмете, если API её отдаёт; иначе None (не критично)."""
        payload = await self._request(f"/{self._settings.stalzone_region}/items/{item_id}")
        if not isinstance(payload, dict):
            return None
        name = payload.get("name")
        title = ""
        if isinstance(name, dict):
            lines = name.get("lines") or {}
            title = lines.get("ru") or lines.get("en") or ""
        elif isinstance(name, str):
            title = name
        return {"item_id": item_id, "title": title, "category": payload.get("category", "")}


def build_source(settings: Settings) -> Any:
    """Фабрика источника по DATA_SOURCE из .env."""
    if settings.data_source == "mock":
        logger.info("Источник данных: mock (синтетические лоты)")
        return MockSource()
    logger.info("Источник данных: %s (%s)", settings.data_source, settings.resolved_api_base)
    return StalzoneClient(settings)


__all__ = ["MockSource", "RateLimiter", "SourceError", "StalzoneClient", "build_source", "T", "Generic"]
