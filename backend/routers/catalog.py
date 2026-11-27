"""Роутер: каталог предметов аукциона.

Каталог собран из официальной базы EXBO и цен аукциона (tools/build_catalog.py).
Здесь пагинация, поиск, фильтр по качеству/редкости и сортировка — всё на сервере:
отдавать 1127 позиций в браузер одним куском незачем.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from sqlalchemy import select

from config import get_settings
from deps import SessionDep
from models.entities import WatchItem
from models.schemas import CatalogGroupOut, CatalogItemOut, CatalogMetaOut, CatalogPageOut
from services.catalog import CatalogItem, get_catalog, get_catalog_meta

router = APIRouter(prefix="/catalog", tags=["catalog"])

SortKey = Literal["default", "title", "price_asc", "price_desc", "tier_asc", "tier_desc"]


def _to_out(item: CatalogItem, tracked: set[str]) -> CatalogItemOut:
    return CatalogItemOut(
        id=item.id,
        title=item.title,
        category=item.category,
        group=item.group,
        subgroup=item.subgroup,
        base_price=item.base_price,
        price_min=item.price_min,
        liquidity=item.liquidity,
        icon_url=item.icon_url,
        tracked=item.id in tracked,
        estimated=item.estimated,
        tier_kind=item.tier_kind,
        tier_label=item.tier_label,
        tier_value=item.tier_value,
        tier_estimated=item.tier_estimated,
    )


@router.get("", response_model=CatalogPageOut)
async def list_catalog(
    session: SessionDep,
    search: str = Query("", max_length=80),
    group: str = Query("", max_length=80),
    tracked_only: bool = False,
    tier: int | None = Query(None, ge=1, le=5, description="Качество/редкость 1–5"),
    sort: SortKey = "default",
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> CatalogPageOut:
    tracked = {row[0] for row in (await session.execute(select(WatchItem.item_id))).all()}
    items = get_catalog().search(search, group, tracked_ids=tracked, tracked_only=tracked_only)
    if tier is not None:
        items = [item for item in items if item.tier_value == tier]

    if sort == "title":
        items.sort(key=lambda item: item.title.lower())
    elif sort == "price_asc":
        items.sort(key=lambda item: (item.base_price, item.title.lower()))
    elif sort == "price_desc":
        items.sort(key=lambda item: (-item.base_price, item.title.lower()))
    elif sort == "tier_asc":
        # сначала предметы с известным качеством, от низкого к высокому
        items.sort(key=lambda item: (item.tier_value == 0, item.tier_value, item.title.lower()))
    elif sort == "tier_desc":
        items.sort(key=lambda item: (item.tier_value == 0, -item.tier_value, item.title.lower()))

    page = items[offset : offset + limit]
    return CatalogPageOut(
        items=[_to_out(item, tracked) for item in page],
        total=len(items),
        offset=offset,
        limit=limit,
        tracked_total=len(tracked),
        catalog_total=len(get_catalog()),
    )


@router.get("/groups", response_model=list[CatalogGroupOut])
async def list_groups() -> list[CatalogGroupOut]:
    return [CatalogGroupOut(**row) for row in get_catalog().groups()]


@router.get("/meta", response_model=CatalogMetaOut)
async def catalog_meta() -> CatalogMetaOut:
    """Дата и источник цен каталога — чтобы интерфейс не врал про «актуальность»."""
    return CatalogMetaOut(**get_catalog_meta())


@router.get("/ids")
async def catalog_ids(
    session: SessionDep,
    search: str = Query("", max_length=80),
    group: str = Query("", max_length=80),
    tracked_only: bool = False,
    tier: int | None = Query(None, ge=1, le=5),
) -> dict:
    """Все id под текущий поиск — для кнопок «отслеживать все / снять все»."""
    tracked = {row[0] for row in (await session.execute(select(WatchItem.item_id))).all()}
    items = get_catalog().search(search, group, tracked_ids=tracked, tracked_only=tracked_only)
    if tier is not None:
        items = [item for item in items if item.tier_value == tier]
    return {"ids": [item.id for item in items], "total": len(items)}


@router.get("/by-ids", response_model=list[CatalogItemOut])
async def items_by_ids(
    session: SessionDep,
    ids: str = Query("", max_length=8000, description="Список id через запятую"),
) -> list[CatalogItemOut]:
    """Названия и иконки для уже выбранных предметов (нужно фильтрам и алертам)."""
    catalog = get_catalog()
    tracked = {row[0] for row in (await session.execute(select(WatchItem.item_id))).all()}
    wanted = [part.strip() for part in ids.split(",") if part.strip()]
    limit = get_settings().catalog_lookup_limit
    result: list[CatalogItemOut] = []
    for item_id in wanted[:limit]:
        item = catalog.get(item_id)
        if item is not None:
            result.append(_to_out(item, tracked))
    return result
