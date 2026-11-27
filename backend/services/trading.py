"""Экономика сделки: чистые функции без I/O.

Формула выгоды живёт ровно в одном месте и используется двумя путями:
калькулятором (``POST /api/trades/calculate`` — «посчитать, не сохраняя»)
и журналом сделок (расчёт по сохранённым записям). Поэтому цифры на экране
калькулятора и в отчёте не могут разойтись.

Модель:
    стоимость   = цена_покупки × количество + прочие расходы
    выручка     = цена_продажи × количество
    комиссия    = выручка × ставка_комиссии
    чистая      = выручка − комиссия
    выгода      = чистая − стоимость
    ROI         = выгода / стоимость × 100 %
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import fmean


def _round(value: float, digits: int = 2) -> float:
    return round(float(value), digits)


@dataclass(frozen=True)
class TradeMath:
    """Результат расчёта одной сделки."""

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

    @property
    def is_profitable(self) -> bool:
        return self.profit > 0

    def as_dict(self) -> dict[str, float | int | bool]:
        return {
            "quantity": self.quantity,
            "buy_price": _round(self.buy_price),
            "sell_price": _round(self.sell_price),
            "fee_pct": self.fee_pct,
            "extra_cost": _round(self.extra_cost),
            "cost": _round(self.cost),
            "gross_revenue": _round(self.gross_revenue),
            "fee": _round(self.fee),
            "net_revenue": _round(self.net_revenue),
            "profit": _round(self.profit),
            "roi_pct": _round(self.roi_pct),
            "holding_days": _round(self.holding_days),
            "profit_per_day": _round(self.profit_per_day),
            "is_profitable": self.is_profitable,
        }


def holding_days(opened_at: datetime | None, closed_at: datetime | None) -> float:
    """Сколько дней товар держали в руках. Отрицательное значение — 0."""
    if opened_at is None or closed_at is None:
        return 0.0
    seconds = (closed_at - opened_at).total_seconds()
    if seconds <= 0:
        return 0.0
    return seconds / 86_400


def compute_trade(
    *,
    quantity: int,
    buy_price: float,
    sell_price: float,
    fee_pct: float = 0.05,
    extra_cost: float = 0.0,
    opened_at: datetime | None = None,
    closed_at: datetime | None = None,
) -> TradeMath:
    """Считает выгоду одной сделки. Никаких исключений: мусорные входы дают нули."""
    qty = max(int(quantity or 0), 1)
    buy = max(float(buy_price or 0.0), 0.0)
    sell = max(float(sell_price or 0.0), 0.0)
    fee_rate = min(max(float(fee_pct or 0.0), 0.0), 1.0)
    extra = max(float(extra_cost or 0.0), 0.0)

    cost = buy * qty + extra
    gross_revenue = sell * qty
    fee = gross_revenue * fee_rate
    net_revenue = gross_revenue - fee
    profit = net_revenue - cost
    roi_pct = (profit / cost * 100) if cost > 0 else 0.0

    days = holding_days(opened_at, closed_at)
    # Быстрый перепродажный цикл (внутри дня) считаем как один день: иначе
    # деление на ноль даёт бессмысленный «профит в сутки».
    per_day = profit / max(days, 1.0)

    return TradeMath(
        quantity=qty,
        buy_price=buy,
        sell_price=sell,
        fee_pct=fee_rate,
        extra_cost=extra,
        cost=cost,
        gross_revenue=gross_revenue,
        fee=fee,
        net_revenue=net_revenue,
        profit=profit,
        roi_pct=roi_pct,
        holding_days=days,
        profit_per_day=per_day,
    )


@dataclass(frozen=True)
class PortfolioSummary:
    """Сводка по всем сделкам журнала."""

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

    def as_dict(self) -> dict[str, float | int]:
        return {
            "trades_count": self.trades_count,
            "profitable_count": self.profitable_count,
            "losing_count": self.losing_count,
            "total_cost": _round(self.total_cost),
            "total_revenue": _round(self.total_revenue),
            "total_profit": _round(self.total_profit),
            "roi_pct": _round(self.roi_pct),
            "win_rate_pct": _round(self.win_rate_pct),
            "best_profit": _round(self.best_profit),
            "worst_profit": _round(self.worst_profit),
            "avg_profit": _round(self.avg_profit),
            "avg_roi_pct": _round(self.avg_roi_pct),
            "avg_holding_days": _round(self.avg_holding_days),
            "profit_per_day": _round(self.profit_per_day),
        }


EMPTY_SUMMARY = PortfolioSummary(
    trades_count=0,
    profitable_count=0,
    losing_count=0,
    total_cost=0.0,
    total_revenue=0.0,
    total_profit=0.0,
    roi_pct=0.0,
    win_rate_pct=0.0,
    best_profit=0.0,
    worst_profit=0.0,
    avg_profit=0.0,
    avg_roi_pct=0.0,
    avg_holding_days=0.0,
    profit_per_day=0.0,
)


def summarize(trades: list[TradeMath]) -> PortfolioSummary:
    """Сводка по списку сделок. Пустой список — нули, а не деление на ноль."""
    if not trades:
        return EMPTY_SUMMARY

    profits = [trade.profit for trade in trades]
    total_cost = sum(trade.cost for trade in trades)
    total_revenue = sum(trade.net_revenue for trade in trades)
    total_profit = sum(profits)
    profitable = [trade for trade in trades if trade.profit > 0]

    return PortfolioSummary(
        trades_count=len(trades),
        profitable_count=len(profitable),
        losing_count=len(trades) - len(profitable),
        total_cost=total_cost,
        total_revenue=total_revenue,
        total_profit=total_profit,
        roi_pct=(total_profit / total_cost * 100) if total_cost > 0 else 0.0,
        win_rate_pct=len(profitable) / len(trades) * 100,
        best_profit=max(profits),
        worst_profit=min(profits),
        avg_profit=fmean(profits),
        avg_roi_pct=fmean(trade.roi_pct for trade in trades),
        avg_holding_days=fmean(trade.holding_days for trade in trades),
        profit_per_day=sum(trade.profit_per_day for trade in trades),
    )
