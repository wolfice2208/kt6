"""Тесты экономики сделки: чистые функции, без БД и HTTP."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.trading import compute_trade, holding_days, summarize


def _dt(days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


def test_basic_profit_and_roi() -> None:
    result = compute_trade(quantity=3, buy_price=10_000, sell_price=15_000, fee_pct=0.05, extra_cost=500)
    assert result.gross_revenue == 45_000
    assert result.fee == 2_250
    assert result.net_revenue == 42_750
    assert result.cost == 30_500
    assert result.profit == 12_250
    assert result.roi_pct == pytest.approx(12_250 / 30_500 * 100)
    assert result.is_profitable


def test_zero_fee_means_full_revenue() -> None:
    result = compute_trade(quantity=1, buy_price=100, sell_price=130, fee_pct=0)
    assert result.fee == 0
    assert result.profit == 30


def test_losing_trade() -> None:
    result = compute_trade(quantity=2, buy_price=10_000, sell_price=8_000, fee_pct=0.05)
    assert result.profit < 0
    assert result.is_profitable is False
    assert result.roi_pct < 0


def test_quantity_scales_linearly() -> None:
    one = compute_trade(quantity=1, buy_price=1_000, sell_price=1_500, fee_pct=0.05)
    five = compute_trade(quantity=5, buy_price=1_000, sell_price=1_500, fee_pct=0.05)
    assert five.profit == pytest.approx(one.profit * 5)
    assert five.roi_pct == pytest.approx(one.roi_pct), "ROI не зависит от объёма"


def test_extra_costs_reduce_profit_and_roi() -> None:
    clean = compute_trade(quantity=1, buy_price=1_000, sell_price=2_000, fee_pct=0.05, extra_cost=0)
    with_costs = compute_trade(quantity=1, buy_price=1_000, sell_price=2_000, fee_pct=0.05, extra_cost=400)
    assert with_costs.profit == pytest.approx(clean.profit - 400)
    assert with_costs.roi_pct < clean.roi_pct


def test_holding_period_and_profit_per_day() -> None:
    result = compute_trade(
        quantity=1,
        buy_price=1_000,
        sell_price=1_500,
        fee_pct=0.05,
        opened_at=_dt(10),
        closed_at=_dt(6),
    )
    assert result.holding_days == pytest.approx(4, abs=0.01)
    assert result.profit_per_day == pytest.approx(result.profit / 4, abs=0.05)


def test_intraday_trade_counts_as_one_day() -> None:
    moment = _dt(0)
    result = compute_trade(
        quantity=1,
        buy_price=1_000,
        sell_price=1_200,
        opened_at=moment,
        closed_at=moment,
    )
    assert result.holding_days == 0
    assert result.profit_per_day == pytest.approx(result.profit), "не делим на ноль"


def test_garbage_inputs_do_not_raise() -> None:
    result = compute_trade(quantity=0, buy_price=-5, sell_price=-1, fee_pct=5, extra_cost=-100)
    assert result.quantity == 1
    assert result.buy_price == 0
    assert result.fee_pct == 1
    assert result.cost == 0
    assert result.profit == 0
    assert result.roi_pct == 0


def test_holding_days_helper() -> None:
    now = datetime.now(timezone.utc)
    assert holding_days(None, now) == 0
    assert holding_days(now, now) == 0
    assert holding_days(now, now - timedelta(days=1)) == 0, "отрицательный срок — это ноль"
    assert holding_days(now - timedelta(days=2), now) == pytest.approx(2)


def test_summarize_empty() -> None:
    summary = summarize([])
    assert summary.trades_count == 0
    assert summary.total_profit == 0
    assert summary.roi_pct == 0
    assert summary.win_rate_pct == 0


def test_summarize_mixed_portfolio() -> None:
    trades = [
        compute_trade(quantity=1, buy_price=1_000, sell_price=2_000, fee_pct=0),   # +1000
        compute_trade(quantity=1, buy_price=1_000, sell_price=1_500, fee_pct=0),   # +500
        compute_trade(quantity=1, buy_price=1_000, sell_price=500, fee_pct=0),     # -500
    ]
    summary = summarize(trades)
    assert summary.trades_count == 3
    assert summary.profitable_count == 2
    assert summary.losing_count == 1
    assert summary.total_profit == pytest.approx(1_000)
    assert summary.win_rate_pct == pytest.approx(2 / 3 * 100)
    assert summary.best_profit == pytest.approx(1_000)
    assert summary.worst_profit == pytest.approx(-500)
    assert summary.avg_profit == pytest.approx(1_000 / 3)
    assert summary.roi_pct == pytest.approx(1_000 / 3_000 * 100)
