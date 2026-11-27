"""Тесты модели цены — без сети и БД.

Запуск:  python -m pytest -q
"""

from __future__ import annotations

from services.pricing import (
    build_quote,
    competition,
    matches_filter,
    normalize_lots,
    percentile,
    sales_per_day,
)


def _lot(amount: int, total: float, lot_id: str = "x") -> dict:
    return {"id": lot_id, "amount": amount, "price": total}


def test_percentile_interpolates() -> None:
    assert percentile([], 0.5) == 0.0
    assert percentile([10], 0.9) == 10
    assert percentile([0, 100], 0.5) == 50
    assert percentile([0, 100], 0.75) == 75


def test_lot_unit_price_is_per_item() -> None:
    lots = normalize_lots([_lot(5, 500), _lot(1, 150)])
    assert [round(lot.unit_price, 2) for lot in lots] == [100.0, 150.0]
    assert lots[0].amount == 5


def test_zero_amount_does_not_divide_by_zero() -> None:
    lots = normalize_lots([{"id": "a", "amount": 0, "price": 100}])
    assert lots[0].unit_price == 100


def test_competition_counts_close_prices() -> None:
    prices = [100, 103, 104, 130]
    assert competition(prices, tolerance=0.05) == 3


def test_sales_per_day_averages_units() -> None:
    history = normalize_lots([_lot(2, 200), _lot(3, 300)])
    assert sales_per_day(history, window_days=5) == 1.0


def test_quote_uses_sold_history_and_fee() -> None:
    lots = [_lot(1, 100, "cheap"), _lot(1, 140, "other")]
    history = [_lot(1, 200, "sold-1"), _lot(1, 200, "sold-2")]
    quote = build_quote(lots, history, fee_pct=0.05, window_days=2)
    assert quote is not None
    assert quote.buy_price == 100
    assert quote.sell_target == 200
    assert round(quote.net_sell, 2) == 190.0
    assert round(quote.margin_pct, 2) == 90.0
    assert quote.verdict == "buy"


def test_quote_without_lots_is_none() -> None:
    assert build_quote([], []) is None


def test_quote_without_history_falls_back_to_lot_median() -> None:
    quote = build_quote([_lot(1, 100), _lot(1, 300)], [], fee_pct=0.0)
    assert quote is not None
    assert quote.sell_target == 200


def test_fee_reduces_margin() -> None:
    lots = [_lot(1, 100)]
    history = [_lot(1, 120)]
    no_fee = build_quote(lots, history, fee_pct=0.0)
    with_fee = build_quote(lots, history, fee_pct=0.15)
    assert no_fee is not None and with_fee is not None
    assert with_fee.margin_pct < no_fee.margin_pct


def test_filter_respects_category_and_liquidity() -> None:
    lots = [_lot(1, 100)]
    history = [_lot(1, 200)]
    quote = build_quote(lots, history, fee_pct=0.05, window_days=1)
    assert quote is not None
    assert matches_filter(
        quote,
        "y1q9",
        "weapon/rifle",
        min_margin_pct=10,
        min_sales_per_day=0.5,
        max_competition=10,
        category_prefix="weapon",
    )
    assert not matches_filter(
        quote,
        "y1q9",
        "artifact",
        min_margin_pct=10,
        min_sales_per_day=0.5,
        max_competition=10,
        category_prefix="weapon",
    )
    assert not matches_filter(
        quote,
        "y1q9",
        "weapon/rifle",
        min_margin_pct=500,
        min_sales_per_day=0.5,
        max_competition=10,
    )


def test_filter_with_selected_items_only() -> None:
    lots = [_lot(1, 100)]
    history = [_lot(1, 200)]
    quote = build_quote(lots, history, fee_pct=0.05, window_days=1)
    assert quote is not None

    # Отмечен галочкой — проходит, не отмечен — нет.
    assert matches_filter(
        quote,
        "0rn7d",
        "armor/combat",
        min_margin_pct=10,
        min_sales_per_day=0.5,
        max_competition=10,
        item_ids=["0rn7d", "y1q9"],
    )
    assert not matches_filter(
        quote,
        "5lr71",
        "armor/clothes",
        min_margin_pct=10,
        min_sales_per_day=0.5,
        max_competition=10,
        item_ids=["0rn7d", "y1q9"],
    )
    # Пустой список = все предметы.
    assert matches_filter(
        quote,
        "5lr71",
        "armor/clothes",
        min_margin_pct=10,
        min_sales_per_day=0.5,
        max_competition=10,
        item_ids=[],
    )
