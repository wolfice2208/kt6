"""Смоук-проверка бэкенда: вход, каталог, калькулятор, журнал сделок.

Запуск: python tools/smoke.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Скрипт лежит в tools/, а пакеты (main, config, models) — на уровень выше.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_TMP = Path(__file__).resolve().parent.parent / ".smoke_tmp"
_TMP.mkdir(parents=True, exist_ok=True)
_tmp_dir = tempfile.mkdtemp(prefix="run-", dir=_TMP)

os.environ["DATA_SOURCE"] = "mock"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_TMP / Path(_tmp_dir).name / 'smoke.db').as_posix()}"
os.environ["ENABLE_INGESTION"] = "false"
os.environ["MAX_REQUESTS_PER_MINUTE"] = "600"
os.environ.setdefault("DEFAULT_MIN_MARGIN_PCT", "0")

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

ok = 0
fail = 0


def check(label: str, condition: bool, detail: object = "") -> None:
    global ok, fail
    if condition:
        ok += 1
        print(f"  OK   {label}")
    else:
        fail += 1
        print(f"  FAIL {label} :: {detail}")


with TestClient(app) as client:
    print("== system ==")
    health = client.get("/api/system/health")
    check("health 200", health.status_code == 200, health.text[:200])
    check("health ok", health.json().get("status") == "ok", health.text[:200])

    print("== auth ==")
    check("чужой без токена -> 401", client.get("/api/trades").status_code == 401)
    bad = client.post("/api/auth/login", json={"username": "demo", "password": "nope"})
    check("неверный пароль -> 401", bad.status_code == 401, bad.text[:200])

    login = client.post("/api/auth/login", json={"username": "demo", "password": "demo12345"})
    check("вход 200", login.status_code == 200, login.text[:300])
    body = login.json()
    token = body.get("access_token", "")
    check("токен выдан", bool(token))
    check("пользователь в ответе", body.get("user", {}).get("username") == "demo")
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/api/auth/me", headers=headers)
    check("me 200", me.status_code == 200, me.text[:200])
    check("me = demo", me.json().get("username") == "demo")

    print("== каталог и лента ==")
    catalog = client.get("/api/catalog", params={"limit": 5})
    check("каталог 200", catalog.status_code == 200)
    check("каталог не пуст", catalog.json()["total"] > 0, catalog.text[:200])
    deals = client.get("/api/deals", params={"limit": 5})
    check("лента 200", deals.status_code == 200)

    print("== калькулятор ==")
    calc = client.post(
        "/api/trades/calculate",
        json={
            "quantity": 3,
            "buy_price": 10000,
            "sell_price": 15000,
            "fee_pct": 0.05,
            "extra_cost": 500,
            "opened_at": "2026-01-01T00:00:00Z",
            "closed_at": "2026-01-05T00:00:00Z",
        },
    )
    check("calculate 200", calc.status_code == 200, calc.text[:300])
    math = calc.json()
    # 15000*3 = 45000; комиссия 5% = 2250; чистая 42750; себестоимость 30500; выгода 12250
    check("выгода 12250", abs(math["profit"] - 12250.0) < 0.01, math)
    check("ROI ~40.16%", abs(math["roi_pct"] - 40.16) < 0.05, math)
    check("срок 4 дня", abs(math["holding_days"] - 4) < 0.01, math)
    check("профит в день ~3062", abs(math["profit_per_day"] - 3062.5) < 0.1, math)

    invalid = client.post("/api/trades/calculate", json={"quantity": 1, "buy_price": 10, "sell_price": 5,
                                                        "opened_at": "2026-02-01T00:00:00Z",
                                                        "closed_at": "2026-01-01T00:00:00Z"})
    check("даты наоборот -> 422", invalid.status_code == 422, invalid.text[:200])

    print("== журнал ==")
    trades = client.get("/api/trades", headers=headers)
    check("журнал 200", trades.status_code == 200, trades.text[:300])
    check("демо-сделки засеяны", len(trades.json()) >= 5, len(trades.json()))

    created = client.post(
        "/api/trades",
        headers=headers,
        json={
            "item_id": "smoke-1",
            "title": "Смоук-предмет",
            "quantity": 2,
            "buy_price": 20000,
            "sell_price": 31000,
            "fee_pct": 0.05,
            "extra_cost": 1000,
            "note": "проверка",
        },
    )
    check("создание 201", created.status_code == 201, created.text[:300])
    trade_id = created.json()["id"]
    check("выгода > 0", created.json()["profit"] > 0, created.json())

    one = client.get(f"/api/trades/{trade_id}", headers=headers)
    check("сделка по id 200", one.status_code == 200)

    stats = client.get("/api/trades/stats", headers=headers)
    check("stats 200", stats.status_code == 200, stats.text[:300])
    summary = stats.json()
    check("stats.trades_count сходится", summary["trades_count"] == len(trades.json()) + 1, summary)
    check("есть разбивка по месяцам", len(summary["by_month"]) >= 1, summary["by_month"])
    check("есть топ предметов", len(summary["top_items"]) >= 1, summary["top_items"])

    other = client.post("/api/auth/login", json={"username": "student", "password": "student123"}).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}
    check("чужой не видит сделку (404)", client.get(f"/api/trades/{trade_id}", headers=other_headers).status_code == 404)
    check("у чужого свой журнал", client.get("/api/trades", headers=other_headers).json() == [])

    check("удаление 204", client.delete(f"/api/trades/{trade_id}", headers=headers).status_code == 204)
    check("после удаления 404", client.get(f"/api/trades/{trade_id}", headers=headers).status_code == 404)

    print("== защищённые ресурсы ==")
    check("фильтры без токена -> 401", client.get("/api/filters").status_code == 401)
    check("фильтры с токеном 200", client.get("/api/filters", headers=headers).status_code == 200)

print(f"\nИтого: OK={ok}, FAIL={fail}")
raise SystemExit(1 if fail else 0)
