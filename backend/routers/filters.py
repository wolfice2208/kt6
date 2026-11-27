"""Роутер: пользовательские фильтры (какие лоты считать выгодными)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, update

from deps import IngestionDep, SessionDep, UserDep
from models.entities import Alert, FilterRule, WatchItem
from models.schemas import FilterRuleIn, FilterRuleOut
from services.catalog import get_catalog

router = APIRouter(prefix="/filters", tags=["filters"])


async def _ensure_tracked(session, item_ids: list[str]) -> int:
    """Предметы из фильтра автоматически попадают в мониторинг.

    Иначе можно отметить галочкой предмет, который воркер не обходит,
    и фильтр молча ничего не найдёт.
    """
    if not item_ids:
        return 0
    existing = {row[0] for row in (await session.execute(select(WatchItem.item_id))).all()}
    catalog = get_catalog()
    added = 0
    for item_id in dict.fromkeys(item_ids):
        if not item_id or item_id in existing:
            continue
        entry = catalog.get(item_id)
        session.add(
            WatchItem(
                item_id=item_id,
                title=entry.title if entry else item_id,
                category=entry.category if entry else "",
                icon_url=entry.icon_url if entry else "",
                priority=300,
            )
        )
        added += 1
    return added


@router.get("", response_model=list[FilterRuleOut])
async def list_filters(session: SessionDep, user: UserDep) -> list[FilterRule]:
    rows = await session.execute(
        select(FilterRule).where(FilterRule.user_id == user).order_by(FilterRule.id)
    )
    return list(rows.scalars().all())


@router.post("", response_model=FilterRuleOut, status_code=status.HTTP_201_CREATED)
async def create_filter(
    payload: FilterRuleIn,
    session: SessionDep,
    user: UserDep,
    ingestion: IngestionDep,
) -> FilterRule:
    rule = FilterRule(user_id=user, **payload.model_dump())
    session.add(rule)
    added = await _ensure_tracked(session, payload.item_ids)
    await session.commit()
    await session.refresh(rule)
    if added:
        asyncio.create_task(ingestion.scan_once())
    return rule


@router.patch("/{rule_id}", response_model=FilterRuleOut)
async def update_filter(
    rule_id: int,
    payload: FilterRuleIn,
    session: SessionDep,
    user: UserDep,
    ingestion: IngestionDep,
) -> FilterRule:
    rule = (await session.execute(select(FilterRule).where(FilterRule.id == rule_id))).scalar_one_or_none()
    if rule is None or rule.user_id != user:
        raise HTTPException(status_code=404, detail="Фильтр не найден")
    for field, value in payload.model_dump().items():
        setattr(rule, field, value)
    added = await _ensure_tracked(session, payload.item_ids)
    await session.commit()
    await session.refresh(rule)
    if added:
        asyncio.create_task(ingestion.scan_once())
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_filter(rule_id: int, session: SessionDep, user: UserDep) -> None:
    rule = (await session.execute(select(FilterRule).where(FilterRule.id == rule_id))).scalar_one_or_none()
    if rule is None or rule.user_id != user:
        raise HTTPException(status_code=404, detail="Фильтр не найден")
    # История алертов остаётся у пользователя: отвязываем её от удаляемого фильтра,
    # иначе внешний ключ не даст удалить правило.
    await session.execute(update(Alert).where(Alert.filter_id == rule_id).values(filter_id=None))
    await session.delete(rule)
    await session.commit()
