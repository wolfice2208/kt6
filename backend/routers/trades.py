"""Журнал сделок и калькулятор выгоды.

Все эндпоинты, кроме ``/calculate``, работают только со сделками текущего
пользователя: чужую запись нельзя ни прочитать, ни удалить — она просто
не находится (404, а не 403, чтобы не раскрывать существование id).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from deps import SessionDep, UserDep
from models.entities import Trade
from models.schemas import (
    ItemProfitOut,
    MonthProfitOut,
    TradeCalcIn,
    TradeIn,
    TradeMathOut,
    TradeOut,
    TradesStatsOut,
)
from services.trading import compute_trade, summarize

router = APIRouter(prefix="/trades", tags=["trades"])

SortKey = Literal["closed_desc", "closed_asc", "profit_desc", "profit_asc", "roi_desc"]


@router.post(
    "/calculate",
    response_model=TradeMathOut,
    summary="Посчитать выгоду, ничего не сохраняя",
)
async def calculate(payload: TradeCalcIn) -> TradeMathOut:
    """Калькулятор ходит сюда: одна формула на весь проект, без дублей на клиенте."""
    result = compute_trade(
        quantity=payload.quantity,
        buy_price=payload.buy_price,
        sell_price=payload.sell_price,
        fee_pct=payload.fee_pct,
        extra_cost=payload.extra_cost,
        opened_at=payload.opened_at,
        closed_at=payload.closed_at,
    )
    return TradeMathOut.model_validate(result.as_dict())


@router.get("", response_model=list[TradeOut], summary="История сделок")
async def list_trades(
    user_id: UserDep,
    session: SessionDep,
    sort: SortKey = Query(default="closed_desc"),
    item_id: str | None = Query(default=None, description="Фильтр по предмету"),
) -> list[TradeOut]:
    stmt = select(Trade).where(Trade.user_id == user_id)
    if item_id:
        stmt = stmt.where(Trade.item_id == item_id)

    if sort == "closed_asc":
        stmt = stmt.order_by(Trade.closed_at.asc())
    elif sort == "profit_desc":
        stmt = stmt.order_by(Trade.closed_at.desc())
    elif sort == "profit_asc":
        stmt = stmt.order_by(Trade.closed_at.desc())
    else:
        stmt = stmt.order_by(Trade.closed_at.desc())

    trades = list((await session.execute(stmt)).scalars().all())

    # Сортировку по вычисляемым полям делает Python: они не хранятся в БД,
    # поэтому ORDER BY по ним невозможен без денормализации.
    if sort == "profit_desc":
        trades.sort(key=lambda trade: trade.profit, reverse=True)
    elif sort == "profit_asc":
        trades.sort(key=lambda trade: trade.profit)
    elif sort == "roi_desc":
        trades.sort(key=lambda trade: trade.roi_pct, reverse=True)

    return [TradeOut.model_validate(trade) for trade in trades]


@router.get("/stats", response_model=TradesStatsOut, summary="Сводка: итоги, месяцы, предметы")
async def stats(user_id: UserDep, session: SessionDep) -> TradesStatsOut:
    trades = list(
        (await session.execute(select(Trade).where(Trade.user_id == user_id))).scalars().all()
    )
    summary = summarize([trade.math() for trade in trades])

    by_month: dict[str, dict[str, float]] = defaultdict(lambda: {"profit": 0.0, "trades": 0})
    by_item: dict[str, dict[str, float]] = defaultdict(lambda: {"profit": 0.0, "trades": 0})
    titles: dict[str, str] = {}

    for trade in trades:
        month = trade.closed_at.strftime("%Y-%m")
        by_month[month]["profit"] += trade.profit
        by_month[month]["trades"] += 1

        by_item[trade.item_id]["profit"] += trade.profit
        by_item[trade.item_id]["trades"] += 1
        titles.setdefault(trade.item_id, trade.title)

    months = sorted(by_month.items())
    top = sorted(by_item.items(), key=lambda pair: pair[1]["profit"], reverse=True)[:5]

    return TradesStatsOut(
        **summary.as_dict(),
        by_month=[
            MonthProfitOut(month=month, profit=round(data["profit"], 2), trades=int(data["trades"]))
            for month, data in months
        ],
        top_items=[
            ItemProfitOut(
                item_id=item_id,
                title=titles.get(item_id, item_id),
                profit=round(data["profit"], 2),
                trades=int(data["trades"]),
            )
            for item_id, data in top
        ],
    )


@router.post("", response_model=TradeOut, status_code=status.HTTP_201_CREATED, summary="Добавить сделку")
async def create_trade(payload: TradeIn, user_id: UserDep, session: SessionDep) -> TradeOut:
    trade = Trade(
        user_id=user_id,
        item_id=payload.item_id,
        title=payload.title,
        note=payload.note,
        quantity=payload.quantity,
        buy_price=payload.buy_price,
        sell_price=payload.sell_price,
        fee_pct=payload.fee_pct,
        extra_cost=payload.extra_cost,
    )
    # Даты необязательны: если не переданы — берутся «сейчас» из default модели.
    if payload.opened_at is not None:
        trade.opened_at = payload.opened_at
    if payload.closed_at is not None:
        trade.closed_at = payload.closed_at

    session.add(trade)
    await session.commit()
    await session.refresh(trade)
    return TradeOut.model_validate(trade)


@router.get("/{trade_id}", response_model=TradeOut, summary="Сделка по id")
async def get_trade(trade_id: int, user_id: UserDep, session: SessionDep) -> TradeOut:
    trade = (
        await session.execute(
            select(Trade).where(Trade.id == trade_id, Trade.user_id == user_id)
        )
    ).scalar_one_or_none()
    if trade is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сделка не найдена")
    return TradeOut.model_validate(trade)


@router.delete("/{trade_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить сделку")
async def delete_trade(trade_id: int, user_id: UserDep, session: SessionDep) -> None:
    trade = (
        await session.execute(
            select(Trade).where(Trade.id == trade_id, Trade.user_id == user_id)
        )
    ).scalar_one_or_none()
    if trade is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Сделка не найдена")
    await session.delete(trade)
    await session.commit()
