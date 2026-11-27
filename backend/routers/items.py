"""Роутер: watchlist (что мониторим) и карточка предмета."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, desc, func, select

from deps import IngestionDep, SessionDep, UserDep
from models.entities import PriceSnapshot, WatchItem, as_utc, utcnow
from models.schemas import (
    BulkItemsIn,
    BulkItemsOut,
    BulkRemoveOut,
    ItemDetailOut,
    PricePointOut,
    WatchItemIn,
    WatchItemOut,
    WatchItemPatch,
)
from services.catalog import get_catalog

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=list[WatchItemOut])
async def list_watch_items(session: SessionDep) -> list[WatchItem]:
    rows = await session.execute(select(WatchItem).order_by(WatchItem.priority, WatchItem.id))
    return list(rows.scalars().all())


@router.post("/bulk", response_model=BulkItemsOut, status_code=status.HTTP_201_CREATED)
async def add_items_bulk(
    payload: BulkItemsIn, session: SessionDep, ingestion: IngestionDep, _user: UserDep
) -> BulkItemsOut:
    """Добавляет несколько предметов сразу — используется галочками в каталоге."""
    catalog = get_catalog()
    existing = {row[0] for row in (await session.execute(select(WatchItem.item_id))).all()}
    candidates = [item_id for item_id in dict.fromkeys(payload.item_ids) if item_id and item_id not in existing]

    for index, item_id in enumerate(candidates):
        entry = catalog.get(item_id)
        session.add(
            WatchItem(
                item_id=item_id,
                title=entry.title if entry else item_id,
                category=entry.category if entry else "",
                icon_url=entry.icon_url if entry else "",
                priority=200 + index,
            )
        )
    await session.commit()

    if candidates:
        asyncio.create_task(ingestion.scan_once())

    total = int((await session.execute(select(func.count()).select_from(WatchItem))).scalar_one())
    return BulkItemsOut(
        added=len(candidates),
        skipped=len(payload.item_ids) - len(candidates),
        total_tracked=total,
    )


@router.post("/bulk-remove", response_model=BulkRemoveOut)
async def remove_items_bulk(
    payload: BulkItemsIn,
    session: SessionDep,
    ingestion: IngestionDep,
    _user: UserDep,
) -> BulkRemoveOut:
    """Снимает предметы с мониторинга одним запросом.

    Пустой ``item_ids`` означает «снять все» — именно это делает кнопка
    «Снять все» в каталоге. Одна транзакция вместо N запросов: быстрее
    и без частичных состояний, если что-то пойдёт не так.
    """
    ids = [item_id for item_id in dict.fromkeys(payload.item_ids) if item_id]
    if not ids:
        ids = [row[0] for row in (await session.execute(select(WatchItem.item_id))).all()]

    # SQLite ограничивает число параметров в запросе — удаляем пачками.
    removed = 0
    for start in range(0, len(ids), 400):
        chunk = ids[start : start + 400]
        result = await session.execute(delete(WatchItem).where(WatchItem.item_id.in_(chunk)))
        removed += int(result.rowcount or 0)
    await session.commit()

    for item_id in ids:
        ingestion.forget(item_id)

    total = int((await session.execute(select(func.count()).select_from(WatchItem))).scalar_one())
    return BulkRemoveOut(removed=removed, total_tracked=total)


@router.post("", response_model=WatchItemOut, status_code=status.HTTP_201_CREATED)
async def add_watch_item(
    payload: WatchItemIn, session: SessionDep, ingestion: IngestionDep, _user: UserDep
) -> WatchItem:
    exists = await session.execute(select(WatchItem).where(WatchItem.item_id == payload.item_id))
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Предмет уже отслеживается")

    title, category, icon_url = payload.title, payload.category, payload.icon_url
    entry = get_catalog().get(payload.item_id)
    if entry is not None:
        title = title or entry.title
        category = category or entry.category
        icon_url = icon_url or entry.icon_url

    source = ingestion.source
    if not title:
        describe = getattr(source, "describe", None)
        if describe is not None:
            info = describe(payload.item_id) or {}
            title = info.get("title", "")
            category = category or info.get("category", "")
            icon_url = icon_url or info.get("icon_url", "")
        else:
            try:
                info = await source.fetch_item_info(payload.item_id)
            except Exception:  # справочная информация не критична
                info = None
            if info:
                title = info.get("title", "")
                category = category or info.get("category", "")

    item = WatchItem(
        item_id=payload.item_id,
        title=title or payload.item_id,
        category=category,
        icon_url=icon_url,
        priority=payload.priority,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)

    # Не ждём следующего цикла: подтягиваем данные по новому предмету сразу.
    asyncio.create_task(ingestion.scan_once())
    return item


@router.patch("/{item_id}", response_model=WatchItemOut)
async def patch_watch_item(
    item_id: str, payload: WatchItemPatch, session: SessionDep, _user: UserDep
) -> WatchItem:
    item = (await session.execute(select(WatchItem).where(WatchItem.item_id == item_id))).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Предмет не найден")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    await session.commit()
    await session.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watch_item(
    item_id: str, session: SessionDep, ingestion: IngestionDep, _user: UserDep
) -> None:
    result = await session.execute(delete(WatchItem).where(WatchItem.item_id == item_id))
    await session.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Предмет не найден")
    ingestion.forget(item_id)


@router.get("/{item_id}", response_model=ItemDetailOut)
async def get_item(item_id: str, session: SessionDep, ingestion: IngestionDep) -> ItemDetailOut:
    item = (await session.execute(select(WatchItem).where(WatchItem.item_id == item_id))).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Предмет не найден")

    payload = ingestion.best_payload(item_id)
    quote_payload = dict(payload["quote"]) if payload else None
    lots = ingestion.lots.get(item_id, [])

    snapshots = await _load_snapshots(session, item_id)
    return ItemDetailOut(
        item=WatchItemOut.model_validate(item),
        quote=quote_payload,
        lots=lots,
        history=snapshots,
        updated_at=payload.get("updated_at") if payload else None,
    )


@router.get("/{item_id}/history", response_model=list[PricePointOut])
async def get_item_history(item_id: str, session: SessionDep, days: int = 7) -> list[PricePointOut]:
    return await _load_snapshots(session, item_id, days=days)


@router.post("/{item_id}/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_item(item_id: str, ingestion: IngestionDep, _user: UserDep) -> dict[str, str]:
    asyncio.create_task(ingestion.scan_once())
    return {"status": "scheduled", "item_id": item_id}


async def _load_snapshots(session, item_id: str, days: int = 7, limit: int = 300) -> list[PricePointOut]:
    since = utcnow() - timedelta(days=max(1, days))
    rows = await session.execute(
        select(PriceSnapshot)
        .where(PriceSnapshot.item_id == item_id)
        .where(PriceSnapshot.ts >= since)
        .order_by(desc(PriceSnapshot.ts))
        .limit(limit)
    )
    snapshots = list(rows.scalars().all())
    snapshots.reverse()
    return [
        PricePointOut(
            ts=as_utc(row.ts) or utcnow(),
            median_price=round(row.median_price, 2),
            buy_price=round(row.buy_price, 2),
            sell_target=round(row.sell_target, 2),
            lots_count=row.lots_count,
        )
        for row in snapshots
    ]
