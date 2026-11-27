"""Начальное наполнение: пользователи, watchlist и демо-журнал сделок.

Каталог аукциона содержит больше двух тысяч позиций — обойти их все в
пределах лимита API нельзя, поэтому в мониторинг по умолчанию попадает
компактный набор (`SEED_ITEMS_LIMIT`): предметы берутся по кругу из всех
подкатегорий, чтобы в ленте были и оружие, и броня, и артефакты, и расходники.

Демо-сделки строятся от реальных цен каталога, поэтому цифры в журнале
и в ленте лотов не противоречат друг другу.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select

from config import get_settings
from models.database import SessionLocal
from models.entities import Trade, User, WatchItem, utcnow
from services.auth import hash_password
from services.catalog import get_catalog

logger = logging.getLogger(__name__)

# Если каталога нет — минимальный набор, чтобы приложение не было пустым.
DEFAULT_ITEM_IDS = ["y1q9", "0n9q", "40vn", "zyv9", "9nd0", "ab12", "c3d4", "e5f6"]

# Демо-пользователи: пароли учебные и открыто описаны в README.
DEMO_USERS = [
    {"username": "demo", "password": "demo12345", "display_name": "Демо-аналитик"},
    {"username": "student", "password": "student123", "display_name": "Студент"},
]

# Демо-сделки. Цены не зашиты числом, а считаются от базовой цены предмета:
# так журнал остаётся правдоподобным при любой версии каталога.
#   buy  — коэффициент к базовой цене (0.78 = «купил ниже рынка»);
#   sell — каким получился выход по отношению к покупке.
DEMO_TRADES = [
    {"days_ago": 96, "held": 4, "qty": 3, "buy": 0.78, "sell": 1.31},
    {"days_ago": 74, "held": 6, "qty": 2, "buy": 0.85, "sell": 1.18},
    {"days_ago": 58, "held": 2, "qty": 5, "buy": 0.92, "sell": 0.94},
    {"days_ago": 41, "held": 9, "qty": 1, "buy": 0.71, "sell": 1.44},
    {"days_ago": 27, "held": 3, "qty": 4, "buy": 0.88, "sell": 0.83},
    {"days_ago": 14, "held": 5, "qty": 2, "buy": 0.74, "sell": 1.52},
    {"days_ago": 6, "held": 2, "qty": 6, "buy": 0.81, "sell": 1.27},
]


def _pick_spread(limit: int) -> list[Any]:
    """Берёт предметы по кругу из всех подкатегорий: широкий охват рынка."""
    catalog = get_catalog()
    buckets: dict[tuple[str, str], list[Any]] = {}
    for item in catalog.all():
        buckets.setdefault((item.group, item.subgroup), []).append(item)

    selected: list[Any] = []
    while len(selected) < limit and any(buckets.values()):
        for key in list(buckets):
            if len(selected) >= limit:
                break
            bucket = buckets[key]
            if bucket:
                selected.append(bucket.pop(0))
        if not any(buckets.values()):
            break
    return selected


async def seed_users() -> int:
    """Создаёт демо-пользователей, если их ещё нет."""
    async with SessionLocal() as session:
        existing = {row[0] for row in (await session.execute(select(User.username))).all()}
        created = 0
        for entry in DEMO_USERS:
            if entry["username"] in existing:
                continue
            session.add(
                User(
                    username=entry["username"],
                    password_hash=hash_password(entry["password"]),
                    display_name=entry["display_name"],
                )
            )
            created += 1
        if created:
            await session.commit()
            logger.info("Созданы демо-пользователи: %s", created)
        return created


async def seed_watchlist(source: Any) -> int:
    async with SessionLocal() as session:
        count = (await session.execute(select(func.count()).select_from(WatchItem))).scalar_one()
        if count:
            return 0

        settings = get_settings()
        catalog = get_catalog()
        entries: list[dict[str, Any]] = []

        if len(catalog) and settings.seed_items_limit > 0:
            picked = _pick_spread(settings.seed_items_limit)
            entries = [
                {
                    "item_id": item.id,
                    "title": item.title,
                    "category": item.category,
                    "icon_url": item.icon_url,
                    "priority": 100 + index,
                }
                for index, item in enumerate(picked)
            ]
        else:
            catalog_entries = source.catalog() if hasattr(source, "catalog") else []
            if catalog_entries:
                entries = [
                    {
                        "item_id": row["item_id"],
                        "title": row.get("title", ""),
                        "category": row.get("category", ""),
                        "icon_url": row.get("icon_url", ""),
                        "priority": 100 + index,
                    }
                    for index, row in enumerate(catalog_entries)
                ]
            else:
                entries = [
                    {"item_id": item_id, "title": item_id, "category": "", "priority": 100 + index}
                    for index, item_id in enumerate(DEFAULT_ITEM_IDS)
                ]

        session.add_all(WatchItem(**entry) for entry in entries)
        await session.commit()
        logger.info("Watchlist инициализирован: %s предметов", len(entries))
        return len(entries)


async def seed_demo_trades() -> int:
    """Демо-история сделок для пользователя ``demo`` (пустой журнал скучно защищать)."""
    settings = get_settings()
    async with SessionLocal() as session:
        count = (await session.execute(select(func.count()).select_from(Trade))).scalar_one()
        if count:
            return 0

        owner = (await session.execute(select(User).where(User.username == "demo"))).scalar_one_or_none()
        if owner is None:
            return 0

        items = list(
            (
                await session.execute(
                    select(WatchItem).order_by(WatchItem.priority).limit(40)
                )
            )
            .scalars()
            .all()
        )
        if not items:
            return 0

        catalog = get_catalog()
        now = utcnow()
        trades: list[Trade] = []

        for index, spec in enumerate(DEMO_TRADES):
            item = items[index % len(items)]
            entry = catalog.get(item.item_id)
            base = float(getattr(entry, "base_price", 0) or 0)
            if base <= 0:
                base = 12_000.0 + index * 3_500

            buy_price = round(base * spec["buy"], -1)
            sell_price = round(buy_price * spec["sell"], -1)
            closed_at = now - timedelta(days=spec["days_ago"])
            opened_at = closed_at - timedelta(days=spec["held"])

            trades.append(
                Trade(
                    user_id=owner.username,
                    item_id=item.item_id,
                    title=item.title,
                    quantity=spec["qty"],
                    buy_price=buy_price,
                    sell_price=sell_price,
                    fee_pct=settings.fee_pct,
                    extra_cost=round(buy_price * spec["qty"] * 0.03, -1),
                    note="",
                    opened_at=opened_at,
                    closed_at=closed_at,
                )
            )

        session.add_all(trades)
        await session.commit()
        logger.info("Созданы демо-сделки: %s", len(trades))
        return len(trades)
