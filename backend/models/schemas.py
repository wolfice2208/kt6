"""Pydantic-схемы API (валидация входа и форма ответа)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------- Watchlist ----------


class WatchItemIn(BaseModel):
    item_id: str = Field(min_length=1, max_length=64, description="ID предмета в STALZONE (регистрозависимый)")
    title: str = Field(default="", max_length=255)
    category: str = Field(default="", max_length=128)
    icon_url: str = Field(default="", max_length=512)
    priority: int = Field(default=100, ge=1, le=1000)


class WatchItemPatch(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=128)
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=1, le=1000)


class WatchItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: str
    title: str
    category: str
    icon_url: str
    enabled: bool
    priority: int


class BulkItemsIn(BaseModel):
    item_ids: list[str] = Field(default_factory=list, max_length=5000)


class BulkItemsOut(BaseModel):
    added: int
    skipped: int
    total_tracked: int


class BulkRemoveOut(BaseModel):
    removed: int
    total_tracked: int


class CatalogItemOut(BaseModel):
    id: str
    title: str
    category: str
    group: str
    subgroup: str
    base_price: float
    price_min: float = 0.0
    liquidity: float
    icon_url: str
    tracked: bool = False
    # Цена не с рыночной страницы, а медиана по группе (для редких позиций).
    estimated: bool = False
    # Качество снаряжения (ранг) или редкость артефакта.
    tier_kind: str = ""
    tier_label: str = ""
    tier_value: int = 0
    tier_estimated: bool = False


class CatalogPageOut(BaseModel):
    items: list[CatalogItemOut]
    total: int
    offset: int
    limit: int
    tracked_total: int
    catalog_total: int


class CatalogGroupOut(BaseModel):
    group: str
    count: int


class CatalogMetaOut(BaseModel):
    source: str = ""
    fetched_at: str = ""
    items: int = 0
    price_estimated: int = 0
    price_min: int = 0
    price_median: int = 0
    price_max: int = 0


# ---------- Фильтры ----------


class FilterRuleIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    min_margin_pct: float = Field(default=15.0, ge=0, le=500)
    min_sales_per_day: float = Field(default=0.5, ge=0, le=10_000)
    max_competition: int = Field(default=15, ge=0, le=10_000)
    category_prefix: str = Field(default="", max_length=128)
    # Выбранные галочками предметы. Пустой список — все отслеживаемые.
    item_ids: list[str] = Field(default_factory=list, max_length=3000)
    enabled: bool = True


class FilterRuleOut(FilterRuleIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    created_at: datetime


# ---------- Алерты ----------


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    filter_id: int | None
    item_id: str
    title: str
    margin_pct: float
    buy_price: float
    sell_price: float
    is_read: bool
    created_at: datetime
    # Подставляется из каталога при выдаче: в БД иконки не храним.
    icon_url: str = ""


# ---------- Рынок ----------


class LotOut(BaseModel):
    lot_id: str
    amount: int
    total_price: float
    unit_price: float
    end_time: str | None = None


class PricePointOut(BaseModel):
    ts: datetime
    median_price: float
    buy_price: float
    sell_target: float
    lots_count: int


class QuoteOut(BaseModel):
    buy_price: float
    sell_target: float
    net_sell: float
    fee_pct: float
    margin_pct: float
    margin_abs: float
    median_price: float
    p25_price: float
    p75_price: float
    lots_count: int
    competition: int
    sales_per_day: float
    liquidity_score: float
    verdict: Literal["buy", "watch", "skip"]
    # Качество артефакта у самого дешёвого лота (0 — не артефакт или нет данных).
    quality: int = 0
    quality_label: str = ""
    level: int = 0


class DealOut(BaseModel):
    item_id: str
    title: str
    category: str
    group: str = ""
    icon_url: str = ""
    quality: int = 0
    quality_label: str = ""
    level: int = 0
    level_label: str = ""
    quote: QuoteOut
    updated_at: datetime | None = None
    stale_seconds: float | None = None


class ItemDetailOut(BaseModel):
    item: WatchItemOut
    quote: QuoteOut | None
    lots: list[LotOut]
    history: list[PricePointOut]
    updated_at: datetime | None = None


class HistoryRawOut(BaseModel):
    item_id: str
    points: list[dict[str, Any]]


# ---------- Служебное ----------


class HealthOut(BaseModel):
    status: str
    version: str
    data_source: str
    region: str
    ingestion_enabled: bool
    scan_interval_seconds: int
    last_scan_at: datetime | None
    last_scan_duration_ms: float | None
    scans_total: int
    items_tracked: int
    sse_clients: int
    ws_connections: int
    database: str


class ScanResultOut(BaseModel):
    scanned: int
    deals: int
    alerts: int
    duration_ms: float


class ProfileOut(BaseModel):
    user_id: str
    display_name: str
    avatar_url: str | None
    avatar_version: int


# ---------- Аутентификация ----------


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64, description="Логин")
    password: str = Field(min_length=1, max_length=128, description="Пароль")


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    display_name: str


class TokenOut(BaseModel):
    """Ответ на успешный вход: токен и данные пользователя одним объектом."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Время жизни токена в секундах")
    user: UserOut


# ---------- Журнал сделок ----------


class TradeCalcIn(BaseModel):
    """Вход калькулятора: что и по какой цене купили и продали."""

    quantity: int = Field(default=1, ge=1, le=100_000)
    buy_price: float = Field(ge=0, le=1e12)
    sell_price: float = Field(ge=0, le=1e12)
    fee_pct: float = Field(default=0.05, ge=0, le=1)
    extra_cost: float = Field(default=0.0, ge=0, le=1e12)
    opened_at: datetime | None = None
    closed_at: datetime | None = None

    @model_validator(mode="after")
    def _check_dates(self) -> TradeCalcIn:
        if self.opened_at and self.closed_at and self.closed_at < self.opened_at:
            raise ValueError("Дата закрытия не может быть раньше даты покупки")
        return self


class TradeMathOut(BaseModel):
    """Результат расчёта выгоды (общий для калькулятора и журнала)."""

    quantity: int
    buy_price: float
    sell_price: float
    fee_pct: float
    extra_cost: float
    cost: float
    gross_revenue: float
    fee: float
    net_revenue: float
    profit: float
    roi_pct: float
    holding_days: float
    profit_per_day: float
    is_profitable: bool


class TradeIn(TradeCalcIn):
    """Сохранение сделки в журнал: то же самое плюс предмет и заметка."""

    item_id: str = Field(min_length=1, max_length=64)
    title: str = Field(default="", max_length=255)
    note: str = Field(default="", max_length=2000)


class TradeOut(TradeMathOut):
    model_config = ConfigDict(from_attributes=True)

    id: int
    item_id: str
    title: str
    note: str
    opened_at: datetime
    closed_at: datetime


class MonthProfitOut(BaseModel):
    month: str = Field(description="YYYY-MM")
    profit: float
    trades: int


class ItemProfitOut(BaseModel):
    item_id: str
    title: str
    profit: float
    trades: int


class TradesStatsOut(BaseModel):
    """Сводка журнала: итоги, динамика по месяцам и самые прибыльные предметы."""

    trades_count: int
    profitable_count: int
    losing_count: int
    total_cost: float
    total_revenue: float
    total_profit: float
    roi_pct: float
    win_rate_pct: float
    best_profit: float
    worst_profit: float
    avg_profit: float
    avg_roi_pct: float
    avg_holding_days: float
    profit_per_day: float
    by_month: list[MonthProfitOut] = Field(default_factory=list)
    top_items: list[ItemProfitOut] = Field(default_factory=list)

