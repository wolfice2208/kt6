"""Mock-источник данных.

Нужен для двух вещей:
1) разработка и тесты без сети и без токена;
2) страховка на защите — если API недоступен, приложение всё равно
   показывает живую, меняющуюся картину рынка.

Цены детерминированы для пары (item_id, окно времени): в пределах окна
данные стабильны, между окнами — «двигаются», чтобы live-обновления были видны.
Названия и категории берутся из каталога, поэтому в интерфейсе видны
настоящие игровые предметы.
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from typing import Any

from services.catalog import get_catalog


def _seed(item_id: str) -> int:
    digest = hashlib.sha256(item_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


class MockSource:
    """Имитация аукциона: стабильные правила + медленный дрейф цены."""

    name = "mock"

    def __init__(self, tick_seconds: int = 20) -> None:
        self._tick_seconds = tick_seconds
        self._catalog = get_catalog()

    # --- служебное ---

    def catalog(self) -> list[dict[str, Any]]:
        """Список предметов для стартового watchlist."""
        return [
            {
                "item_id": item.id,
                "title": item.title,
                "category": item.category,
                "icon_url": item.icon_url,
                "priority": 100 + index,
            }
            for index, item in enumerate(self._catalog.all())
        ]

    def describe(self, item_id: str) -> dict[str, Any]:
        return self._catalog.describe(item_id)

    def _base(self, item_id: str) -> tuple[float, float]:
        item = self._catalog.get(item_id)
        if item is not None:
            return item.base_price, item.liquidity
        seed = _seed(item_id)
        return 10_000.0 + seed % 90_000, 0.5 + (seed % 40) / 10

    def _drift(self, item_id: str) -> float:
        """Плавное изменение цены во времени — чтобы график и лента «жили»."""
        tick = int(time.time() // self._tick_seconds)
        rng = random.Random(_seed(item_id) ^ tick)
        wave = math.sin(time.time() / 900 + (_seed(item_id) % 100) / 10) * 0.05
        return 1.0 + wave + rng.uniform(-0.015, 0.015)

    # --- контракт источника ---

    def _is_artifact(self, item_id: str) -> bool:
        item = self._catalog.get(item_id)
        return bool(item and item.category.startswith("artefact/"))

    def _quality_multiplier(self, quality: int) -> float:
        # Запасной коэффициент, если по предмету нет реальной матрицы цен.
        return {1: 1.0, 2: 1.08, 3: 1.18, 4: 1.32, 5: 1.52, 6: 1.78, 7: 2.2}.get(quality, 1.0)

    def _real_prices(self, item_id: str) -> dict[str, dict[str, dict]] | None:
        item = self._catalog.get(item_id)
        return item.prices if item and item.prices else None

    async def fetch_lots(self, item_id: str, limit: int = 50) -> list[dict[str, Any]]:
        base, _liquidity = self._base(item_id)
        price_level = base * self._drift(item_id)
        rng = random.Random(_seed(item_id) ^ int(time.time() // 5))
        is_artifact = self._is_artifact(item_id)
        real_prices = self._real_prices(item_id)

        lots: list[dict[str, Any]] = []
        now = int(time.time())

        if real_prices:
            # Есть реальная матрица «качество × диапазон прокачки»: генерируем
            # лоты вокруг фактических цен, без каких-либо потолков.
            for quality_key, bands in real_prices.items():
                try:
                    quality = int(quality_key) + 1  # в игре ступени 1..7
                except ValueError:
                    continue
                for band_keys, cell in bands.items():
                    price = float(cell.get("price") or 0)
                    if price <= 0:
                        continue
                    low, _, high = band_keys.partition("-")
                    level_low = int(low)
                    level_high = int(high) if high else level_low
                    for _ in range(rng.randint(1, 3)):
                        level = rng.randint(level_low, level_high)
                        unit = price * rng.uniform(0.88, 1.12)
                        if rng.random() < 0.25:
                            unit *= rng.uniform(0.85, 0.95)  # срочный лот
                        total = max(1.0, round(unit))
                        lots.append(
                            {
                                "id": f"{item_id}-{len(lots)}",
                                "amount": 1 if is_artifact else rng.choice([1, 1, 2, 3, 5]),
                                "price": total,
                                "quality": quality if is_artifact else 0,
                                "level": level if is_artifact else 0,
                                "startTime": now - rng.randint(60, 3600),
                                "endTime": now + rng.randint(3600, 86_400),
                            }
                        )
            if lots:
                # Не обрезаем по цене: дорогие качества/прокачка должны попасть в группы,
                # иначе в ленте останутся только дешёвые ступени.
                return lots[:160]

        # Фолбэк: рынок вокруг базовой цены (для предметов без статистики).
        quality_weights = [10, 9, 14, 18, 44, 50, 5]
        count = rng.randint(6, min(max(limit, 10), 24))
        for index in range(count):
            amount = 1 if is_artifact else rng.choice([1, 1, 1, 2, 3, 5, 10])
            unit = price_level * rng.uniform(0.88, 1.12)
            if index == 0 and rng.random() < 0.4:
                unit = price_level * rng.uniform(0.82, 0.92)
            quality = 0
            level = 0
            if is_artifact:
                quality = rng.choices([1, 2, 3, 4, 5, 6, 7], weights=quality_weights, k=1)[0]
                level = rng.choices(
                    list(range(16)),
                    weights=[6, 6, 6, 5, 5, 5, 4, 4, 4, 3, 3, 3, 2, 2, 1, 1],
                    k=1,
                )[0]
                unit *= self._quality_multiplier(quality) * (1 + 0.02 * level)
            total = max(1.0, round(unit * amount))
            lots.append(
                {
                    "id": f"{item_id}-{index}",
                    "amount": amount,
                    "price": total,
                    "quality": quality,
                    "level": level,
                    "startTime": now - rng.randint(60, 3600),
                    "endTime": now + rng.randint(3600, 86_400),
                }
            )
        return lots

    async def fetch_history(self, item_id: str, limit: int = 200) -> list[dict[str, Any]]:
        base, liquidity = self._base(item_id)
        price_level = base * self._drift(item_id)
        rng = random.Random(_seed(item_id) ^ 0xABCD)
        now = time.time()
        history: list[dict[str, Any]] = []
        real_prices = self._real_prices(item_id)

        if real_prices and self._is_artifact(item_id):
            # Продажи по качествам/прокачке: чтобы маржа считалась «как за свой класс».
            for quality_key, bands in real_prices.items():
                try:
                    quality = int(quality_key) + 1
                except ValueError:
                    continue
                for band_keys, cell in bands.items():
                    price = float(cell.get("price") or 0)
                    if price <= 0:
                        continue
                    low, _, high = band_keys.partition("-")
                    level_low = int(low)
                    level_high = int(high) if high else level_low
                    sold = max(1, min(12, int(cell.get("lots_month") or 0) // 10 or 1))
                    for _ in range(sold):
                        level = rng.randint(level_low, level_high)
                        unit = price * rng.uniform(0.94, 1.06)
                        history.append(
                            {
                                "id": f"{item_id}-sold-{len(history)}",
                                "amount": 1,
                                "price": round(unit),
                                "quality": quality,
                                "level": level,
                                "time": int(now - rng.uniform(0, 7) * 86_400),
                            }
                        )
            history.sort(key=lambda row: row["time"], reverse=True)
            return history[: max(limit, 60)]

        sold_count = max(3, int(liquidity * 7 * rng.uniform(0.6, 1.3)))
        for index in range(min(sold_count, limit)):
            age_days = rng.uniform(0, 7)
            amount = rng.choice([1, 1, 2, 3, 5])
            unit = price_level * rng.uniform(0.94, 1.06)
            history.append(
                {
                    "id": f"{item_id}-sold-{index}",
                    "amount": amount,
                    "price": max(1.0, round(unit * amount / 10) * 10),
                    "time": int(now - age_days * 86_400),
                }
            )
        history.sort(key=lambda row: row["time"], reverse=True)
        return history
