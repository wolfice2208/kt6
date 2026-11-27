"""Тесты журнала сделок: CRUD, изоляция пользователей, статистика."""

from __future__ import annotations

from fastapi.testclient import TestClient

TRADE = {
    "item_id": "test-item",
    "title": "Тестовый предмет",
    "quantity": 2,
    "buy_price": 20_000,
    "sell_price": 31_000,
    "fee_pct": 0.05,
    "extra_cost": 1_000,
    "note": "проверка",
}


def _create(client: TestClient, auth: dict[str, str], **overrides) -> dict:
    payload = {**TRADE, **overrides}
    response = client.post("/api/trades", json=payload, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_read_trade(client: TestClient, auth: dict[str, str]) -> None:
    created = _create(client, auth)
    assert created["item_id"] == "test-item"
    # 31000*2 = 62000; комиссия 5% = 3100; чистая 58900; себестоимость 41000; выгода 17900
    assert created["profit"] == 17900
    assert created["net_revenue"] == 58900
    assert created["roi_pct"] == round(17900 / 41000 * 100, 2)
    assert created["is_profitable"] is True

    read = client.get(f"/api/trades/{created['id']}", headers=auth)
    assert read.status_code == 200
    assert read.json()["profit"] == created["profit"]

    client.delete(f"/api/trades/{created['id']}", headers=auth)


def test_list_returns_only_own_trades(client: TestClient, auth: dict[str, str], other_auth: dict[str, str]) -> None:
    created = _create(client, auth, item_id="list-item")

    mine = client.get("/api/trades", headers=auth).json()
    assert any(trade["id"] == created["id"] for trade in mine)

    strangers = client.get("/api/trades", headers=other_auth).json()
    assert all(trade["id"] != created["id"] for trade in strangers)

    # Чужую сделку нельзя ни прочитать, ни удалить — 404, а не 403.
    assert client.get(f"/api/trades/{created['id']}", headers=other_auth).status_code == 404
    assert client.delete(f"/api/trades/{created['id']}", headers=other_auth).status_code == 404

    client.delete(f"/api/trades/{created['id']}", headers=auth)


def test_unknown_trade_returns_404(client: TestClient, auth: dict[str, str]) -> None:
    assert client.get("/api/trades/999999", headers=auth).status_code == 404
    assert client.delete("/api/trades/999999", headers=auth).status_code == 404


def test_filters_by_item_and_sorting(client: TestClient, auth: dict[str, str]) -> None:
    first = _create(client, auth, item_id="sort-a", title="A", quantity=1, buy_price=1000, sell_price=5000)
    second = _create(client, auth, item_id="sort-b", title="B", quantity=1, buy_price=1000, sell_price=900)

    by_item = client.get("/api/trades", params={"item_id": "sort-a"}, headers=auth).json()
    assert [trade["item_id"] for trade in by_item] == ["sort-a"]

    by_profit = client.get("/api/trades", params={"sort": "profit_desc"}, headers=auth).json()
    profits = [trade["profit"] for trade in by_profit]
    assert profits == sorted(profits, reverse=True)

    ascending = client.get("/api/trades", params={"sort": "profit_asc"}, headers=auth).json()
    assert [trade["profit"] for trade in ascending] == sorted(trade["profit"] for trade in ascending)

    for trade in (first, second):
        client.delete(f"/api/trades/{trade['id']}", headers=auth)


def test_validation_errors(client: TestClient, auth: dict[str, str]) -> None:
    negative = client.post("/api/trades", json={**TRADE, "quantity": 0}, headers=auth)
    assert negative.status_code == 422

    bad_dates = client.post(
        "/api/trades",
        json={
            **TRADE,
            "opened_at": "2026-05-01T00:00:00Z",
            "closed_at": "2026-04-01T00:00:00Z",
        },
        headers=auth,
    )
    assert bad_dates.status_code == 422

    no_item = client.post("/api/trades", json={k: v for k, v in TRADE.items() if k != "item_id"}, headers=auth)
    assert no_item.status_code == 422


def test_stats_are_consistent_with_trades(client: TestClient, auth: dict[str, str]) -> None:
    before = client.get("/api/trades/stats", headers=auth).json()
    created = _create(client, auth, item_id="stats-item", title="Статистика")

    after = client.get("/api/trades/stats", headers=auth).json()
    assert after["trades_count"] == before["trades_count"] + 1
    assert after["total_profit"] == round(before["total_profit"] + created["profit"], 2)
    assert after["by_month"], "должна быть разбивка по месяцам"
    assert after["top_items"] and len(after["top_items"]) <= 5
    assert 0 <= after["win_rate_pct"] <= 100

    client.delete(f"/api/trades/{created['id']}", headers=auth)


def test_stats_empty_for_new_user(client: TestClient, other_auth: dict[str, str]) -> None:
    stats = client.get("/api/trades/stats", headers=other_auth).json()
    assert stats["trades_count"] == 0
    assert stats["total_profit"] == 0
    assert stats["roi_pct"] == 0
    assert stats["by_month"] == []
    assert stats["top_items"] == []


def test_demo_trades_seeded(client: TestClient, auth: dict[str, str]) -> None:
    """Журнал демо-пользователя не пуст: на защите есть что показывать."""
    trades = client.get("/api/trades", headers=auth).json()
    assert len(trades) >= 5
    assert all("profit" in trade and "roi_pct" in trade for trade in trades)
    assert all(trade["title"] for trade in trades), "у засеянных сделок есть название предмета"
