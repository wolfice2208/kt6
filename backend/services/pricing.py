"""Модель цены: чистые функции без I/O.

Здесь считается «выгодно ли перепродавать»: лучшая цена выкупа, целевая цена
продажи по истории продаж, маржа с учётом комиссии аукциона, ликвидность
и конкуренция. Функции намеренно не знают ни про HTTP, ни про БД — их можно
тестировать на фикстурах (см. tests/test_pricing.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median as _median
from typing import Any, Iterable, Sequence

# ---------- Разбор «сырых» данных API ----------


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Lot:
    """Лот аукциона с ценой за единицу (в игре лоты продаются стаками).

    ``quality`` — качество артефакта (1–6), ``level`` — прокачка (+0…+15).
    Оба параметра относятся к конкретному экземпляру, а не к типу предмета.
    У снаряжения их нет (0).
    """

    lot_id: str
    amount: int
    total_price: float
    quality: int = 0
    level: int = 0

    @property
    def unit_price(self) -> float:
        if self.amount <= 0:
            return self.total_price
        return self.total_price / self.amount


QUALITY_LABELS: dict[int, str] = {
    1: "Обычное",
    2: "Необычное",
    3: "Особое",
    4: "Редкое",
    5: "Исключительное",
    6: "Легендарное",
    7: "Уникальное",
}


def quality_label(value: int) -> str:
    return QUALITY_LABELS.get(value, "")


def normalize_lot(raw: dict[str, Any]) -> Lot | None:
    """Приводит лот из API к единому виду, устойчиво к разным именам полей."""
    if not isinstance(raw, dict):
        return None
    total = as_float(
        raw.get("price")
        or raw.get("totalPrice")
        or raw.get("currentPrice")
        or raw.get("buyoutPrice")
    )
    amount = as_int(raw.get("amount") or raw.get("quantity") or 1, 1) or 1
    if total <= 0:
        return None
    additional = raw.get("additional") if isinstance(raw.get("additional"), dict) else {}
    quality = as_int(raw.get("quality") or additional.get("quality") or 0, 0)
    if quality < 0 or quality > 6:
        quality = 0
    level = as_int(raw.get("level") or additional.get("level") or 0, 0)
    if level < 0 or level > 15:
        level = 0
    return Lot(
        lot_id=str(raw.get("id") or raw.get("lotId") or ""),
        amount=amount,
        total_price=total,
        quality=quality,
        level=level,
    )


def normalize_lots(raw_lots: Iterable[Any]) -> list[Lot]:
    lots = [lot for lot in (normalize_lot(item) for item in raw_lots) if lot is not None]
    return sorted(lots, key=lambda lot: lot.unit_price)


def normalize_history(raw_history: Iterable[Any]) -> list[Lot]:
    """История продаж: те же поля, но лот уже продан."""
    return normalize_lots(raw_history)


# ---------- Статистика ----------


def percentile(values: Sequence[float], q: float) -> float:
    """Перцентиль с линейной интерполяцией; q в диапазоне 0..1."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, q)) * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def median_price(values: Sequence[float]) -> float:
    return float(_median(values)) if values else 0.0


def competition(unit_prices: Sequence[float], tolerance: float = 0.05) -> int:
    """Сколько лотов стоят в пределах tolerance от лучшей цены."""
    if not unit_prices:
        return 0
    best = min(unit_prices)
    limit = best * (1 + tolerance)
    return sum(1 for price in unit_prices if price <= limit)


def sales_per_day(history: Sequence[Lot], window_days: int) -> float:
    """Оценка ликвидности: сколько единиц товара продаётся в сутки."""
    if not history or window_days <= 0:
        return 0.0
    units = sum(max(lot.amount, 1) for lot in history)
    return round(units / window_days, 2)


# ---------- Итоговая котировка ----------


