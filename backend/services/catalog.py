"""Каталог предметов STALZONE.

`catalog.json` собран из официальной базы предметов EXBO
(https://github.com/EXBO-Studio/stalzone-database): id, русское название,
категория, группа, ориентировочная цена и ликвидность, путь к иконке.

Каталог нужен, чтобы в интерфейсе были человеческие названия и группировка,
а не «Предмет y1q9». Иконки берутся из того же репозитория по ссылке.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CatalogItem:
    id: str
    title: str
    category: str
    group: str
    subgroup: str
    base_price: float
    liquidity: float
    icon: str
    estimated: bool = False
    tier_kind: str = ""      # rank — ранг снаряжения, rarity — редкость артефакта
    tier_label: str = ""
    tier_value: int = 0
    tier_estimated: bool = False
    # Реальные цены по качеству и диапазону прокачки (из API аукциона).
    prices: dict[str, dict[str, dict]] | None = None
    price_min: float = 0.0
    lots_per_day: float = 0.0

    @property
    def icon_url(self) -> str:
        base = get_settings().icon_base_url.rstrip("/")
        return f"{base}/{self.icon}"


class Catalog:
    def __init__(self, items: list[CatalogItem]) -> None:
        self._items = items
        self._by_id = {item.id: item for item in items}

    def __len__(self) -> int:
        return len(self._items)

    def all(self) -> list[CatalogItem]:
        return list(self._items)

    def get(self, item_id: str) -> CatalogItem | None:
        return self._by_id.get(item_id)

    def search(
        self,
        query: str = "",
        group: str = "",
        tracked_ids: set[str] | None = None,
        tracked_only: bool = False,
    ) -> list[CatalogItem]:
        text = query.strip().lower()
        result = []
        for item in self._items:
            if group and item.group != group:
                continue
            if tracked_only and tracked_ids is not None and item.id not in tracked_ids:
                continue
            if text and text not in item.title.lower() and text not in item.id.lower():
                continue
            result.append(item)
        return result

    def groups(self) -> list[dict[str, Any]]:
        counter: dict[str, int] = {}
        for item in self._items:
            counter[item.group] = counter.get(item.group, 0) + 1
        return [{"group": group, "count": count} for group, count in sorted(counter.items())]

    def describe(self, item_id: str) -> dict[str, Any]:
        """Название/категория/иконка по id; для неизвестных — аккуратная заглушка."""
        item = self._by_id.get(item_id)
        if item is not None:
            return {
                "item_id": item.id,
                "title": item.title,
                "category": item.category,
                "group": item.group,
                "icon_url": item.icon_url,
                "base_price": item.base_price,
                "liquidity": item.liquidity,
            }
        return {
            "item_id": item_id,
            "title": f"Неизвестный предмет ({item_id})",
            "category": "unknown",
            "group": "Без категории",
            "icon_url": "",
            "base_price": 20_000.0,
            "liquidity": 1.0,
        }


@lru_cache
def get_catalog_meta() -> dict[str, Any]:
    """Когда и откуда собраны цены каталога."""
    path = get_settings().catalog_meta_file
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Не удалось прочитать %s", path)
        return {}


@lru_cache
def get_catalog() -> Catalog:
    settings = get_settings()
    path: Path = settings.catalog_file
    if not path.exists():
        logger.warning("Каталог предметов не найден: %s", path)
        return Catalog([])

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("Не удалось прочитать каталог предметов")
        return Catalog([])

    items = [
        CatalogItem(
            id=str(row["id"]),
            title=str(row.get("title") or row["id"]),
            category=str(row.get("category") or "unknown"),
            group=str(row.get("group") or "Без категории"),
            subgroup=str(row.get("subgroup") or ""),
            base_price=float(row.get("base_price") or 10_000),
            liquidity=float(row.get("liquidity") or 1.0),
            icon=str(row.get("icon") or ""),
            estimated=bool(row.get("estimated") or False),
            tier_kind=str(row.get("tier_kind") or ""),
            tier_label=str(row.get("tier_label") or ""),
            tier_value=int(row.get("tier_value") or 0),
            tier_estimated=bool(row.get("tier_estimated") or False),
            prices=row.get("prices") or None,
            price_min=float(row.get("price_min") or 0),
            lots_per_day=float(row.get("lots_per_day") or 0),
        )
        for row in raw
        if isinstance(row, dict) and row.get("id")
    ]
    logger.info("Каталог предметов загружен: %s позиций", len(items))
    return Catalog(items)
