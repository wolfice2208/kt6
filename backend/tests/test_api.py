"""Интеграционные тесты API: каталог, лента лотов, карточка предмета, фильтры и алерты."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def test_health_and_root(client: TestClient) -> None:
    health = client.get("/api/system/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["data_source"] == "mock"
    assert body["items_tracked"] >= 1

    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["docs"] == "/docs"


def test_deals_after_ingestion(client: TestClient) -> None:
    deals = client.get("/api/deals", params={"limit": 100})
    assert deals.status_code == 200
    rows = deals.json()
    assert rows, "после первого обхода mock-источник должен дать лоты"
    first = rows[0]
    assert first["quote"]["buy_price"] > 0
    assert first["quote"]["sell_target"] > 0
    assert "verdict" in first["quote"]

    stats = client.get("/api/deals/stats")
    assert stats.status_code == 200
    # В статистику попадают все обойдённые предметы, в ленту — только с маржой ≥ 0.
    assert stats.json()["items_tracked"] >= len(rows)


def test_item_detail_and_history(client: TestClient) -> None:
    items = client.get("/api/items").json()
    item_id = items[0]["item_id"]
    detail = client.get(f"/api/items/{item_id}")
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["quote"] is not None
    assert payload["lots"], "в карточке должны быть активные лоты"

    history = client.get(f"/api/items/{item_id}/history")
    assert history.status_code == 200
    assert isinstance(history.json(), list)


def test_catalog_endpoint(client: TestClient) -> None:
    page = client.get("/api/catalog").json()
    assert page["catalog_total"] > 800, "в каталоге должен быть весь ассортимент аукциона"
    assert page["total"] == page["catalog_total"]
    assert len(page["items"]) == page["limit"]
    first = page["items"][0]
    assert first["title"] and first["title"] != first["id"]
    assert first["group"]

    groups = client.get("/api/catalog/groups").json()
    assert groups
    filtered = client.get("/api/catalog", params={"group": first["group"]}).json()
    assert filtered["items"] and all(row["group"] == first["group"] for row in filtered["items"])

    by_search = client.get("/api/catalog", params={"search": first["id"]}).json()
    assert any(row["id"] == first["id"] for row in by_search["items"])

    # Точечная выборка по id — этим пользуется калькулятор.
    lookup = client.get("/api/catalog/by-ids", params={"ids": first["id"]}).json()
    assert len(lookup) == 1 and lookup[0]["id"] == first["id"]


def test_catalog_tier_sorting_and_filter(client: TestClient) -> None:
    """Качество снаряжения: сортировка и фильтр. У артефактов ранга нет — качество в лоте."""
    weapons = client.get(
        "/api/catalog", params={"group": "Оружие", "sort": "tier_desc", "limit": 200}
    ).json()
    known = [item["tier_value"] for item in weapons["items"] if item["tier_value"] > 0]
    assert known, "у оружия должен быть ранг"
    assert known == sorted(known, reverse=True)

    only_top = client.get("/api/catalog", params={"group": "Оружие", "tier": max(known)}).json()
    assert only_top["total"] > 0
    assert all(item["tier_value"] == max(known) for item in only_top["items"])


def test_artifact_quality_lives_in_lots(client: TestClient) -> None:
    artifacts = client.get("/api/deals", params={"category": "artefact", "limit": 200}).json()
    assert artifacts, "в мониторинге должны быть артефакты"
    qualities = {deal["quality"] for deal in artifacts if deal.get("quality")}
    assert qualities <= {1, 2, 3, 4, 5, 6, 7}
    with_label = [deal for deal in artifacts if deal.get("quality_label")]
    assert with_label and with_label[0]["quality_label"]


def test_personal_endpoints_require_auth(client: TestClient, auth: dict[str, str]) -> None:
    """Рынок открыт всем, личные данные — только по токену.

    Каталог, лента лотов и карточка предмета публичны: это рыночные данные.
    Фильтры, алерты и журнал сделок принадлежат пользователю, поэтому без
    токена отдают 401. Изменение мониторинга тоже требует входа.
    """
    for path in ("/api/filters", "/api/alerts", "/api/trades"):
        assert client.get(path).status_code == 401, path

    for path in ("/api/catalog", "/api/deals", "/api/items"):
        assert client.get(path).status_code == 200, path

    assert client.post("/api/items", json={"item_id": "x1"}).status_code == 401
    assert client.post("/api/items/bulk", json={"item_ids": ["x1"]}).status_code == 401
    assert client.delete("/api/items/x1").status_code == 401

    assert client.get("/api/filters", headers=auth).status_code == 200


def test_filter_creates_targeted_alert(client: TestClient, auth: dict[str, str]) -> None:
    created = client.post(
        "/api/filters",
        json={
            "name": "Все сделки",
            "min_margin_pct": 0,
            "min_sales_per_day": 0,
            "max_competition": 1000,
            "category_prefix": "",
            "enabled": True,
        },
        headers=auth,
    )
    assert created.status_code == 201

    scan = client.post("/api/system/scan")
    assert scan.status_code == 200
    assert scan.json()["scanned"] >= 1

    alerts = client.get("/api/alerts", headers=auth)
    assert alerts.status_code == 200
    rows = alerts.json()
    assert rows, "фильтр без ограничений должен поймать хотя бы один лот"
    assert rows[0]["user_id"] == "demo"


def test_bulk_add_item_and_checkbox_filter(
    client: TestClient, auth: dict[str, str], other_auth: dict[str, str]
) -> None:
    deals = client.get("/api/deals", params={"limit": 100}).json()
    target_id = deals[0]["item_id"]

    client.delete(f"/api/items/{target_id}", headers=auth)
    response = client.post("/api/items/bulk", json={"item_ids": [target_id]}, headers=auth)
    assert response.status_code == 201
    assert response.json()["added"] == 1

    created = client.post(
        "/api/filters",
        json={
            "name": "Только выбранные предметы",
            "min_margin_pct": 0,
            "min_sales_per_day": 0,
            "max_competition": 1000,
            "category_prefix": "",
            "item_ids": [target_id],
            "enabled": True,
        },
        headers=auth,
    )
    assert created.status_code == 201
    assert created.json()["item_ids"] == [target_id]

    client.post("/api/system/scan")

    matching: list[dict] = []
    for _ in range(40):
        alerts = client.get("/api/alerts", params={"limit": 200}, headers=auth).json()
        matching = [row for row in alerts if row["filter_id"] == created.json()["id"]]
        if matching:
            break
        time.sleep(0.05)
    assert matching, "фильтр по конкретному предмету должен дать алерт"
    assert {row["item_id"] for row in matching} == {target_id}

    # Второй пользователь не видит чужих алертов.
    assert client.get("/api/alerts", headers=other_auth).json() == []


def test_filter_delete_keeps_alert_history(client: TestClient, auth: dict[str, str]) -> None:
    """Удаление фильтра не падает из-за внешнего ключа и не стирает историю алертов."""
    item_id = client.get("/api/deals", params={"limit": 50}).json()[0]["item_id"]
    created = client.post(
        "/api/filters",
        json={
            "name": "Удаляемый фильтр",
            "min_margin_pct": 0,
            "min_sales_per_day": 0,
            "max_competition": 1000,
            "category_prefix": "",
            "item_ids": [item_id],
            "enabled": True,
        },
        headers=auth,
    ).json()
    client.post("/api/system/scan")

    before = client.get("/api/alerts", params={"limit": 200}, headers=auth).json()
    assert any(row["filter_id"] == created["id"] for row in before)

    assert client.delete(f"/api/filters/{created['id']}", headers=auth).status_code == 204

    after = client.get("/api/alerts", params={"limit": 200}, headers=auth).json()
    assert len(after) >= len(before)
    assert [row for row in after if row["filter_id"] is None], "алерты должны остаться"
