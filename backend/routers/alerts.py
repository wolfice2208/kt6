"""Роутер: персональные уведомления (история срабатываний фильтров)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select, update

from deps import SessionDep, UserDep
from models.entities import Alert
from models.schemas import AlertOut
from services.catalog import get_catalog

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _with_icon(alert: Alert) -> AlertOut:
    payload = AlertOut.model_validate(alert)
    entry = get_catalog().get(alert.item_id)
    if entry is not None:
        payload.icon_url = entry.icon_url
    return payload


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    session: SessionDep,
    user: UserDep,
    unread_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
) -> list[AlertOut]:
    query = select(Alert).where(Alert.user_id == user).order_by(Alert.created_at.desc()).limit(limit)
    if unread_only:
        query = query.where(Alert.is_read.is_(False))
    rows = await session.execute(query)
    return [_with_icon(row) for row in rows.scalars().all()]


@router.get("/unread-count")
async def unread_count(session: SessionDep, user: UserDep) -> dict[str, int]:
    count = await session.execute(
        select(func.count()).select_from(Alert).where(Alert.user_id == user).where(Alert.is_read.is_(False))
    )
    return {"unread": int(count.scalar_one())}


@router.post("/{alert_id}/read", response_model=AlertOut)
async def mark_read(alert_id: int, session: SessionDep, user: UserDep) -> AlertOut:
    alert = (await session.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if alert is None or alert.user_id != user:
        raise HTTPException(status_code=404, detail="Уведомление не найдено")
    alert.is_read = True
    await session.commit()
    await session.refresh(alert)
    return _with_icon(alert)


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(session: SessionDep, user: UserDep) -> None:
    await session.execute(update(Alert).where(Alert.user_id == user).values(is_read=True))
    await session.commit()