@dataclass(frozen=True)
class Quote:
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
    verdict: str = "skip"
    quality: int = 0
    level: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "buy_price": round(self.buy_price, 2),
            "sell_target": round(self.sell_target, 2),
            "net_sell": round(self.net_sell, 2),
            "fee_pct": self.fee_pct,
            "margin_pct": round(self.margin_pct, 2),
            "margin_abs": round(self.margin_abs, 2),
            "median_price": round(self.median_price, 2),
            "p25_price": round(self.p25_price, 2),
            "p75_price": round(self.p75_price, 2),
            "lots_count": self.lots_count,
            "competition": self.competition,
            "sales_per_day": self.sales_per_day,
            "liquidity_score": round(self.liquidity_score, 2),
            "verdict": self.verdict,
            "quality": self.quality,
            "quality_label": quality_label(self.quality),
            "level": self.level,
        }


def build_quote(
    raw_lots: Iterable[Any],
    raw_history: Iterable[Any],
    *,
    fee_pct: float = 0.05,
    competition_tolerance: float = 0.05,
    window_days: int = 7,
    min_margin_pct: float = 15.0,
    min_sales_per_day: float = 0.5,
    max_competition: int = 15,
) -> Quote | None:
    """Считает котировку по текущим лотам и истории продаж.

    Логика:
    * выкуп — по лучшей (минимальной) цене за единицу среди активных лотов;
    * продажа — по 75-му перцентилю цен *проданных* лотов (а не выставленных:
      выставленные включают «мёртвые» лоты с завышенной ценой);
    * маржа — после вычета комиссии аукциона;
    * вердикт — buy, если маржа и ликвидность проходят пороги фильтра.
    """
    lots = normalize_lots(raw_lots)
    if not lots:
        return None

    history = normalize_history(raw_history)
    unit_prices = [lot.unit_price for lot in lots]
    history_prices = [lot.unit_price for lot in history]

    buy_price = unit_prices[0]
    if history_prices:
        sell_target = percentile(history_prices, 0.75)
        if sell_target < buy_price:
            # История дешевле текущего лучшего лота — рынок сдвинулся вниз,
            # ориентируемся на лучшую альтернативу из активных лотов.
            sell_target = percentile(unit_prices, 0.25)
    else:
        # Нет истории — консервативно берём медиану активных лотов.
        sell_target = median_price(unit_prices)

    net_sell = sell_target * (1 - fee_pct)
    margin_abs = net_sell - buy_price
    margin_pct = (margin_abs / buy_price * 100) if buy_price > 0 else 0.0

    competition_count = competition(unit_prices, competition_tolerance)
    sales = sales_per_day(history, window_days)
    liquidity = sales / (1 + competition_count / 5)

    verdict = "skip"
    if (
        margin_pct >= min_margin_pct
        and sales >= min_sales_per_day
        and competition_count <= max_competition
    ):
        verdict = "buy"
    elif margin_pct >= min_margin_pct * 0.5:
        verdict = "watch"

    return Quote(
        buy_price=buy_price,
        sell_target=sell_target,
        net_sell=net_sell,
        fee_pct=fee_pct,
        margin_pct=margin_pct,
        margin_abs=margin_abs,
        median_price=median_price(unit_prices),
        p25_price=percentile(unit_prices, 0.25),
        p75_price=percentile(unit_prices, 0.75),
        lots_count=len(lots),
        competition=competition_count,
        sales_per_day=sales,
        liquidity_score=liquidity,
        verdict=verdict,
        quality=lots[0].quality,
        level=lots[0].level,
    )


def matches_filter(
    quote: Quote,
    item_id: str,
    item_category: str,
    *,
    min_margin_pct: float,
    min_sales_per_day: float,
    max_competition: int,
    category_prefix: str = "",
    item_ids: Sequence[str] = (),
) -> bool:
    """Проходит ли котировка под правила пользовательского фильтра.

    ``item_ids`` — предметы, отмеченные галочками в фильтре. Пустой список
    означает «все отслеживаемые предметы».
    """
    if item_ids and item_id not in item_ids:
        return False
    if category_prefix and not item_category.lower().startswith(category_prefix.lower()):
        return False
    return (
        quote.margin_pct >= min_margin_pct
        and quote.sales_per_day >= min_sales_per_day
        and quote.competition <= max_competition
        and quote.verdict != "skip"
    )
