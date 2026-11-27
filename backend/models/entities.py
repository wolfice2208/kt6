"""ORM-модели приложения."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base
from services.trading import TradeMath, compute_trade


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite возвращает naive-datetime — приводим к UTC, чтобы не смешивать."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class User(Base):
    """Пользователь приложения (вход по логину и паролю, сессия — JWT)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WatchItem(Base):
    """Предмет, который мы отслеживаем (watchlist)."""

    __tablename__ = "watch_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    category: Mapped[str] = mapped_column(String(128), default="")
    icon_url: Mapped[str] = mapped_column(String(512), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FilterRule(Base):
    """Пользовательский фильтр: какие лоты считать выгодными."""

    __tablename__ = "filter_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    min_margin_pct: Mapped[float] = mapped_column(Float, default=15.0)
    min_sales_per_day: Mapped[float] = mapped_column(Float, default=0.5)
    max_competition: Mapped[int] = mapped_column(Integer, default=15)
    category_prefix: Mapped[str] = mapped_column(String(128), default="")
    item_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PriceSnapshot(Base):
    """Снимок рынка по предмету: результат одного обхода воркером."""

    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[str] = mapped_column(String(64), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    buy_price: Mapped[float] = mapped_column(Float, default=0.0)
    sell_target: Mapped[float] = mapped_column(Float, default=0.0)
    margin_pct: Mapped[float] = mapped_column(Float, default=0.0)
    median_price: Mapped[float] = mapped_column(Float, default=0.0)
    p75_price: Mapped[float] = mapped_column(Float, default=0.0)
    p25_price: Mapped[float] = mapped_column(Float, default=0.0)
    lots_count: Mapped[int] = mapped_column(Integer, default=0)
    competition: Mapped[int] = mapped_column(Integer, default=0)
    sales_per_day: Mapped[float] = mapped_column(Float, default=0.0)
    liquidity_score: Mapped[float] = mapped_column(Float, default=0.0)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Alert(Base):
    """Срабатывание фильтра — персональное уведомление пользователю."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    filter_id: Mapped[int | None] = mapped_column(ForeignKey("filter_rules.id"), nullable=True)
    item_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    margin_pct: Mapped[float] = mapped_column(Float, default=0.0)
    buy_price: Mapped[float] = mapped_column(Float, default=0.0)
    sell_price: Mapped[float] = mapped_column(Float, default=0.0)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Trade(Base):
    """Сделка журнала: купил N единиц по одной цене, продал по другой.

    Хранятся только «сырые» входные данные; выгода, ROI и срок удержания
    вычисляются из них (см. ``services/trading.py``) — так формула существует
    в одном месте и одинаково работает и в калькуляторе, и в статистике.
    """

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    item_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    buy_price: Mapped[float] = mapped_column(Float, default=0.0)
    sell_price: Mapped[float] = mapped_column(Float, default=0.0)
    fee_pct: Mapped[float] = mapped_column(Float, default=0.05)
    extra_cost: Mapped[float] = mapped_column(Float, default=0.0)
    note: Mapped[str] = mapped_column(Text, default="")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    def math(self) -> TradeMath:
        return compute_trade(
            quantity=self.quantity,
            buy_price=self.buy_price,
            sell_price=self.sell_price,
            fee_pct=self.fee_pct,
            extra_cost=self.extra_cost,
            opened_at=as_utc(self.opened_at),
            closed_at=as_utc(self.closed_at),
        )

    # Производные величины дублируются свойствами: Pydantic читает их
    # через from_attributes, а SQL остаётся компактным. Округление до копеек
    # делается здесь же, чтобы ответ API совпадал с калькулятором.
    @property
    def cost(self) -> float:
        return round(self.math().cost, 2)

    @property
    def gross_revenue(self) -> float:
        return round(self.math().gross_revenue, 2)

    @property
    def fee(self) -> float:
        return round(self.math().fee, 2)

    @property
    def net_revenue(self) -> float:
        return round(self.math().net_revenue, 2)

    @property
    def profit(self) -> float:
        return round(self.math().profit, 2)

    @property
    def roi_pct(self) -> float:
        return round(self.math().roi_pct, 2)

    @property
    def holding_days(self) -> float:
        return round(self.math().holding_days, 2)

    @property
    def profit_per_day(self) -> float:
        return round(self.math().profit_per_day, 2)

    @property
    def is_profitable(self) -> bool:
        return self.math().is_profitable
